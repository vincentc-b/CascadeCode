"""Episode-keyed stall diagnostics and supervised recovery (feat_012_004 / task_012_004_003)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cascade.task.execution import (
    mark_stall_recovery_queued,
    read_stall_disposition,
    write_stall_disposition,
)
from cascade.workspace.stall_cancellation import (
    CancellationOutcome,
    cancel_stalled_turn,
)
from cascade.workspace.turn_progress import TurnProgressObservation
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event

_FORBIDDEN_DIAGNOSTIC_KEYS = frozenset(
    {
        "prompt",
        "prompts",
        "credential",
        "credentials",
        "api_key",
        "token",
        "secret",
        "model_output",
        "output",
        "instruction",
        "messages",
        "content",
    }
)
_STALL_RECOVERY_EVENT = "TaskStallRecoveryScheduled"


@dataclass(frozen=True)
class RecoveryDisposition:
    episode_signature: str
    diagnostic_recorded: bool
    recovery_scheduled: bool


@dataclass(frozen=True)
class TurnStallDiagnostic:
    task_id: str
    turn_id: str
    provider: str
    model_id: str | None
    episode_signature: str
    last_progress_kind: str | None
    last_progress_at_monotonic: float | None
    stalled_for_seconds: float | None
    cancellation_termination: str
    cancellation_process_tree_pid: int | None
    cancellation_force_kill_applied: bool
    preserved_checkpoint_present: bool
    preserved_worktree_present: bool
    preserved_checkpoint_fingerprint: tuple[int, int] | None
    preserved_worktree_fingerprint: str | None

    def as_safe_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "task_id": self.task_id,
            "turn_id": self.turn_id,
            "provider": self.provider,
            "model_id": self.model_id,
            "episode_signature": self.episode_signature,
            "last_progress_kind": self.last_progress_kind,
            "last_progress_at_monotonic": self.last_progress_at_monotonic,
            "stalled_for_seconds": self.stalled_for_seconds,
            "cancellation": {
                "termination": self.cancellation_termination,
                "process_tree_pid": self.cancellation_process_tree_pid,
                "force_kill_applied": self.cancellation_force_kill_applied,
            },
            "preserved_work": {
                "checkpoint_present": self.preserved_checkpoint_present,
                "worktree_present": self.preserved_worktree_present,
                "checkpoint_fingerprint": self.preserved_checkpoint_fingerprint,
                "worktree_fingerprint": self.preserved_worktree_fingerprint,
            },
        }
        _assert_diagnostic_redaction(payload)
        return payload


@dataclass(frozen=True)
class StallRecoveryResult:
    diagnostic: TurnStallDiagnostic
    disposition: RecoveryDisposition
    cancellation: CancellationOutcome | None
    recovery_event_appended: bool


def reset_stall_recovery_for_tests() -> None:
    """No in-process state; tests reset execution sidecars directly."""


def handle_expired_stall_episode(
    observation: TurnProgressObservation,
    *,
    task_id: str,
    provider: str,
    model_id: str | None = None,
    root: Path,
    grace_seconds: float | None = None,
) -> StallRecoveryResult | None:
    """Cancel if needed, emit one durable diagnostic, and schedule at most one recovery."""

    if observation.state != "no_progress_deadline_exceeded":
        return None

    episode_signature = observation.episode_signature
    repo = Path(root).resolve()
    existing = read_stall_disposition(task_id, episode_signature, root=repo)
    if existing and existing.get("diagnostic_recorded") and existing.get("recovery_scheduled"):
        return _result_from_disposition(
            task_id,
            episode_signature,
            existing,
            provider=provider,
            model_id=model_id,
            observation=observation,
            recovery_event_appended=False,
        )

    outcome = cancel_stalled_turn(
        observation,
        task_id=task_id,
        root=repo,
        grace_seconds=grace_seconds,
    )
    if outcome is None and existing is None:
        return None

    cancellation_row = _cancellation_row(outcome, existing)
    if cancellation_row is None:
        return None

    if outcome is not None and not (existing and existing.get("cancellation")):
        write_stall_disposition(
            task_id,
            episode_signature,
            {"turn_id": observation.turn_id, "cancellation": cancellation_row},
            root=repo,
        )
        existing = read_stall_disposition(task_id, episode_signature, root=repo)

    diagnostic = _build_diagnostic(
        task_id=task_id,
        provider=provider,
        model_id=model_id,
        observation=observation,
        cancellation_row=cancellation_row,
    )
    diagnostic_recorded = bool(existing and existing.get("diagnostic_recorded"))
    recovery_scheduled = bool(existing and existing.get("recovery_scheduled"))
    recovery_event_appended = False

    if not diagnostic_recorded:
        write_stall_disposition(
            task_id,
            episode_signature,
            {
                "turn_id": observation.turn_id,
                "diagnostic_recorded": True,
                "diagnostic": diagnostic.as_safe_dict(),
                "cancellation": cancellation_row,
            },
            root=repo,
        )
        diagnostic_recorded = True

    if not recovery_scheduled:
        mark_stall_recovery_queued(task_id, root=repo)
        recovery_event_appended = _append_recovery_event(
            task_id,
            episode_signature,
            root=repo,
        )
        write_stall_disposition(
            task_id,
            episode_signature,
            {"recovery_scheduled": True},
            root=repo,
        )
        recovery_scheduled = True

    disposition = RecoveryDisposition(
        episode_signature=episode_signature,
        diagnostic_recorded=diagnostic_recorded,
        recovery_scheduled=recovery_scheduled,
    )
    return StallRecoveryResult(
        diagnostic=diagnostic,
        disposition=disposition,
        cancellation=outcome,
        recovery_event_appended=recovery_event_appended,
    )


def _result_from_disposition(
    task_id: str,
    episode_signature: str,
    row: dict[str, Any],
    *,
    provider: str,
    model_id: str | None,
    observation: TurnProgressObservation,
    recovery_event_appended: bool,
) -> StallRecoveryResult:
    diagnostic_payload = row.get("diagnostic")
    if isinstance(diagnostic_payload, dict):
        diagnostic = _diagnostic_from_dict(diagnostic_payload)
    else:
        cancellation_row = row.get("cancellation")
        if not isinstance(cancellation_row, dict):
            cancellation_row = {}
        diagnostic = _build_diagnostic(
            task_id=task_id,
            provider=provider,
            model_id=model_id,
            observation=observation,
            cancellation_row=cancellation_row,
        )
    disposition = RecoveryDisposition(
        episode_signature=episode_signature,
        diagnostic_recorded=bool(row.get("diagnostic_recorded")),
        recovery_scheduled=bool(row.get("recovery_scheduled")),
    )
    return StallRecoveryResult(
        diagnostic=diagnostic,
        disposition=disposition,
        cancellation=None,
        recovery_event_appended=recovery_event_appended,
    )


def _build_diagnostic(
    *,
    task_id: str,
    provider: str,
    model_id: str | None,
    observation: TurnProgressObservation,
    cancellation_row: dict[str, Any],
) -> TurnStallDiagnostic:
    preserved = cancellation_row.get("preserved")
    preserved_row = preserved if isinstance(preserved, dict) else {}
    return TurnStallDiagnostic(
        task_id=task_id,
        turn_id=observation.turn_id,
        provider=provider,
        model_id=model_id,
        episode_signature=observation.episode_signature,
        last_progress_kind=observation.last_progress_kind,
        last_progress_at_monotonic=observation.last_progress_at_monotonic,
        stalled_for_seconds=observation.stalled_for_seconds,
        cancellation_termination=str(cancellation_row.get("termination") or "not_required"),
        cancellation_process_tree_pid=_optional_int(cancellation_row.get("process_tree_pid")),
        cancellation_force_kill_applied=bool(cancellation_row.get("force_kill_applied")),
        preserved_checkpoint_present=bool(preserved_row.get("checkpoint_present")),
        preserved_worktree_present=bool(preserved_row.get("worktree_present")),
        preserved_checkpoint_fingerprint=_optional_fingerprint(
            preserved_row.get("checkpoint_fingerprint")
        ),
        preserved_worktree_fingerprint=_optional_str(preserved_row.get("worktree_fingerprint")),
    )


def _diagnostic_from_dict(payload: dict[str, Any]) -> TurnStallDiagnostic:
    cancellation = payload.get("cancellation")
    cancellation_row = cancellation if isinstance(cancellation, dict) else {}
    preserved = payload.get("preserved_work")
    preserved_row = preserved if isinstance(preserved, dict) else {}
    return TurnStallDiagnostic(
        task_id=str(payload["task_id"]),
        turn_id=str(payload["turn_id"]),
        provider=str(payload["provider"]),
        model_id=_optional_str(payload.get("model_id")),
        episode_signature=str(payload["episode_signature"]),
        last_progress_kind=_optional_str(payload.get("last_progress_kind")),
        last_progress_at_monotonic=_optional_float(payload.get("last_progress_at_monotonic")),
        stalled_for_seconds=_optional_float(payload.get("stalled_for_seconds")),
        cancellation_termination=str(cancellation_row.get("termination") or "not_required"),
        cancellation_process_tree_pid=_optional_int(cancellation_row.get("process_tree_pid")),
        cancellation_force_kill_applied=bool(cancellation_row.get("force_kill_applied")),
        preserved_checkpoint_present=bool(preserved_row.get("checkpoint_present")),
        preserved_worktree_present=bool(preserved_row.get("worktree_present")),
        preserved_checkpoint_fingerprint=_optional_fingerprint(
            preserved_row.get("checkpoint_fingerprint")
        ),
        preserved_worktree_fingerprint=_optional_str(preserved_row.get("worktree_fingerprint")),
    )


def _cancellation_row(
    outcome: CancellationOutcome | None, existing: dict[str, Any] | None
) -> dict[str, Any] | None:
    if outcome is not None:
        return {
            "termination": outcome.termination,
            "process_tree_pid": outcome.process_tree_pid,
            "force_kill_applied": outcome.force_kill_applied,
            "preserved": {
                "checkpoint_present": outcome.preserved.checkpoint_present,
                "worktree_present": outcome.preserved.worktree_present,
                "checkpoint_fingerprint": outcome.preserved.checkpoint_fingerprint,
                "worktree_fingerprint": outcome.preserved.worktree_fingerprint,
            },
        }
    if existing is None:
        return None
    row = existing.get("cancellation")
    return dict(row) if isinstance(row, dict) else None


def _append_recovery_event(task_id: str, episode_signature: str, *, root: Path) -> bool:
    events, _offset = read_events(task_id, 0, root=root)
    for event in events:
        if event.type != _STALL_RECOVERY_EVENT:
            continue
        payload = event.payload
        if payload.get("episode_signature") == episode_signature:
            return False
    append_event(
        task_id,
        Event(
            type=_STALL_RECOVERY_EVENT,
            ts=datetime.now(timezone.utc),
            payload={
                "task_id": task_id,
                "episode_signature": episode_signature,
                "reason": "in_flight_turn_no_progress",
            },
            dest=task_id,
        ),
        root=root,
    )
    return True


def _assert_diagnostic_redaction(payload: dict[str, Any]) -> None:
    for key in payload:
        if key.lower() in _FORBIDDEN_DIAGNOSTIC_KEYS:
            raise ValueError(f"diagnostic must not include {key!r}")
    for value in payload.values():
        if isinstance(value, dict):
            _assert_diagnostic_redaction(value)


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _optional_fingerprint(value: object) -> tuple[int, int] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    return (int(value[0]), int(value[1]))
