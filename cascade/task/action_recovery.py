"""Durable recovery records for logical lifecycle actions.

Records live in the existing lifecycle sidecar (.cascade/executions.json), under
an additive actions key. This keeps recovery on the same locking and atomic
replacement boundary as task execution health.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock

FailureClassification = Literal[
    "deterministic_repair",
    "transient_retry",
    "owner_decision",
    "human_gate",
    "terminal_blocker",
]
RecoveryState = Literal[
    "pending",
    "running",
    "retryable",
    "repaired",
    "awaiting_owner_decision",
    "awaiting_human_gate",
    "blocked",
    "completed",
]
AttemptOutcome = Literal["succeeded", "failed", "cancelled"]
PreconditionState = Literal["pending", "repaired", "unrepairable"]
DecisionOwner = Literal["feature_team", "epic_team"]

_CLASSIFICATIONS = frozenset(FailureClassification.__args__)
_STATES = frozenset(RecoveryState.__args__)
_OUTCOMES = frozenset(AttemptOutcome.__args__)
_PRECONDITION_STATES = frozenset(PreconditionState.__args__)
_DECISION_OWNERS = frozenset(DecisionOwner.__args__)


class ActionRecoveryError(ValueError):
    """An action recovery transition cannot be recorded."""


class ActionNotFound(ActionRecoveryError):
    """The requested durable action does not exist."""


class AttemptAlreadyFinalized(ActionRecoveryError):
    """An attempt outcome is immutable once it has been finalized."""


class ActionFailure(ActionRecoveryError):
    """An executor-reported failure with a durable recovery classification."""

    def __init__(
        self,
        classification: FailureClassification,
        message: str = "action failed",
        *,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.classification = classification
        self.metadata = _validate_metadata(metadata, field="failure metadata")


@dataclass(frozen=True)
class ActionContext:
    """Stable information for an executor's idempotent downstream effect."""

    action_id: str
    attempt_number: int
    idempotency_key: str


@dataclass(frozen=True)
class ActionResult:
    """An explicit outcome returned by an action executor."""

    outcome: AttemptOutcome = "succeeded"
    classification: FailureClassification | None = None
    metadata: Mapping[str, Any] | None = None


def _path(root: Path) -> Path:
    return root / ".cascade" / "executions.json"


