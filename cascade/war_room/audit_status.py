"""Read-only War Room projection of durable health-audit state."""

from __future__ import annotations

import json
import os
import stat
import time
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cascade.task.lifecycle_lock import lifecycle_root, task_lifecycle_read_lock

_STORES = (
    ("action_recovery", "executions.json", "actions"),
    ("orphan_delivery", "orphan_delivery_recoveries.json", "recoveries"),
    ("remediation_dispositions", "remediation_dispositions.json", "dispositions"),
)
_OUTCOMES = ("healthy", "expected_wait", "proven_incident", "unavailable_evidence")
_TIERS = ("task", "feature", "epic")
_MAX_INCIDENT_ROWS = 100
_INCIDENT_RECHECK_BUDGET_SECONDS = 2.0
_RECEIPT_FIELDS = (
    "last_completed_at",
    "next_scheduled_at",
    "interval_seconds",
    "duration_seconds",
    "counts",
    "next_cursor",
)


def health_audit_status(*, root: Path) -> dict[str, object]:
    """Project the compact receipt and current durable incident generations."""

    # Keep the route importable while audit_lane is importing audit -> health ->
    # feature recovery -> the War Room package during supervisor startup.
    from cascade.watchdog.audit_lane import (
        audit_receipt_path,
        read_audit_failure,
        read_audit_receipt,
    )

    unavailable: list[dict[str, str]] = []
    try:
        receipt = read_audit_receipt(root)
    except OSError as exc:
        receipt = None
        unavailable.append({"source": "audit_receipt", "reason": str(exc)})
    else:
        receipt_path = audit_receipt_path(root)
        if receipt is None:
            unavailable.append(
                {
                    "source": "audit_receipt",
                    "reason": (
                        "no completed audit receipt"
                        if not receipt_path.exists()
                        else "audit receipt is malformed or incomplete"
                    ),
                }
            )
        elif not _valid_receipt(receipt):
            receipt = None
            unavailable.append(
                {
                    "source": "audit_receipt",
                    "reason": "audit receipt is malformed or incomplete",
                }
            )
    try:
        failure = read_audit_failure(root)
    except OSError as exc:
        failure = None
        unavailable.append({"source": "audit_failure", "reason": str(exc)})

    incidents, ledger_errors = _active_incidents(root)
    unavailable.extend(ledger_errors)
    counts = _project_counts(receipt.get("counts") if receipt else None)
    from cascade.watchdog.audit_investigation import read_investigation_cases
    from cascade.watchdog.audit_agent_lane import investigation_schedule

    investigations = []
    agent_schedule = {}
    try:
        investigations = list(read_investigation_cases(root=root))
        agent_schedule = investigation_schedule(root)
    except (OSError, ValueError) as exc:
        unavailable.append({"source": "agent_investigations", "reason": type(exc).__name__})
    return {
        "schema_version": 1,
        "last_run": receipt.get("last_completed_at") if receipt else None,
        "next_due": receipt.get("next_scheduled_at") if receipt else None,
        "duration_seconds": receipt.get("duration_seconds") if receipt else None,
        "interval_seconds": receipt.get("interval_seconds") if receipt else None,
        "counts": counts,
        "incidents": incidents,
        "failure": failure,
        "unavailable_evidence": unavailable,
        "investigations": investigations,
        "agent_schedule": agent_schedule,
    }


