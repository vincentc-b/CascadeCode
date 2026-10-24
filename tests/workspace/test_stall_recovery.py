"""Stall diagnostics and supervised recovery idempotency (feat_012_004 / task_012_004_003)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.task.execution import execution_view, mark_running, read_stall_disposition
from cascade.watchdog.events import read_events
from cascade.workspace.stall_cancellation import reset_stall_cancellation_for_tests
from cascade.workspace.stall_recovery import (
    TurnStallDiagnostic,
    handle_expired_stall_episode,
)
from cascade.workspace.turn_progress import (
    UsefulProgressEvidence,
    observe_turn_progress,
    reset_turn_progress_for_tests,
    set_turn_progress_clock_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_state() -> None:
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()
    yield
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()


def _expired_observation(turn_id: str) -> object:
    now = {"t": 0.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    evidence = UsefulProgressEvidence(provider_events=1)
    observe_turn_progress(turn_id, evidence=evidence, deadline_seconds=1.0)
    now["t"] = 5.0
    return observe_turn_progress(turn_id, evidence=evidence, deadline_seconds=1.0)


def test_emits_one_diagnostic_and_schedules_one_recovery(tmp_path: Path) -> None:
    task_id = "task_012_004_003"
    turn_id = "turn-recovery-a"
    mark_running(task_id, root=tmp_path)
    expired = _expired_observation(turn_id)
    assert expired.state == "no_progress_deadline_exceeded"

    first = handle_expired_stall_episode(
        expired,
        task_id=task_id,
        provider="cursor",
        model_id="composer-2.5",
        root=tmp_path,
    )
    assert first is not None
    assert first.disposition.diagnostic_recorded
    assert first.disposition.recovery_scheduled
    assert first.recovery_event_appended is True
    assert first.diagnostic.task_id == task_id
    assert first.diagnostic.turn_id == turn_id
    assert first.diagnostic.provider == "cursor"

    stored = read_stall_disposition(task_id, expired.episode_signature, root=tmp_path)
    assert stored is not None
    assert stored["diagnostic_recorded"] is True
    assert stored["recovery_scheduled"] is True
    assert execution_view(task_id, root=tmp_path)["phase"] == "queued"

    events, _ = read_events(task_id, 0, root=tmp_path)
    recovery_events = [event for event in events if event.type == "TaskStallRecoveryScheduled"]
    assert len(recovery_events) == 1
    assert recovery_events[0].payload["episode_signature"] == expired.episode_signature


def test_repeated_handle_is_idempotent(tmp_path: Path) -> None:
    task_id = "task_012_004_003"
    turn_id = "turn-recovery-b"
    mark_running(task_id, root=tmp_path)
    expired = _expired_observation(turn_id)

    first = handle_expired_stall_episode(
        expired,
        task_id=task_id,
        provider="cursor",
        model_id=None,
        root=tmp_path,
    )
    second = handle_expired_stall_episode(
        expired,
        task_id=task_id,
        provider="cursor",
        model_id=None,
        root=tmp_path,
    )
    assert first is not None and second is not None
    assert first.diagnostic.as_safe_dict() == second.diagnostic.as_safe_dict()
    assert second.recovery_event_appended is False

    events, _ = read_events(task_id, 0, root=tmp_path)
    recovery_events = [event for event in events if event.type == "TaskStallRecoveryScheduled"]
    assert len(recovery_events) == 1


def test_diagnostic_minimizes_sensitive_fields(tmp_path: Path) -> None:
    task_id = "task_012_004_003"
    expired = _expired_observation("turn-recovery-c")
    mark_running(task_id, root=tmp_path)
    result = handle_expired_stall_episode(
        expired,
        task_id=task_id,
        provider="cursor",
        model_id="composer-2.5",
        root=tmp_path,
    )
    assert result is not None
    payload = result.diagnostic.as_safe_dict()
    encoded = json.dumps(payload)
    for forbidden in ("prompt", "credential", "api_key", "model_output", "instruction"):
        assert forbidden not in encoded.lower()
    assert "messages" not in payload
    assert "content" not in payload


def test_new_episode_allows_new_recovery(tmp_path: Path) -> None:
    task_id = "task_012_004_003"
    turn_id = "turn-recovery-d"
    mark_running(task_id, root=tmp_path)

    now = {"t": 0.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    base = UsefulProgressEvidence(provider_events=1)
    observe_turn_progress(turn_id, evidence=base, deadline_seconds=1.0)
    now["t"] = 5.0
    first_expired = observe_turn_progress(turn_id, evidence=base, deadline_seconds=1.0)

    first = handle_expired_stall_episode(
        first_expired,
        task_id=task_id,
        provider="cursor",
        model_id=None,
        root=tmp_path,
    )
    assert first is not None

    advanced = UsefulProgressEvidence(provider_events=2)
    now["t"] = 6.0
    observe_turn_progress(turn_id, evidence=advanced, deadline_seconds=1.0)
    now["t"] = 12.0
    second_expired = observe_turn_progress(turn_id, evidence=advanced, deadline_seconds=1.0)
    assert second_expired.episode_signature != first_expired.episode_signature

    mark_running(task_id, root=tmp_path)
    second = handle_expired_stall_episode(
        second_expired,
        task_id=task_id,
        provider="cursor",
        model_id=None,
        root=tmp_path,
    )
    assert second is not None
    assert second.recovery_event_appended is True

    events, _ = read_events(task_id, 0, root=tmp_path)
    recovery_events = [event for event in events if event.type == "TaskStallRecoveryScheduled"]
    assert len(recovery_events) == 2
    signatures = {event.payload["episode_signature"] for event in recovery_events}
    assert signatures == {first_expired.episode_signature, second_expired.episode_signature}


def test_turn_stall_diagnostic_rejects_forbidden_keys() -> None:
    diagnostic = TurnStallDiagnostic(
        task_id="task_x",
        turn_id="turn_x",
        provider="cursor",
        model_id=None,
        episode_signature="sig",
        last_progress_kind="provider_event",
        last_progress_at_monotonic=1.0,
        stalled_for_seconds=30.0,
        cancellation_termination="turn_not_live",
        cancellation_process_tree_pid=None,
        cancellation_force_kill_applied=False,
        preserved_checkpoint_present=False,
        preserved_worktree_present=False,
        preserved_checkpoint_fingerprint=None,
        preserved_worktree_fingerprint=None,
    )
    payload = diagnostic.as_safe_dict()
    payload["prompt"] = "secret"
    with pytest.raises(ValueError):
        from cascade.workspace import stall_recovery as module

        module._assert_diagnostic_redaction(payload)
