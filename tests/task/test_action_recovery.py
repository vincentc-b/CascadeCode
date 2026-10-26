from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

import pytest

from cascade.task.action_recovery import (
    ActionRecoveryError,
    AttemptAlreadyFinalized,
    ActionFailure,
    create_or_load_action,
    finalize_attempt,
    load_action,
    resume_action,
    record_owner_decision,
    record_owner_resolution,
    record_repair_precondition,
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


def test_resume_serializes_concurrent_calls_and_supplies_stable_idempotency_key(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_turn", root=root, attempt_bound=2)
    started = Event()
    release = Event()
    effect_keys: list[str] = []

    def execute(context) -> None:
        effect_keys.append(context.idempotency_key)
        started.set()
        assert release.wait(timeout=2)

    worker = Thread(target=lambda: resume_action("action", root=root, execute=execute))
    worker.start()
    assert started.wait(timeout=2)

    # This call sees the persisted running claim rather than emitting another turn.
    concurrent = resume_action(
        "action", root=root, execute=lambda _context: pytest.fail("duplicate effect")
    )
    assert concurrent["recovery_state"] == "running"
    release.set()
    worker.join(timeout=2)

    completed = load_action("action", root=root)
    assert completed is not None
    assert completed["recovery_state"] == "completed"
    assert completed["attempt_count"] == 1
    assert effect_keys == ["action"]


def test_resume_routes_failures_and_stops_when_attempt_budget_is_exhausted(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_turn", root=root, attempt_bound=1)

    retryable = resume_action(
        "action",
        root=root,
        execute=lambda _context: (_ for _ in ()).throw(
            ActionFailure("transient_retry", metadata={"reason": "network"})
        ),
    )
    assert retryable["recovery_state"] == "retryable"
    assert retryable["attempts"][-1]["completion_metadata"] == {"reason": "network"}

    bounded = resume_action("action", root=root, execute=lambda _context: None)
    assert bounded["recovery_state"] == "blocked"
    assert bounded["failure_classification"] == "terminal_blocker"
    assert bounded["attempt_count"] == 1



def test_resume_can_reclaim_an_unfinished_attempt_after_restart(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_turn", root=root, attempt_bound=2)
    start_attempt("action", root=root)

    resumed = resume_action(
        "action",
        root=root,
        reclaim_running=True,
        execute=lambda context: {"metadata": {"key": context.idempotency_key}},
    )

    assert resumed["recovery_state"] == "completed"
    assert resumed["attempt_count"] == 2
    assert resumed["attempts"][0]["outcome"] == "cancelled"
    assert resumed["attempts"][0]["classification"] == "transient_retry"
    assert resumed["attempts"][1]["completion_metadata"] == {"key": "action"}


def test_restart_and_concurrent_retry_preserve_one_logical_lifecycle_effect(
    tmp_path: Path,
) -> None:
    """A recovered retry has one durable history and emits each effect once."""

    root = make_repo(tmp_path, git=False)
    action_id = "task_001:publish_completion"
    create_or_load_action(action_id, "publish_completion", root=root, attempt_bound=2)

    first_attempt = resume_action(
        action_id,
        root=root,
        execute=lambda _context: (_ for _ in ()).throw(
            ActionFailure("transient_retry", metadata={"reason": "supervisor_lost"})
        ),
    )
    assert first_attempt["recovery_state"] == "retryable"
    assert first_attempt["failure_classification"] == "transient_retry"
    assert first_attempt["attempt_count"] == 1

    # Loading from the sidecar models the new supervisor's process after restart.
    after_restart = load_action(action_id, root=root)
    assert after_restart is not None
    assert after_restart["attempts"] == first_attempt["attempts"]

    started = Event()
    release = Event()
    downstream_effects = {name: [] for name in ("team_turn", "review", "merge", "completion")}
    worker_result: list[dict] = []

    def publish(context) -> dict:
        for effects in downstream_effects.values():
            effects.append(context.idempotency_key)
        started.set()
        assert release.wait(timeout=2)
        return {"metadata": {"completion_event": context.idempotency_key}}

    worker = Thread(
        target=lambda: worker_result.append(
            resume_action(action_id, root=root, execute=publish)
        )
    )
    worker.start()
    assert started.wait(timeout=2)

    # A second retry request observes the persisted claim and cannot re-publish.
    concurrent_retry = resume_action(
        action_id,
        root=root,
        execute=lambda _context: pytest.fail("duplicate lifecycle effect"),
    )
    assert concurrent_retry["recovery_state"] == "running"
    release.set()
    worker.join(timeout=2)
    assert not worker.is_alive()

    completed = worker_result[0]
    assert completed["recovery_state"] == "completed"
    assert completed["attempt_count"] == completed["attempt_bound"] == 2
    assert [attempt["outcome"] for attempt in completed["attempts"]] == ["failed", "succeeded"]
    assert [attempt["classification"] for attempt in completed["attempts"]] == [
        "transient_retry",
        None,
    ]
    assert all(effects == [action_id] for effects in downstream_effects.values())

    # Repeated retry requests after completion are idempotent and add no history or effects.
    assert resume_action(
        action_id,
        root=root,
        execute=lambda _context: pytest.fail("completed action must not execute"),
    ) == completed
    assert load_action(action_id, root=root) == completed



def test_supervisor_preconditions_and_owner_resolution_resume_same_action(
    tmp_path: Path,
) -> None:
    """Mechanical repair and semantic handoff share one durable action identity."""

    root = make_repo(tmp_path, git=False)
    action_id = "task_001:queued_merge"
    create_or_load_action(action_id, "queued_merge", root=root, attempt_bound=2)

    pending = record_repair_precondition(
        action_id,
        "integration_checkout",
        root=root,
        metadata={"feature_id": "feat_001", "branch": "epic/epic_001"},
    )
    assert pending["repair_preconditions"][0]["state"] == "pending"
    assert record_repair_precondition(
        action_id,
        "integration_checkout",
        root=root,
        metadata={"feature_id": "feat_001", "branch": "epic/epic_001"},
    ) == pending

    repaired = record_repair_precondition(
        action_id,
        "integration_checkout",
        root=root,
        state="repaired",
        metadata={"feature_id": "feat_001", "branch": "epic/epic_001"},
    )
    assert repaired["repair_preconditions"][0]["state"] == "repaired"

    handed_off = record_owner_decision(
        action_id,
        "merge-conflict:source-target",
        root=root,
        owner="feature_team",
        metadata={"conflict_paths": ["cascade/task/action_recovery.py"]},
    )
    assert handed_off["recovery_state"] == "awaiting_owner_decision"
    assert resume_action(
        action_id, root=root, execute=lambda _context: pytest.fail("must await owner")
    ) == handed_off

    resolved = record_owner_resolution(
        action_id,
        "merge-conflict:source-target",
        "resolution:feat_001:42",
        root=root,
        metadata={"strategy": "feature-approved"},
    )
    decision = resolved["owner_decisions"][0]
    # A fresh supervisor process reads the same durable record before resuming it.
    resolved = load_action(action_id, root=root)
    assert resolved is not None
    assert resolved["action_id"] == action_id
    assert resolved["recovery_state"] == "retryable"
    assert decision["resolution"]["action_id"] == action_id
    assert decision["resolution"]["decision_id"] == decision["decision_id"]
    assert record_owner_resolution(
        action_id,
        "merge-conflict:source-target",
        "resolution:feat_001:42",
        root=root,
        metadata={"strategy": "feature-approved"},
    ) == resolved

    resumed = resume_action(action_id, root=root, execute=lambda context: {
        "metadata": {"resumed_action": context.action_id}
    })
    assert resumed["recovery_state"] == "completed"
    assert resumed["attempts"][-1]["completion_metadata"] == {"resumed_action": action_id}
