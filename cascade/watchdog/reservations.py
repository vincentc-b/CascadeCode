"""Locked incident rechecks and crash-safe health-auditor reservations.

This module is an admission boundary, not a repair adapter.  It records a
bounded claim in the durable store already owned by the selected capability,
then returns.  Callers must release the lifecycle lock before invoking the
operation (and the operation remains responsible for its own publication
preconditions).
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.board.work_ids import parse_work_id_parts
from cascade.task.execution import execution_views
from cascade.task.lifecycle_lock import lifecycle_root, task_lifecycle_lock
from cascade.watchdog.audit import AuditObservation, project_audit_observation
from cascade.watchdog.capabilities import CapabilityDescriptor
from cascade.watchdog.incidents import incident_record

ReservationState = Literal["reserved", "stale", "gated", "unavailable"]
ResultOutcome = Literal["success", "error", "refused", "deferred", "unsafe", "no_op"]
FreshRecheck = Callable[[str, Path], AuditObservation | Mapping[str, Any]]

_RESULT_OUTCOMES = frozenset({"success", "error", "refused", "deferred", "unsafe", "no_op"})
_GATE_WORDS = (
    "approval",
    "comment",
    "dependency",
    "credential",
    "permission",
    "install",
    "human",
    "owner_decision",
)


@dataclass(frozen=True, slots=True)
class IncidentReservation:
    """A lease-bound handoff token for a later lifecycle adapter."""

    reservation_id: str
    claim_token: str
    work_id: str
    tier: str
    generation: str
    failure_class: str
    capability: str
    durable_store: str
    claimed_at: str
    claim_expires_at: str


@dataclass(frozen=True, slots=True)
class ReservationDecision:
    state: ReservationState
    reason: str
    reservation: IncidentReservation | None = None

    @property
    def reserved(self) -> bool:
        return self.state == "reserved"


class ReservationConflict(RuntimeError):
    """A result does not belong to the store's current reservation token."""


def reserve_after_recheck(
    incident: Mapping[str, Any],
    capability: CapabilityDescriptor,
    *,
    root: Path,
    now: datetime | None = None,
    claim_seconds: int | None = None,
    fresh_recheck: FreshRecheck | None = None,
) -> ReservationDecision:
    """Freshly validate and atomically reserve one incident generation.

    The default audit projection is prepared before taking the lifecycle lock
    because it may inspect Git.  Under the lock we re-read the owning document
    and Task execution state, which are the local authority protected by that
    lock.  A custom ``fresh_recheck`` is for local projections only and is run
    under the lock; it must not perform provider, network, Git, or test I/O.
    """

    repo = resolve_root(root)
    fields = _incident_fields(incident)
    work_id, tier, failure, generation, operation, evidence, owner = fields
    mismatch = _capability_mismatch(capability, tier, failure, operation)
    if mismatch is not None:
        return ReservationDecision("unavailable", mismatch)
    seconds = claim_seconds or int(
        dict(incident.get("retry_policy") or {}).get("claim_seconds") or 300
    )
    if seconds < 1:
        raise ValueError("claim lease must be positive")

    # Git/worktree facts are deliberately gathered without a broad lifecycle
    # lock.  The adapter which consumes the reservation must repeat any Git
    # head checks immediately before its external effect.
    prepared: AuditObservation | Mapping[str, Any] | None = None
    if fresh_recheck is None:
        try:
            prepared = project_audit_observation(work_id, root=repo)
        except Exception:
            return ReservationDecision("stale", "incident_disappeared")

    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with task_lifecycle_lock(root=repo):
        try:
            fresh = (
                fresh_recheck(work_id, repo)
                if fresh_recheck is not None
                else _locked_local_recheck(prepared, root=repo)
            )
        except Exception:
            return ReservationDecision("stale", "incident_disappeared")
        state, reason = _compare_fresh(fresh, work_id, tier, generation, failure)
        if state != "reserved":
            return ReservationDecision(state, reason)

        ledger = _read_store(capability.durable_store, repo)
        reservation_id = _reservation_id(work_id, failure, generation, capability.name)
        previous_row = ledger.rows.get(reservation_id)
        previous = _row_incident(previous_row)
        if previous is not None:
            prior_outcome = previous.get("outcome")
            if prior_outcome == "success":
                return ReservationDecision("unavailable", "terminal_success")
            deadline_field = (
                "claim_expires_at"
                if prior_outcome == "claimed"
                else "next_reassessment_at"
            )
            deadline = _parse_time(previous.get(deadline_field))
            if deadline is not None and stamped < deadline:
                reason = "active_claim" if prior_outcome == "claimed" else "reassessment_cooldown"
                return ReservationDecision("unavailable", reason)

        prior_attempts = list(previous.get("attempts") or []) if previous else []
        if len(prior_attempts) >= capability.attempt_bound:
            return ReservationDecision("unavailable", "attempt_bound_exhausted")
        claim_token = uuid.uuid4().hex
        request = {
            "reservation_id": reservation_id,
            "claim_token": claim_token,
            "operation": capability.operation,
        }
        contract = incident_record(
            work_id=work_id,
            tier=tier,  # type: ignore[arg-type]
            accountable_owner=owner,
            failure_class=failure,
            generation=generation,
            evidence=evidence,
            selected_capability=operation,
            request=request,
            attempts=[
                *prior_attempts,
                {
                    "attempt": len(prior_attempts) + 1,
                    "reservation_id": reservation_id,
                    "claim_token": claim_token,
                    "started_at": stamped.isoformat(),
                    "outcome": None,
                },
            ],
            outcome="claimed",
            now=stamped,
            claim_seconds=seconds,
            attempt_bound=capability.attempt_bound,
        )
        row = _claim_row(
            previous_row,
            reservation_id=reservation_id,
            capability=capability,
            contract=contract,
        )
        ledger.rows[reservation_id] = row
        _write_store(ledger)
        reservation = IncidentReservation(
            reservation_id=reservation_id,
            claim_token=claim_token,
            work_id=work_id,
            tier=tier,
            generation=generation,
            failure_class=failure,
            capability=capability.name,
            durable_store=capability.durable_store,
            claimed_at=str(contract["recorded_at"]),
            claim_expires_at=str(contract["claim_expires_at"]),
        )
        return ReservationDecision("reserved", "fresh_generation_claimed", reservation)


