from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.task.action_recovery import (
    ActionRecoveryError,
    AttemptAlreadyFinalized,
    create_or_load_action,
    finalize_attempt,
    load_action,
    start_attempt,
)
from cascade.task.execution import mark_queued
from tests.support import make_repo


def test_action_identity_attempt_history_and_restart_durability(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    action = create_or_load_action(
        "task_001:swe_turn",
        "swe_turn",
        root=root,
        attempt_bound=2,
        metadata={"task_id": "task_001"},
        now=started,
    )
    assert action["attempt_count"] == 0
    assert create_or_load_action(
        "task_001:swe_turn", "swe_turn", root=root, attempt_bound=9
    ) == action

    started_action = start_attempt(
        "task_001:swe_turn", root=root, start_metadata={"provider": "codex"}, now=started
    )
    finalized = finalize_attempt(
        "task_001:swe_turn",
        1,
        root=root,
        outcome="failed",
        classification="transient_retry",
        recovery_state="retryable",
        completion_metadata={"reason": "temporary_failure"},
        now=started,
    )

    assert started_action["attempts"][0]["outcome"] is None
    assert finalized["attempt_count"] == 1
    assert finalized["failure_classification"] == "transient_retry"
    assert finalized["attempts"] == [
        {
            "attempt_number": 1,
            "started_at": started.isoformat(),
            "start_metadata": {"provider": "codex"},
            "outcome": "failed",
            "classification": "transient_retry",
            "completed_at": started.isoformat(),
            "completion_metadata": {"reason": "temporary_failure"},
        }
    ]

    # A fresh import-style load crosses the normal file-backed restart boundary.
    reloaded = load_action("task_001:swe_turn", root=root)
    assert reloaded == finalized


def test_action_transitions_are_atomic_and_history_is_append_only(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_recovery", root=root, attempt_bound=2)
    start_attempt("action", root=root, start_metadata={"turn": 1})
    before = load_action("action", root=root)

    import cascade.task.action_recovery as recovery

    def fail_write(_root, _payload) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(recovery, "_write_payload", fail_write)
    with pytest.raises(OSError, match="disk full"):
        finalize_attempt(
            "action",
            1,
            root=root,
            outcome="failed",
            classification="deterministic_repair",
            recovery_state="repaired",
        )
    assert load_action("action", root=root) == before

    monkeypatch.undo()
    finalize_attempt(
        "action",
        1,
        root=root,
        outcome="failed",
        classification="deterministic_repair",
        recovery_state="repaired",
    )
    with pytest.raises(AttemptAlreadyFinalized):
        finalize_attempt(
            "action",
            1,
            root=root,
            outcome="failed",
            classification="terminal_blocker",
            recovery_state="blocked",
        )
    with pytest.raises(ActionRecoveryError, match="only the latest"):
        finalize_attempt(
            "action",
            0,
            root=root,
            outcome="failed",
            classification="terminal_blocker",
            recovery_state="blocked",
        )


def test_execution_updates_preserve_action_records(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_recovery", root=root, attempt_bound=1)
    mark_queued("task_001", root=root)

    action = load_action("action", root=root)
    assert action is not None
    assert action["action_kind"] == "task_recovery"