def _iso(now: datetime | None) -> str:
    return (now or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _read_payload(root: Path) -> dict[str, Any]:
    path = _path(root)
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dict(value) if isinstance(value, dict) else {}


def _write_payload(root: Path, payload: Mapping[str, Any]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent, text=True
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def _actions(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    actions = payload.get("actions")
    if not isinstance(actions, dict):
        return {}
    return {
        str(identity): dict(action)
        for identity, action in actions.items()
        if isinstance(action, dict)
    }


def _validate_identity(identity: str) -> None:
    if not identity or identity.strip() != identity:
        raise ActionRecoveryError("action identity must be a nonempty stable string")


def _validate_choice(value: str, choices: frozenset[str], *, field: str) -> None:
    if value not in choices:
        raise ActionRecoveryError(f"unknown {field}: {value}")


def _validate_metadata(
    metadata: Mapping[str, Any] | None, *, field: str
) -> dict[str, Any]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ActionRecoveryError(f"{field} must be a mapping")
    try:
        encoded = json.dumps(dict(metadata))
    except (TypeError, ValueError) as exc:
        raise ActionRecoveryError(f"{field} must be JSON serializable") from exc
    return json.loads(encoded)


def _copy(action: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(action))


def _validate_lifecycle_state(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or value.strip() != value:
        raise ActionRecoveryError("lifecycle state must be a nonempty string")
    return value


def _validate_owning_team(value: Mapping[str, Any] | None) -> dict[str, str] | None:
    """Validate the durable owner without coupling recovery to board documents."""

    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise ActionRecoveryError("owning team must be a mapping")
    kind = value.get("kind")
    work_id = value.get("work_id")
    _validate_choice(kind, _DECISION_OWNERS, field="owning team kind")
    if not isinstance(work_id, str) or not work_id or work_id.strip() != work_id:
        raise ActionRecoveryError("owning team work_id must be a nonempty string")
    return {"kind": kind, "work_id": work_id}


def _validate_human_blocker(value: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Keep a human gate actionable after the process that observed it exits."""

    if value is None:
        return None
    details = _validate_metadata(value, field="human blocker")
    required = ("code", "message", "required_action")
    if any(
        not isinstance(details.get(key), str) or not details[key].strip()
        for key in required
    ):
        raise ActionRecoveryError(
            "human blocker needs nonempty code, message, and required_action"
        )
    return details


def _recovery_record(
    action_id: str,
    action_kind: str,
    *,
    lifecycle_state: str | None = None,
    owning_team: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    retry_marker: Mapping[str, Any] | None = None,
    routing_marker: Mapping[str, Any] | None = None,
    human_blocker: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the additive durable context shared by lifecycle actions.

    ``metadata`` remains deliberately application-defined for compatibility.
    This separately named record holds the facts needed to resume a branch or
    lifecycle request without reconstructing them from transient process state.
    """

    return {
        "original_action": {"action_id": action_id, "action_kind": action_kind},
        "lifecycle_state": _validate_lifecycle_state(lifecycle_state),
        "owning_team": _validate_owning_team(owning_team),
        "evidence": _validate_metadata(evidence, field="evidence"),
        "provenance": _validate_metadata(provenance, field="provenance"),
        "retry_marker": _validate_metadata(retry_marker, field="retry marker"),
        "routing_marker": _validate_metadata(routing_marker, field="routing marker"),
        "human_blocker": _validate_human_blocker(human_blocker),
    }


def create_or_load_action(
    action_id: str,
    action_kind: str,
    *,
    root: Path,
    attempt_bound: int,
    recovery_state: RecoveryState = "pending",
    failure_classification: FailureClassification | None = None,
    metadata: Mapping[str, Any] | None = None,
    lifecycle_state: str | None = None,
    owning_team: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    retry_marker: Mapping[str, Any] | None = None,
    routing_marker: Mapping[str, Any] | None = None,
    human_blocker: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Create one action by stable identity, or return its original durable record."""

    _validate_identity(action_id)
    if not action_kind or action_kind.strip() != action_kind:
        raise ActionRecoveryError("action kind must be a nonempty string")
    if attempt_bound < 1:
        raise ActionRecoveryError("attempt bound must be positive")
    if recovery_state not in _STATES:
        raise ActionRecoveryError(f"unknown recovery state: {recovery_state}")
    if (
        failure_classification is not None
        and failure_classification not in _CLASSIFICATIONS
    ):
        raise ActionRecoveryError(
            f"unknown failure classification: {failure_classification}"
        )
    initial_metadata = _validate_metadata(metadata, field="metadata")
    recovery = _recovery_record(
        action_id,
        action_kind,
        lifecycle_state=lifecycle_state,
        owning_team=owning_team,
        evidence=evidence,
        provenance=provenance,
        retry_marker=retry_marker,
        routing_marker=routing_marker,
        human_blocker=human_blocker,
    )
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        existing = actions.get(action_id)
        if existing is not None:
            if existing.get("action_kind") != action_kind:
                raise ActionRecoveryError(
                    f"action identity {action_id!r} already belongs to a different kind"
                )
            return _copy(existing)

        created = _iso(now)
        action = {
            "action_id": action_id,
            "action_kind": action_kind,
            "recovery_state": recovery_state,
            "failure_classification": failure_classification,
            "attempt_count": 0,
            "attempt_bound": attempt_bound,
            "metadata": initial_metadata,
            "recovery": recovery,
            "idempotency_key": action_id,
            "execution_claim": None,
            "created_at": created,
            "updated_at": created,
            "attempts": [],
        }
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def update_recovery_record(
    action_id: str,
    *,
    root: Path,
    lifecycle_state: str | None = None,
    owning_team: Mapping[str, Any] | None = None,
    evidence: Mapping[str, Any] | None = None,
    provenance: Mapping[str, Any] | None = None,
    retry_marker: Mapping[str, Any] | None = None,
    routing_marker: Mapping[str, Any] | None = None,
    human_blocker: Mapping[str, Any] | None = None,
    clear_human_blocker: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist new lifecycle evidence without replacing the original request.

    Each supplied mapping replaces only its corresponding context field.  This
    makes retries and owner handoffs additive at the action boundary while
    preserving historical user files, approvals, and application ``metadata``.
    ``clear_human_blocker`` is explicit so an empty update cannot accidentally
    erase an unresolved human gate.
    """

    _validate_identity(action_id)
    if clear_human_blocker and human_blocker is not None:
        raise ActionRecoveryError("cannot set and clear a human blocker together")
    validated = {
        "lifecycle_state": _validate_lifecycle_state(lifecycle_state),
        "owning_team": _validate_owning_team(owning_team),
        "evidence": _validate_metadata(evidence, field="evidence")
        if evidence is not None
        else None,
        "provenance": _validate_metadata(provenance, field="provenance")
        if provenance is not None
        else None,
        "retry_marker": _validate_metadata(retry_marker, field="retry marker")
        if retry_marker is not None
        else None,
        "routing_marker": _validate_metadata(routing_marker, field="routing marker")
        if routing_marker is not None
        else None,
        "human_blocker": _validate_human_blocker(human_blocker),
    }
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        action_kind = action.get("action_kind")
        if not isinstance(action_kind, str):
            raise ActionRecoveryError("action has no valid action kind")
        # Records written before this extension are valid.  Materialize the
        # additive context on their first update, retaining every old field.
        recovery = _recovery_record(action_id, action_kind)
        if isinstance(action.get("recovery"), Mapping):
            recovery.update(
                _validate_metadata(action["recovery"], field="recovery record")
            )
        original = recovery.get("original_action")
        if original != {"action_id": action_id, "action_kind": action_kind}:
            raise ActionRecoveryError(
                "recovery record cannot change original action identity"
            )
        for field, value in validated.items():
            if value is not None:
                recovery[field] = value
        if clear_human_blocker:
            recovery["human_blocker"] = None
        stamped = _iso(now)
        action.update(recovery=recovery, updated_at=stamped)
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 3)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def replace_action_metadata(
    action_id: str, metadata: Mapping[str, Any], *, root: Path
) -> dict[str, Any]:
    """Atomically replace an action's descriptive, non-control metadata.

    Validation evidence is descriptive: it identifies the commit/base pair the
    queued merge represents, while recovery state and completed attempts remain
    immutable.  Replacing it lets a later green validation supersede stale
    evidence without creating a second queue item for the same Task.
    """

    _validate_identity(action_id)
    replacement = _validate_metadata(metadata, field="metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        action["metadata"] = replacement
        actions[action_id] = action
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def load_action(action_id: str, *, root: Path) -> dict[str, Any] | None:
    """Load a durable action and its complete append-only attempt history."""

    _validate_identity(action_id)
    repo = resolve_root(root)
    with process_lock:
        action = _actions(_read_payload(repo)).get(action_id)
    return _copy(action) if action is not None else None


def record_repair_precondition(
    action_id: str,
    precondition_id: str,
    *,
    root: Path,
    state: PreconditionState = "pending",
    metadata: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Persist one mechanical prerequisite without creating another action."""

    _validate_identity(action_id)
    _validate_identity(precondition_id)
    _validate_choice(state, _PRECONDITION_STATES, field="precondition state")
    details = _validate_metadata(metadata, field="precondition metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        preconditions = {
            str(item["precondition_id"]): dict(item)
            for item in action.get("repair_preconditions", [])
            if isinstance(item, dict) and isinstance(item.get("precondition_id"), str)
        }
        current = preconditions.get(precondition_id)
        desired = {
            "precondition_id": precondition_id,
            "state": state,
            "metadata": details,
        }
        if (
            current is not None
            and {key: current.get(key) for key in desired} == desired
        ):
            return _copy(action)
        stamped = _iso(now)
        preconditions[precondition_id] = {**desired, "updated_at": stamped}
        action.update(
            repair_preconditions=list(preconditions.values()),
            updated_at=stamped,
        )
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def record_owner_decision(
    action_id: str,
    decision_id: str,
    *,
    root: Path,
    owner: DecisionOwner,
    metadata: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Hand a semantic issue to its owning team without creating a new action."""

    _validate_identity(action_id)
    _validate_identity(decision_id)
    _validate_choice(owner, _DECISION_OWNERS, field="decision owner")
    details = _validate_metadata(metadata, field="decision metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        if action.get("recovery_state") in {"completed", "blocked"}:
            raise ActionRecoveryError("terminal action cannot await an owner decision")
        decisions = {
            str(item["decision_id"]): dict(item)
            for item in action.get("owner_decisions", [])
            if isinstance(item, dict) and isinstance(item.get("decision_id"), str)
        }
        current = decisions.get(decision_id)
        if current is not None:
            if current.get("owner") != owner or current.get("metadata") != details:
                raise ActionRecoveryError(
                    f"decision identity {decision_id!r} already has different details"
                )
            return _copy(action)
        stamped = _iso(now)
        decisions[decision_id] = {
            "decision_id": decision_id,
            "action_id": action_id,
            "owner": owner,
            "state": "awaiting_resolution",
            "metadata": details,
            "created_at": stamped,
            "resolved_at": None,
            "resolution": None,
        }
        action.update(
            owner_decisions=list(decisions.values()),
            failure_classification="owner_decision",
            recovery_state="awaiting_owner_decision",
            updated_at=stamped,
        )
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def record_owner_resolution(
    action_id: str,
    decision_id: str,
    resolution_id: str,
    *,
    root: Path,
    metadata: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Resolve a decision and return the original persisted action to retryable."""

    _validate_identity(action_id)
    _validate_identity(decision_id)
    _validate_identity(resolution_id)
    details = _validate_metadata(metadata, field="resolution metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        decisions = [
            dict(item)
            for item in action.get("owner_decisions", [])
            if isinstance(item, dict)
        ]
        index = next(
            (
                i
                for i, item in enumerate(decisions)
                if item.get("decision_id") == decision_id
            ),
            None,
        )
        if index is None:
            raise ActionRecoveryError(f"owner decision not found: {decision_id}")
        decision = decisions[index]
        if decision.get("action_id") != action_id:
            raise ActionRecoveryError("owner decision belongs to a different action")
        resolution = {
            "resolution_id": resolution_id,
            "action_id": action_id,
            "decision_id": decision_id,
            "metadata": details,
        }
        if decision.get("state") == "resolved":
            if decision.get("resolution") != resolution:
                raise ActionRecoveryError(
                    "owner decision already has a different resolution"
                )
            return _copy(action)
        if decision.get("state") != "awaiting_resolution":
            raise ActionRecoveryError("unknown decision state")
        stamped = _iso(now)
        decisions[index] = {
            **decision,
            "state": "resolved",
            "resolution": resolution,
            "resolved_at": stamped,
        }
        unresolved = any(item.get("state") != "resolved" for item in decisions)
        action.update(
            owner_decisions=decisions,
            failure_classification="owner_decision" if unresolved else None,
            recovery_state="awaiting_owner_decision" if unresolved else "retryable",
            updated_at=stamped,
        )
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def start_attempt(
    action_id: str,
    *,
    root: Path,
    start_metadata: Mapping[str, Any] | None = None,
    recovery_state: RecoveryState = "running",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically append one attempt start and update the action state."""

    _validate_identity(action_id)
    if recovery_state not in _STATES:
        raise ActionRecoveryError(f"unknown recovery state: {recovery_state}")
    start = _validate_metadata(start_metadata, field="start metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        attempts = list(action.get("attempts") or [])
        if attempts and attempts[-1].get("outcome") is None:
            raise ActionRecoveryError("latest attempt has not been finalized")
        attempt_number = int(action.get("attempt_count") or 0) + 1
        if attempt_number > int(action.get("attempt_bound") or 0):
            raise ActionRecoveryError("configured attempt bound reached")
        started = _iso(now)
        attempts.append(
            {
                "attempt_number": attempt_number,
                "started_at": started,
                "start_metadata": start,
                "outcome": None,
                "classification": None,
                "completed_at": None,
                "completion_metadata": None,
            }
        )
        action["attempt_count"] = attempt_number
        action["recovery_state"] = recovery_state
        action["updated_at"] = started
        action["attempts"] = attempts
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


def finalize_attempt(
    action_id: str,
    attempt_number: int,
    *,
    root: Path,
    outcome: AttemptOutcome,
    classification: FailureClassification | None,
    recovery_state: RecoveryState,
    completion_metadata: Mapping[str, Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Atomically finalize the current attempt and record the resulting state.

    Earlier entries are never rewritten. The only mutable history is the
    currently open final entry, which is completed exactly once.
    """

    _validate_identity(action_id)
    if outcome not in _OUTCOMES:
        raise ActionRecoveryError(f"unknown attempt outcome: {outcome}")
    if classification is not None and classification not in _CLASSIFICATIONS:
        raise ActionRecoveryError(f"unknown failure classification: {classification}")
    if recovery_state not in _STATES:
        raise ActionRecoveryError(f"unknown recovery state: {recovery_state}")
    completion = _validate_metadata(completion_metadata, field="completion metadata")
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        attempts = list(action.get("attempts") or [])
        if (
            not attempts
            or int(attempts[-1].get("attempt_number") or 0) != attempt_number
        ):
            raise ActionRecoveryError("only the latest attempt may be finalized")
        attempt = dict(attempts[-1])
        if attempt.get("outcome") is not None:
            raise AttemptAlreadyFinalized(f"attempt {attempt_number}")
        finished = _iso(now)
        attempt.update(
            outcome=outcome,
            classification=classification,
            completed_at=finished,
            completion_metadata=completion,
        )
        attempts[-1] = attempt
        action["failure_classification"] = classification
        action["recovery_state"] = recovery_state
        action["updated_at"] = finished
        action["attempts"] = attempts
        action.pop("execution_claim", None)
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)


_RESUMABLE_STATES = frozenset(("pending", "retryable", "repaired"))
_FAILURE_STATES: dict[FailureClassification, RecoveryState] = {
    "deterministic_repair": "repaired",
    "transient_retry": "retryable",
    "owner_decision": "awaiting_owner_decision",
    "human_gate": "awaiting_human_gate",
    "terminal_blocker": "blocked",
}


def _claim_resume_attempt(
    action_id: str,
    *,
    root: Path,
    reclaim_running: bool = False,
    now: datetime | None = None,
) -> tuple[dict[str, Any], ActionContext] | None:
    """Atomically claim one eligible action and append its running attempt."""

    _validate_identity(action_id)
    repo = resolve_root(root)
    with process_lock:
        payload = _read_payload(repo)
        actions = _actions(payload)
        action = actions.get(action_id)
        if action is None:
            raise ActionNotFound(action_id)
        state = action.get("recovery_state")
        attempts = list(action.get("attempts") or [])
        if state == "running":
            if not reclaim_running:
                return None
            if not attempts or attempts[-1].get("outcome") is not None:
                raise ActionRecoveryError("running action has no open attempt")
            reclaimed_at = _iso(now)
            attempts[-1] = {
                **attempts[-1],
                "outcome": "cancelled",
                "classification": "transient_retry",
                "completed_at": reclaimed_at,
                "completion_metadata": {"reason": "reclaimed_after_restart"},
            }
            action["failure_classification"] = "transient_retry"
            action["recovery_state"] = "retryable"
        elif state not in _RESUMABLE_STATES:
            return None
        attempt_number = int(action.get("attempt_count") or 0) + 1
        if attempt_number > int(action.get("attempt_bound") or 0):
            action["failure_classification"] = "terminal_blocker"
            action["recovery_state"] = "blocked"
            action["updated_at"] = _iso(now)
            actions[action_id] = action
            payload["version"] = max(int(payload.get("version") or 1), 2)
            payload["actions"] = actions
            _write_payload(repo, payload)
            return None

        claimed_at = _iso(now)
        claim_id = uuid.uuid4().hex
        attempts.append(
            {
                "attempt_number": attempt_number,
                "started_at": claimed_at,
                "start_metadata": {"claim_id": claim_id},
                "outcome": None,
                "classification": None,
                "completed_at": None,
                "completion_metadata": None,
            }
        )
        action.update(
            attempt_count=attempt_number,
            recovery_state="running",
            updated_at=claimed_at,
            attempts=attempts,
            execution_claim={"claim_id": claim_id, "claimed_at": claimed_at},
        )
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action), ActionContext(
            action_id=action_id,
            attempt_number=attempt_number,
            idempotency_key=str(action.get("idempotency_key") or action_id),
        )


def _result_parts(
    result: ActionResult | Mapping[str, Any] | None,
) -> tuple[AttemptOutcome, FailureClassification | None, dict[str, Any]]:
    if result is None:
        return "succeeded", None, {}
    if isinstance(result, ActionResult):
        return (
            result.outcome,
            result.classification,
            _validate_metadata(result.metadata, field="result metadata"),
        )
    if isinstance(result, Mapping):
        outcome = result.get("outcome", "succeeded")
        classification = result.get("classification")
        if outcome not in _OUTCOMES:
            raise ActionRecoveryError(f"unknown attempt outcome: {outcome}")
        if classification is not None and classification not in _CLASSIFICATIONS:
            raise ActionRecoveryError(
                f"unknown failure classification: {classification}"
            )
        return (
            outcome,
            classification,
            _validate_metadata(result.get("metadata"), field="result metadata"),
        )
    raise ActionRecoveryError(
        "action executor must return ActionResult, a mapping, or None"
    )


def resume_action(
    action_id: str,
    *,
    root: Path,
    execute: Callable[[ActionContext], ActionResult | Mapping[str, Any] | None],
    reclaim_running: bool = False,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Claim and run one eligible action, returning its durable state.

    Claiming and attempt creation share one locked write, so concurrent calls
    observe the running action and never invoke a second downstream effect.
    A restarted supervisor may explicitly reclaim its unfinished running attempt;
    it receives the same idempotency key for the replacement effect.
    """

    claimed = _claim_resume_attempt(
        action_id, root=root, reclaim_running=reclaim_running, now=now
    )
    if claimed is None:
        action = load_action(action_id, root=root)
        if action is None:
            raise ActionNotFound(action_id)
        return action
    _, context = claimed
    try:
        outcome, classification, metadata = _result_parts(execute(context))
        if outcome == "succeeded":
            classification, state = None, "completed"
        else:
            classification = classification or "terminal_blocker"
            state = _FAILURE_STATES[classification]
    except ActionFailure as exc:
        outcome, classification, metadata = "failed", exc.classification, exc.metadata
        state = _FAILURE_STATES[classification]
    except BaseException as exc:
        outcome, classification, state = "failed", "terminal_blocker", "blocked"
        metadata = {"error_type": type(exc).__name__, "message": str(exc)}
    return finalize_attempt(
        action_id,
        context.attempt_number,
        root=root,
        outcome=outcome,
        classification=classification,
        recovery_state=state,
        completion_metadata=metadata,
        now=now,
    )
