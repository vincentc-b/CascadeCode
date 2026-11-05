import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

import pytest

from cascade.task.action_recovery import (
    ActionRecoveryError,
    AttemptAlreadyFinalized,
    ActionFailure,
    capture_and_route_action_failure,
    create_or_load_action,
    finalize_attempt,
    load_action,
    resume_action,
    record_owner_decision,
    record_owner_resolution,
    record_repair_precondition,
    record_action_checkpoint,
    reconcile_action,
    repair_action,
    start_attempt,
    update_recovery_record,
)
from cascade.task.execution import mark_queued
from cascade.watchdog.events import read_events
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
    assert (
        create_or_load_action(
            "task_001:swe_turn", "swe_turn", root=root, attempt_bound=9
        )
        == action
    )

    started_action = start_attempt(
        "task_001:swe_turn",
        root=root,
        start_metadata={"provider": "codex"},
        now=started,
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


def test_action_transitions_are_atomic_and_history_is_append_only(
    tmp_path: Path, monkeypatch
) -> None:
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


def test_recovery_record_preserves_branch_action_identity_and_context(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = create_or_load_action(
        "feat_001:merge_to_epic",
        "feature_merge",
        root=root,
        attempt_bound=2,
        lifecycle_state="ready_for_merge",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"source_sha": "source", "target_sha": "target"},
        provenance={"requested_by": "operator", "approval_id": "approval-7"},
        retry_marker={"attempt": 0},
        routing_marker={"queue": "feature-lifecycle"},
        human_blocker={
            "code": "review_required",
            "message": "The implementation review is still pending.",
            "required_action": "Approve review approval-7.",
        },
    )

    assert action["recovery"] == {
        "original_action": {
            "action_id": "feat_001:merge_to_epic",
            "action_kind": "feature_merge",
        },
        "lifecycle_state": "ready_for_merge",
        "owning_team": {"kind": "feature_team", "work_id": "feat_001"},
        "evidence": {"source_sha": "source", "target_sha": "target"},
        "provenance": {"requested_by": "operator", "approval_id": "approval-7"},
        "retry_marker": {"attempt": 0},
        "routing_marker": {"queue": "feature-lifecycle"},
        "human_blocker": {
            "code": "review_required",
            "message": "The implementation review is still pending.",
            "required_action": "Approve review approval-7.",
        },
    }
    # Restart reads the same context without reconstructing the original action.
    assert load_action("feat_001:merge_to_epic", root=root) == action


def test_recovery_record_updates_do_not_replace_user_metadata_or_legacy_records(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        "epic_001:close",
        "epic_close",
        root=root,
        attempt_bound=2,
        metadata={"user_file": "keep", "approval": "approved"},
    )
    # Simulate an epic_026 record written before the additive recovery field.
    path = root / ".cascade" / "executions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"]["epic_001:close"].pop("recovery")
    path.write_text(json.dumps(payload), encoding="utf-8")
    updated = update_recovery_record(
        "epic_001:close",
        root=root,
        lifecycle_state="awaiting_closeout",
        owning_team={"kind": "epic_team", "work_id": "epic_001"},
        routing_marker={"investigation_id": "epic_001:close"},
        human_blocker={
            "code": "dirty_operator_checkout",
            "message": "Operator checkout has unrelated changes.",
            "required_action": "Use the isolated closeout review.",
        },
    )
    assert updated["metadata"] == {"user_file": "keep", "approval": "approved"}
    assert updated["recovery"]["original_action"] == {
        "action_id": "epic_001:close",
        "action_kind": "epic_close",
    }
    assert updated["recovery"]["routing_marker"] == {
        "investigation_id": "epic_001:close"
    }

    cleared = update_recovery_record(
        "epic_001:close",
        root=root,
        retry_marker={"resume_token": "same-action"},
        clear_human_blocker=True,
    )
    assert cleared["recovery"]["human_blocker"] is None
    assert cleared["recovery"]["routing_marker"] == {
        "investigation_id": "epic_001:close"
    }
    assert cleared["recovery"]["retry_marker"] == {"resume_token": "same-action"}