def _active_incidents(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    projected: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
    candidates: list[tuple[str, str, Mapping[str, Any]]] = []
    home = lifecycle_root(root) / ".cascade"
    with task_lifecycle_read_lock(root=root):
        for store_name, filename, collection in _STORES:
            try:
                payload = _read_small_json(home / filename)
            except (OSError, ValueError) as exc:
                errors.append({"source": store_name, "reason": str(exc)})
                continue
            rows = payload.get(collection) if payload else None
            if rows is None:
                continue
            if not isinstance(rows, Mapping):
                errors.append(
                    {"source": store_name, "reason": f"{collection} is unavailable"}
                )
                continue
            for row_id, row in rows.items():
                if len(candidates) >= _MAX_INCIDENT_ROWS:
                    errors.append(
                        {
                            "source": "incident_ledgers",
                            "reason": f"active incident read is limited to {_MAX_INCIDENT_ROWS} rows",
                        }
                    )
                    break
                if not isinstance(row, Mapping):
                    continue
                incident = row.get("incident")
                if not isinstance(incident, Mapping):
                    continue
                if incident.get("outcome") == "success":
                    continue
                candidates.append((str(row_id), store_name, incident))

    deadline = time.monotonic() + _INCIDENT_RECHECK_BUDGET_SECONDS
    observations: dict[str, tuple[Any, str | None]] = {}
    for row_id, store_name, incident in candidates:
        current, reason = _incident_is_current(
            root, incident, deadline=deadline, observations=observations
        )
        if not current:
            if reason is not None:
                errors.append(
                    {"source": f"{store_name}:{row_id}", "reason": reason}
                )
            continue
        item = _project_incident(row_id, store_name, incident)
        if item is None:
            errors.append(
                {
                    "source": f"{store_name}:{row_id}",
                    "reason": "incident identity is unavailable",
                }
            )
        else:
            projected.append(item)
    projected.sort(
        key=lambda item: (str(item["tier"]), str(item["work_id"]), str(item["incident_id"]))
    )
    return projected, errors


def _incident_is_current(
    root: Path, incident: Mapping[str, Any], *, deadline: float,
    observations: dict[str, tuple[Any, str | None]] | None = None,
) -> tuple[bool, str | None]:
    """Require fresh authoritative generation before calling a ledger row active."""

    work_id = incident.get("work_id")
    generation = incident.get("authoritative_generation")
    failure_class = incident.get("failure_class")
    if not all(
        isinstance(value, str) and value
        for value in (work_id, generation, failure_class)
    ):
        return False, "incident identity is unavailable"
    # Repeated historical generations share one current observation for this
    # response only. Never carry this read cache into a later request or repair.
    if observations is None:
        observations = {}
    if work_id not in observations:
        observations[work_id] = _observe_incident_work(root, work_id, deadline)
    observation, error = observations[work_id]
    if error is not None:
        return False, error
    if observation.classification == "unavailable_evidence":
        return False, f"current lifecycle evidence unavailable: {observation.reason}"
    if observation.classification != "proven_incident" or observation.incident is None:
        return False, None
    if (
        str(observation.generation) != generation
        or observation.incident.failure_class != failure_class
    ):
        return False, None
    return True, None


def _observe_incident_work(
    root: Path, work_id: str, deadline: float
) -> tuple[Any, str | None]:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        return None, "current lifecycle recheck exceeded its bounded budget"
    try:
        from cascade.watchdog.audit import project_audit_observation

        observation = project_audit_observation(
            work_id,
            root=root,
            timeout_seconds=remaining,
        )
    except Exception as exc:
        return None, f"current lifecycle state is unavailable ({type(exc).__name__})"
    return observation, None


def _valid_receipt(receipt: Mapping[str, Any]) -> bool:
    if any(field not in receipt for field in _RECEIPT_FIELDS):
        return False
    if not _aware_timestamp(receipt["last_completed_at"]) or not _aware_timestamp(
        receipt["next_scheduled_at"]
    ):
        return False
    if (
        not isinstance(receipt["interval_seconds"], int)
        or isinstance(receipt["interval_seconds"], bool)
        or receipt["interval_seconds"] <= 0
    ):
        return False
    duration = receipt["duration_seconds"]
    if (
        not isinstance(duration, (int, float))
        or isinstance(duration, bool)
        or duration < 0
    ):
        return False
    counts = receipt["counts"]
    if not isinstance(counts, Mapping) or any(
        not isinstance(key, str) or type(value) is not int or value < 0
        for key, value in counts.items()
    ):
        return False
    return receipt["next_cursor"] is None or isinstance(receipt["next_cursor"], str)


def _aware_timestamp(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    return parsed.tzinfo is not None


def _project_incident(
    row_id: str, store_name: str, incident: Mapping[str, Any]
) -> dict[str, object] | None:
    work_id, tier = incident.get("work_id"), incident.get("tier")
    owner = incident.get("accountable_owner")
    if not isinstance(work_id, str) or tier not in _TIERS or not isinstance(owner, str):
        return None
    request = incident.get("request")
    request = dict(request) if isinstance(request, Mapping) else {}
    acknowledgement = incident.get("acknowledgement")
    acknowledgement = dict(acknowledgement) if isinstance(acknowledgement, Mapping) else {}
    result = incident.get("result")
    result = dict(result) if isinstance(result, Mapping) else {}
    attempts = incident.get("attempts")
    attempts = [dict(item) for item in attempts if isinstance(item, Mapping)] if isinstance(attempts, list) else []
    claim_token = request.get("claim_token")
    accepted_attempt = next(
        (
            item
            for item in reversed(attempts)
            if item.get("accepted_at")
            and (not claim_token or item.get("claim_token") == claim_token)
        ),
        {},
    )
    acknowledged = bool(acknowledgement) or bool(accepted_attempt)
    if acknowledged and not acknowledgement:
        acknowledgement = {
            "accepted_at": accepted_attempt.get("accepted_at"),
            "attempt": accepted_attempt.get("attempt"),
        }
    request_state = (
        "resulted"
        if result
        else "acknowledged"
        if acknowledged
        else "reserved"
        if request.get("claim_token")
        else "pending"
        if request.get("delivered_at")
        else "recorded"
        if request
        else "unavailable"
    )
    evidence = incident.get("evidence")
    evidence_value = dict(evidence) if isinstance(evidence, Mapping) and evidence else None
    policy = incident.get("retry_policy")
    policy_value = dict(policy) if isinstance(policy, Mapping) else {}
    operation = request.get("operation") or incident.get("selected_capability")
    outcome = incident.get("outcome")
    cooldown_until = (
        incident.get("claim_expires_at")
        if outcome == "claimed"
        else incident.get("next_reassessment_at")
    )
    return {
        "incident_id": str(request.get("reservation_id") or row_id),
        "store": store_name,
        "work_id": work_id,
        "tier": tier,
        "owner": owner,
        "failure_class": str(incident.get("failure_class") or "unavailable"),
        "generation": incident.get("authoritative_generation"),
        "evidence": {"available": evidence_value is not None, "value": evidence_value},
        "request": {"state": request_state, "value": request or None},
        "acknowledgement": {
            "available": acknowledged,
            "value": acknowledgement or None,
        },
        "result": {"available": bool(result), "value": result or None},
        "outcome": outcome,
        "retry": {
            "state": _cooldown_state(cooldown_until, outcome),
            "cooldown_until": cooldown_until,
            "claim_expires_at": incident.get("claim_expires_at"),
            "next_reassessment_at": incident.get("next_reassessment_at"),
            "policy": policy_value,
            "attempts": attempts,
        },
        "resume_action": {"operation": operation, "owner": owner},
        "recorded_at": incident.get("recorded_at"),
    }


def _project_counts(raw: object) -> dict[str, object]:
    values = raw if isinstance(raw, Mapping) else {}
    by_outcome = {
        name: _nonnegative_int(values.get(name)) for name in _OUTCOMES
    }
    by_tier: dict[str, dict[str, int]] = defaultdict(dict)
    for tier in _TIERS:
        for outcome in _OUTCOMES:
            by_tier[tier][outcome] = _nonnegative_int(
                values.get(f"tier.{tier}.{outcome}")
            )
    return {"by_outcome": by_outcome, "by_tier": dict(by_tier)}


def _nonnegative_int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


def _cooldown_state(deadline: object, outcome: object) -> str:
    if not isinstance(deadline, str):
        return "ready"
    try:
        parsed = datetime.fromisoformat(deadline)
    except ValueError:
        return "unavailable"
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) >= parsed.astimezone(timezone.utc):
        return "ready"
    return "active_claim" if outcome == "claimed" else "cooldown"


def _read_small_json(path: Path) -> dict[str, Any] | None:
    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"{path.name} is not a regular file")
        if info.st_size > 8 * 1024 * 1024:
            raise OSError(f"{path.name} is too large")
        content = os.read(descriptor, info.st_size + 1)
    finally:
        os.close(descriptor)
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{path.name} is unreadable") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} is unreadable")
    return value


__all__ = ["health_audit_status"]