def record_result(
    reservation: IncidentReservation,
    acknowledgement: Mapping[str, Any] | None,
    result: Mapping[str, Any],
    *,
    root: Path,
    now: datetime | None = None,
) -> Mapping[str, Any]:
    """Durably finish the exact claim token, preserving every earlier attempt.

    Replaying the same completed token is idempotent.  A late worker cannot
    overwrite a newer claim after its lease was reassessed.
    """

    outcome = result.get("outcome")
    if outcome not in _RESULT_OUTCOMES:
        raise ValueError("result outcome must be a supported incident outcome")
    repo = resolve_root(root)
    stamped = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    with task_lifecycle_lock(root=repo):
        ledger = _read_store(reservation.durable_store, repo)
        row = ledger.rows.get(reservation.reservation_id)
        current = _row_incident(row)
        if current is None:
            raise ReservationConflict("reservation receipt is missing")
        request = current.get("request")
        token = request.get("claim_token") if isinstance(request, Mapping) else None
        if token != reservation.claim_token:
            raise ReservationConflict("reservation was superseded by another claim")
        if current.get("outcome") != "claimed":
            return json.loads(json.dumps(current))
        if (
            current.get("work_id") != reservation.work_id
            or current.get("tier") != reservation.tier
            or current.get("authoritative_generation") != reservation.generation
        ):
            raise ReservationConflict("reservation identity changed")

        attempts = list(current.get("attempts") or [])
        if not attempts or attempts[-1].get("claim_token") != reservation.claim_token:
            raise ReservationConflict("reservation attempt history is inconsistent")
        attempts[-1] = {
            **attempts[-1],
            "finished_at": stamped.isoformat(),
            "outcome": outcome,
        }
        policy = dict(current.get("retry_policy") or {})
        final = incident_record(
            work_id=reservation.work_id,
            tier=reservation.tier,  # type: ignore[arg-type]
            accountable_owner=str(current["accountable_owner"]),
            failure_class=reservation.failure_class,
            generation=reservation.generation,
            evidence=dict(current.get("evidence") or {}),
            selected_capability=str(current["selected_capability"]),
            request=dict(request),
            acknowledgement=dict(acknowledgement or {}),
            result=dict(result),
            attempts=attempts,
            outcome=outcome,  # type: ignore[arg-type]
            now=stamped,
            reassessment_seconds=int(policy.get("reassessment_seconds") or 60),
            claim_seconds=int(policy.get("claim_seconds") or 300),
            attempt_bound=int(policy.get("attempt_bound") or 3),
        )
        assert row is not None
        history = list(row.get("incident_history") or [])
        history.append(json.loads(json.dumps(current)))
        row["incident_history"] = history
        row["incident"] = final
        if reservation.durable_store == "action_recovery":
            row["recovery_state"] = "completed" if outcome == "success" else "retryable"
            row["updated_at"] = stamped.isoformat()
        ledger.rows[reservation.reservation_id] = row
        _write_store(ledger)
        return json.loads(json.dumps(final))