def test_first_branch_action_failure_routes_once_to_feature_team_and_survives_restart(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    captured = capture_and_route_action_failure(
        "task_001:merge_to_feature",
        "task_merge",
        affected_work_id="task_001",
        intended_target_ref="refs/heads/feat/feat_001",
        root=root,
        failure_code="branch_conflict",
        safe_summary="Task branch conflicts with its Feature target.",
        conflicting_paths=["cascade/task/action_recovery.py"],
        evidence={"source_sha": "a", "target_sha": "b"},
    )

    marker = captured["recovery"]["routing_marker"]
    assert captured["recovery_state"] == "awaiting_owner_decision"
    assert captured["recovery"]["owning_team"] == {
        "kind": "feature_team",
        "work_id": "feat_001",
    }
    assert marker["status"] == "enqueued"
    events, _ = read_events("feat_001", 0, root=root)
    assert [event.payload["investigation_id"] for event in events] == [
        marker["investigation_id"]
    ]

    # Repeated clicks and a fresh process use the episode marker rather than
    # producing another normal-team queue item.
    assert (
        capture_and_route_action_failure(
            "task_001:merge_to_feature",
            "task_merge",
            affected_work_id="task_001",
            intended_target_ref="feat/feat_001",
            root=root,
            failure_code="branch_conflict",
            safe_summary="Task branch conflicts with its Feature target.",
        )
        == captured
    )
    events, _ = read_events("feat_001", 0, root=root)
    assert len(events) == 1
    assert load_action("task_001:merge_to_feature", root=root) == captured


def test_branch_action_failure_uses_epic_target_or_blocks_ambiguous_owner(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    epic = capture_and_route_action_failure(
        "feat_001:merge_to_epic",
        "feature_merge",
        affected_work_id="feat_001",
        intended_target_ref="epic/epic_001",
        root=root,
        failure_code="permission_denied",
        safe_summary="The Epic integration checkout rejected the merge.",
    )
    assert epic["recovery"]["owning_team"] == {
        "kind": "epic_team",
        "work_id": "epic_001",
    }
    events, _ = read_events("epic_001", 0, root=root)
    assert len(events) == 1

    blocked = capture_and_route_action_failure(
        "unknown:update",
        "branch_update",
        affected_work_id="unknown",
        intended_target_ref=None,
        root=root,
        failure_code="checkout_missing",
        safe_summary="The integration checkout is unavailable.",
    )
    assert blocked["recovery_state"] == "blocked"
    assert blocked["recovery"]["routing_marker"]["reason"] == "ambiguous_owner"


@pytest.mark.parametrize(
    ("action_id", "action_kind", "affected_work_id", "target_ref", "owner"),
    (
        (
            "task_001:operator_branch_update",
            "operator_branch_update",
            "task_001",
            "feat/feat_001",
            {"kind": "feature_team", "work_id": "feat_001"},
        ),
        (
            "task_001:supervisor_branch_update",
            "supervisor_branch_update",
            "task_001",
            "feat/feat_001",
            {"kind": "feature_team", "work_id": "feat_001"},
        ),
        (
            "task_001:merge_to_feature",
            "task_merge",
            "task_001",
            "feat/feat_001",
            {"kind": "feature_team", "work_id": "feat_001"},
        ),
        (
            "feat_001:merge_to_epic",
            "feature_merge",
            "feat_001",
            "epic/epic_001",
            {"kind": "epic_team", "work_id": "epic_001"},
        ),
        (
            "epic_001:promote",
            "epic_promotion",
            "epic_001",
            "epic/epic_001",
            {"kind": "epic_team", "work_id": "epic_001"},
        ),
        (
            "epic_001:close",
            "epic_close",
            "epic_001",
            "epic/epic_001",
            {"kind": "epic_team", "work_id": "epic_001"},
        ),
    ),
)
def test_supported_failure_boundaries_preserve_context_and_enqueue_once(
    tmp_path: Path,
    action_id: str,
    action_kind: str,
    affected_work_id: str,
    target_ref: str,
    owner: dict[str, str],
) -> None:
    """All supported first-failure callers share the durable route-once boundary."""

    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        action_id,
        action_kind,
        root=root,
        attempt_bound=2,
        metadata={"user_file": "leave-me-alone", "approval": "review-42"},
    )
    captured = capture_and_route_action_failure(
        action_id,
        action_kind,
        affected_work_id=affected_work_id,
        intended_target_ref=target_ref,
        root=root,
        failure_code="branch_conflict",
        safe_summary="The recorded integration boundary rejected the action.",
        evidence={"source_revision": "abc", "target_revision": "def"},
        provenance={"authorization": "auth-42", "review": "review-42"},
        conflicting_paths=("user/edited-file.txt",),
    )

    assert captured["metadata"] == {
        "user_file": "leave-me-alone",
        "approval": "review-42",
    }
    assert captured["recovery"]["original_action"] == {
        "action_id": action_id,
        "action_kind": action_kind,
    }
    assert captured["recovery"]["provenance"] == {
        "authorization": "auth-42",
        "review": "review-42",
    }
    assert captured["recovery"]["owning_team"] == owner
    assert captured["recovery"]["evidence"]["conflicting_paths"] == [
        "user/edited-file.txt"
    ]

    events, _ = read_events(owner["work_id"], 0, root=root)
    assert len(events) == 1
    assert events[0].payload["investigation_id"] == f"recovery:{action_id}"

    # A retry after a process reload preserves the original identity and never
    # overwrites approvals/provenance or sends another investigation.
    assert (
        capture_and_route_action_failure(
            action_id,
            action_kind,
            affected_work_id=affected_work_id,
            intended_target_ref=target_ref,
            root=root,
            failure_code="branch_conflict",
            safe_summary="The recorded integration boundary rejected the action.",
        )
        == captured
    )
    events, _ = read_events(owner["work_id"], 0, root=root)
    assert len(events) == 1
    assert load_action(action_id, root=root) == captured


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


def test_resume_routes_failures_and_stops_when_attempt_budget_is_exhausted(
    tmp_path: Path,
) -> None:
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
    downstream_effects = {
        name: [] for name in ("team_turn", "review", "merge", "completion")
    }
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
    assert [attempt["outcome"] for attempt in completed["attempts"]] == [
        "failed",
        "succeeded",
    ]
    assert [attempt["classification"] for attempt in completed["attempts"]] == [
        "transient_retry",
        None,
    ]
    assert all(effects == [action_id] for effects in downstream_effects.values())

    # Repeated retry requests after completion are idempotent and add no history or effects.
    assert (
        resume_action(
            action_id,
            root=root,
            execute=lambda _context: pytest.fail("completed action must not execute"),
        )
        == completed
    )
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
    assert (
        record_repair_precondition(
            action_id,
            "integration_checkout",
            root=root,
            metadata={"feature_id": "feat_001", "branch": "epic/epic_001"},
        )
        == pending
    )

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
    assert (
        resume_action(
            action_id,
            root=root,
            execute=lambda _context: pytest.fail("must await owner"),
        )
        == handed_off
    )

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
    assert (
        record_owner_resolution(
            action_id,
            "merge-conflict:source-target",
            "resolution:feat_001:42",
            root=root,
            metadata={"strategy": "feature-approved"},
        )
        == resolved
    )

    resumed = resume_action(
        action_id,
        root=root,
        execute=lambda context: {"metadata": {"resumed_action": context.action_id}},
    )
    assert resumed["recovery_state"] == "completed"
    assert resumed["attempts"][-1]["completion_metadata"] == {
        "resumed_action": action_id
    }


def test_allowlisted_repair_is_bounded_and_resume_revalidates_same_action(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action_id = "task_001:merge_to_feature"
    create_or_load_action(action_id, "task_merge", root=root, attempt_bound=1)
    called: list[str] = []

    repaired = repair_action(
        action_id,
        "restore_abort_state",
        root=root,
        execute=lambda action: {"metadata": {"operation": "restore_abort_state", "id": action["action_id"]}},
    )
    assert repaired["recovery_state"] == "ready_to_resume"
    assert repaired["repair_attempts"][0]["operation"] == "restore_abort_state"
    assert repaired["attempt_count"] == 0

    resumed = resume_action(
        action_id,
        root=root,
        preflight=lambda context: called.append(f"checked:{context.action_id}"),
        execute=lambda context: {"metadata": {"original": context.action_id}},
    )
    assert resumed["recovery_state"] == "completed"
    assert called == [f"checked:{action_id}"]
    assert resumed["attempts"][0]["completion_metadata"] == {"original": action_id}


def test_repair_refuses_unknown_operation_and_stops_at_its_bound(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action("action", "task_merge", root=root, attempt_bound=1)
    with pytest.raises(ActionRecoveryError, match="repair operation"):
        repair_action("action", "discard_unrelated_files", root=root, execute=lambda _: None)

    repair_action(
        "action", "validate_checkout", root=root,
        execute=lambda _: (_ for _ in ()).throw(
            ActionFailure("deterministic_repair", "still repairing")
        ),
    )
    bounded = repair_action(
        "action", "validate_checkout", root=root, execute=lambda _: pytest.fail("must not run")
    )
    assert bounded["recovery_state"] == "blocked"
    assert bounded["recovery"]["human_blocker"]["code"] == "repair_attempt_bound_reached"


def test_reconciliation_selects_one_restart_outcome_from_checkpointed_git_facts(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action_id = "review:147:rebase"
    create_or_load_action(action_id, "review_rebase", root=root, attempt_bound=2)
    record_action_checkpoint(
        action_id,
        "admitted-heads",
        root=root,
        refs={"source": "feat/147", "target": "main"},
        shas={"source_head": "source-1", "target_head": "target-1"},
        affected_paths=["cascade/task/action_recovery.py"],
        command_summary="git rebase origin/main",
        test_summary="not run",
        resume_instructions="Resume the admitted rebase or refresh admission.",
    )

    safe_retry = reconcile_action(
        action_id, root=root, local_head="source-1", remote_head="target-1"
    )
    assert (safe_retry.outcome, safe_retry.reason) == ("safe_retry", "source_head_unchanged")

    in_progress = reconcile_action(
        action_id, root=root, local_head="partial", remote_head="target-1", rebase_in_progress=True
    )
    assert in_progress.outcome == "resume"

    remote_race = reconcile_action(
        action_id, root=root, local_head="source-1", remote_head="target-2"
    )
    assert (remote_race.outcome, remote_race.reason) == ("blocker", "remote_head_changed")
    persisted = load_action(action_id, root=root)
    assert persisted is not None
    assert persisted["checkpoint"]["affected_paths"] == ["cascade/task/action_recovery.py"]
    assert persisted["last_reconciliation"] == remote_race.as_dict()


def test_reconciliation_detects_completed_publication_without_replaying_it(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    action_id = "review:148:rebase"
    create_or_load_action(action_id, "review_rebase", root=root, attempt_bound=2)
    record_action_checkpoint(
        action_id,
        "published",
        root=root,
        refs={"source": "feat/148", "target": "main"},
        shas={
            "source_head": "source-1", "target_head": "target-1",
            "rebased_head": "rebased-1", "published_head": "target-1",
        },
        affected_paths=[],
        command_summary="git push --force-with-lease",
        test_summary="tests/test_review_rebase.py passed",
        resume_instructions="Verify the review then mark the action complete.",
    )

    completed = reconcile_action(
        action_id, root=root, local_head="rebased-1", remote_head="target-1"
    )
    assert (completed.outcome, completed.reason) == ("already_completed", "published_head_on_remote")
