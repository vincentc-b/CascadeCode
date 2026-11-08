"""Read-only War Room projection of durable health-audit state."""

from __future__ import annotations

import json
import os
import stat
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


def health_audit_status(*, root: Path) -> dict[str, object]:
    """Project the compact receipt and current durable incident generations."""

    # Keep the route importable while audit_lane is importing audit -> health ->
    # feature recovery -> the War Room package during supervisor startup.
    from cascade.watchdog.audit_lane import read_audit_failure, read_audit_receipt

    unavailable: list[dict[str, str]] = []
    try:
        receipt = read_audit_receipt(root)
    except OSError as exc:
        receipt = None
        unavailable.append({"source": "audit_receipt", "reason": str(exc)})
    try:
        failure = read_audit_failure(root)
    except OSError as exc:
        failure = None
        unavailable.append({"source": "audit_failure", "reason": str(exc)})

    incidents, ledger_errors = _active_incidents(root)
    unavailable.extend(ledger_errors)
    counts = _project_counts(receipt.get("counts") if receipt else None)
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
    }


def _active_incidents(
    root: Path,
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    projected: list[dict[str, object]] = []
    errors: list[dict[str, str]] = []
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
                if not isinstance(row, Mapping):
                    continue
                incident = row.get("incident")
                if not isinstance(incident, Mapping):
                    continue
                if incident.get("outcome") == "success":
                    continue
                item = _project_incident(str(row_id), store_name, incident)
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
    acknowledged = bool(acknowledgement) or any(item.get("accepted_at") for item in attempts)
    if acknowledged and not acknowledgement:
        accepted_attempt = next(
            (item for item in reversed(attempts) if item.get("accepted_at")), {}
        )
        acknowledgement = {
            "accepted_at": accepted_attempt.get("accepted_at"),
            "attempt": accepted_attempt.get("attempt"),
        }
    request_state = (
        "resulted"
        if result
        else "acknowledged"
        if acknowledged
        else "pending"
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