def _incident_fields(
    incident: Mapping[str, Any],
) -> tuple[str, str, str, str, str, dict[str, Any], str]:
    work = incident.get("work")
    work_id = incident.get("work_id")
    tier = incident.get("tier")
    if isinstance(work, Mapping):
        if work_id is not None and work_id != work.get("work_id"):
            raise ValueError("incident work identities disagree")
        if tier is not None and tier != work.get("tier"):
            raise ValueError("incident tiers disagree")
        work_id, tier = work.get("work_id"), work.get("tier")
    if not isinstance(work_id, str) or tier not in {"task", "feature", "epic"}:
        raise ValueError("incident needs a typed work identity")
    try:
        actual = parse_work_id_parts(work_id).tier
    except Exception as exc:
        raise ValueError("incident work ID is invalid") from exc
    if actual != tier:
        raise ValueError(f"{work_id!r} is not a {tier} ID")
    failure = incident.get("failure_class")
    generation = incident.get("authoritative_generation")
    operation = incident.get("selected_capability")
    evidence = incident.get("evidence")
    owner = incident.get("accountable_owner")
    if not all(isinstance(value, str) and value for value in (failure, generation, operation, owner)):
        raise ValueError("incident identity fields are incomplete")
    if not isinstance(evidence, Mapping):
        raise ValueError("incident evidence must be a mapping")
    # parent_rev is evidence only.  In particular it can never repair or
    # substitute for a missing/mistyped Feature work identity above.
    return work_id, tier, failure, generation, operation, dict(evidence), owner


def _capability_mismatch(
    capability: CapabilityDescriptor, tier: str, failure: str, operation: str
) -> str | None:
    if tier not in capability.tiers:
        return "capability_tier_mismatch"
    if failure not in capability.failure_classes:
        return "capability_failure_mismatch"
    if operation not in {capability.name, capability.operation, capability.action_kind}:
        return "capability_operation_mismatch"
    if not callable(capability.executor):
        return "capability_not_executable"
    return None


def _locked_local_recheck(
    prepared: AuditObservation | Mapping[str, Any] | None, *, root: Path
) -> AuditObservation | Mapping[str, Any]:
    if prepared is None:
        raise ValueError("fresh audit projection is unavailable")
    work_id, _tier, _generation, _classification, _reason, evidence = _fresh_fields(prepared)
    tracking = getattr(getattr(prepared, "evidence", None), "tracking_repository", root)
    doc = read_doc(work_id, root=tracking)
    expected_revision = getattr(getattr(prepared, "document_revision", None), "value", None)
    if expected_revision is not None and doc.sha != expected_revision:
        raise ValueError("document revision changed")
    expected_status = getattr(evidence, "status", None)
    expected_parent = getattr(evidence, "parent_id", None)
    if expected_status is not None and doc.meta.status != expected_status:
        raise ValueError("document status changed")
    if doc.meta.parent != expected_parent:
        raise ValueError("document owner changed")
    expected_execution = getattr(evidence, "execution", None)
    if doc.meta.tier == "task" and execution_views({work_id}, root=root).get(work_id) != expected_execution:
        raise ValueError("task execution changed")
    return prepared


def _fresh_fields(
    fresh: AuditObservation | Mapping[str, Any],
) -> tuple[str, str, str, str, str, object]:
    if isinstance(fresh, Mapping):
        identity = fresh.get("identity") if isinstance(fresh.get("identity"), Mapping) else fresh
        work = identity.get("work_id")
        work_id = getattr(work, "value", work)
        tier = identity.get("tier")
        generation = identity.get("generation")
        generation = getattr(generation, "value", generation)
        classification = fresh.get("classification")
        reason = fresh.get("reason")
        evidence = fresh.get("evidence") or {}
    else:
        work_id = fresh.work_id.value
        tier = fresh.tier
        generation = fresh.generation.value
        classification = fresh.classification
        reason = fresh.reason
        evidence = fresh.evidence
    return str(work_id), str(tier), str(generation), str(classification), str(reason), evidence


