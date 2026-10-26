"""Durable recovery records for logical lifecycle actions.

Records live in the existing lifecycle sidecar (.cascade/executions.json), under
an additive actions key. This keeps recovery on the same locking and atomic
replacement boundary as task execution health.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, Mapping

from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock

FailureClassification = Literal[
    "deterministic_repair", "transient_retry", "owner_decision", "human_gate", "terminal_blocker"
]
RecoveryState = Literal[
    "pending", "running", "retryable", "repaired", "awaiting_owner_decision",
    "awaiting_human_gate", "blocked", "completed",
]
AttemptOutcome = Literal["succeeded", "failed", "cancelled"]

_CLASSIFICATIONS = frozenset(FailureClassification.__args__)
_STATES = frozenset(RecoveryState.__args__)
_OUTCOMES = frozenset(AttemptOutcome.__args__)


class ActionRecoveryError(ValueError):
    """An action recovery transition cannot be recorded."""


class ActionNotFound(ActionRecoveryError):
    """The requested durable action does not exist."""


class AttemptAlreadyFinalized(ActionRecoveryError):
    """An attempt outcome is immutable once it has been finalized."""


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
    return {str(identity): dict(action) for identity, action in actions.items() if isinstance(action, dict)}


def _validate_identity(identity: str) -> None:
    if not identity or identity.strip() != identity:
        raise ActionRecoveryError("action identity must be a nonempty stable string")


def _validate_metadata(metadata: Mapping[str, Any] | None, *, field: str) -> dict[str, Any]:
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


def create_or_load_action(
    action_id: str,
    action_kind: str,
    *,
    root: Path,
    attempt_bound: int,
    recovery_state: RecoveryState = "pending",
    failure_classification: FailureClassification | None = None,
    metadata: Mapping[str, Any] | None = None,
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
    if failure_classification is not None and failure_classification not in _CLASSIFICATIONS:
        raise ActionRecoveryError(f"unknown failure classification: {failure_classification}")
    initial_metadata = _validate_metadata(metadata, field="metadata")
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
            "created_at": created,
            "updated_at": created,
            "attempts": [],
        }
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
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
        if not attempts or int(attempts[-1].get("attempt_number") or 0) != attempt_number:
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
        actions[action_id] = action
        payload["version"] = max(int(payload.get("version") or 1), 2)
        payload["actions"] = actions
        _write_payload(repo, payload)
        return _copy(action)