def _compare_fresh(
    fresh: AuditObservation | Mapping[str, Any],
    work_id: str,
    tier: str,
    generation: str,
    failure: str,
) -> tuple[ReservationState, str]:
    fresh_id, fresh_tier, fresh_generation, classification, reason, evidence = _fresh_fields(fresh)
    if fresh_id != work_id or fresh_tier != tier:
        return "stale", "typed_identity_changed"
    if fresh_generation != generation:
        return "stale", "authoritative_generation_changed"
    gates = getattr(evidence, "gates", None)
    if gates is None and isinstance(evidence, Mapping):
        gates = evidence.get("gates") or ()
    if gates or classification == "expected_wait" or any(word in reason for word in _GATE_WORDS):
        return "gated", "protected_lifecycle_gate"
    if classification == "unavailable_evidence":
        return "unavailable", "fresh_evidence_unavailable"
    if classification != "proven_incident" or reason != failure:
        return "stale", "incident_no_longer_matches"
    return "reserved", "fresh_generation"


@dataclass(slots=True)
class _Store:
    path: Path
    collection: str
    payload: dict[str, Any]
    rows: dict[str, dict[str, Any]]


def _read_store(name: str, root: Path) -> _Store:
    home = lifecycle_root(root) / ".cascade"
    specs = {
        "action_recovery": ("executions.json", "actions"),
        "orphan_delivery": ("orphan_delivery_recoveries.json", "recoveries"),
        "remediation_dispositions": ("remediation_dispositions.json", "dispositions"),
    }
    if name not in specs:
        raise ValueError(f"unknown durable recovery store: {name}")
    filename, collection = specs[name]
    path = home / filename
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ReservationConflict(f"durable recovery store is unreadable: {filename}") from exc
        if isinstance(loaded, dict):
            payload = loaded
    raw = payload.get(collection)
    rows = {
        str(key): dict(value)
        for key, value in (raw.items() if isinstance(raw, dict) else ())
        if isinstance(value, dict)
    }
    return _Store(path, collection, payload, rows)


def _write_store(store: _Store) -> None:
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.payload[store.collection] = store.rows
    store.payload["version"] = max(int(store.payload.get("version") or 1), 2)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{store.path.name}.", suffix=".tmp", dir=store.path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(store.payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, store.path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _reservation_id(work_id: str, failure: str, generation: str, capability: str) -> str:
    digest = hashlib.sha256(
        json.dumps([work_id, failure, generation, capability], separators=(",", ":")).encode()
    ).hexdigest()[:24]
    return f"{work_id}:health_reservation:{digest}"


def _row_incident(row: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(row, Mapping):
        return None
    incident = row.get("incident")
    return dict(incident) if isinstance(incident, Mapping) else None


def _claim_row(
    previous: Mapping[str, Any] | None,
    *,
    reservation_id: str,
    capability: CapabilityDescriptor,
    contract: Mapping[str, Any],
) -> dict[str, Any]:
    row = dict(previous or {})
    prior = _row_incident(previous)
    history = list(row.get("incident_history") or [])
    if prior is not None:
        history.append(prior)
    row.update(
        reservation_id=reservation_id,
        durable_store=capability.durable_store,
        incident=dict(contract),
        incident_history=history,
    )
    if capability.durable_store == "action_recovery":
        row.update(
            action_id=reservation_id,
            action_kind="health_auditor_reservation",
            recovery_state="running",
            failure_classification=None,
            attempt_count=len(contract.get("attempts") or []),
            attempt_bound=capability.attempt_bound,
            metadata={"affected_work_id": contract["work_id"]},
            recovery={
                "owning_team": None,
                "evidence": {"affected_work_id": contract["work_id"]},
            },
            idempotency_key=reservation_id,
            execution_claim=None,
            attempts=[],
            created_at=row.get("created_at") or contract["recorded_at"],
            updated_at=contract["recorded_at"],
        )
    return row


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)


__all__ = [
    "IncidentReservation",
    "ReservationConflict",
    "ReservationDecision",
    "record_result",
    "reserve_after_recheck",
]
