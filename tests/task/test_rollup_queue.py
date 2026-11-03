import json
from pathlib import Path

import pytest

from cascade.board.store import read_doc, write_doc
from cascade.boss.merge import MergeResult
from cascade.task.action_recovery import ActionNotFound, ActionRecoveryError, load_action
from cascade.task.execution import execution_view, mark_queued
from cascade.task_rollup import (
    handoff_queued_merge_semantic_conflict,
    pending_task_merges,
    queue_task_merge,
    resolve_semantic_conflict,
    retry_pending_task_merges,
)
from cascade.watchdog.events import read_events
from cascade.war_room.toasts import events_to_toasts
from tests.support import add_doc, make_repo


def test_blocked_pending_merge_is_pruned_as_terminal(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=root)
    queue_task_merge("task_001", root=root)

    assert retry_pending_task_merges(root) == []
    path = root / ".cascade" / "pending-task-merges.json"
    assert json.loads(path.read_text(encoding="utf-8")) == []


def test_revalidation_replaces_queue_evidence_without_duplicate_entry(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    first = {
        "task_id": "task_001",
        "deliverable_sha": "deliverable-1",
        "feature_base_sha": "feature-base-1",
    }
    second = {
        "task_id": "task_001",
        "deliverable_sha": "deliverable-2",
        "feature_base_sha": "feature-base-2",
    }

    queue_task_merge("task_001", root=root, delivery_evidence=first)
    queue_task_merge("task_001", root=root, delivery_evidence=second)

    action = load_action("task_001:queued_merge", root=root)
    assert action is not None
    assert action["metadata"]["final_validation"] == second
    assert pending_task_merges(root) == {"task_001"}

    retry_pending_task_merges(root)
    action = load_action("task_001:queued_merge", root=root)
    assert action is not None
    assert action["metadata"]["final_validation"] == second


def test_conflict_is_persisted_as_semantic_block_without_repeat_merge(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    mark_queued("task_001", root=root)
    heads = ["source1", "target1"]
    attempts = []

    monkeypatch.setattr(
        "cascade.task_rollup._merge_head_pair",
        lambda task_id, repo: tuple(heads)
        if read_doc(task_id, root=repo).meta.status == "active" else None,
    )

    def conflicting_merge(task_id: str, *, root: Path):
        attempts.append(task_id)
        return MergeResult(
            ok=False, reason="branch_conflict", branch="task/task_001",
            target_branch="feat/feat_001", conflict_paths=("cascade/workspace/worker.py",),
        )

    monkeypatch.setattr("cascade.boss.merge.merge_task_branch", conflicting_merge)
    queue_task_merge("task_001", root=root)
    assert retry_pending_task_merges(root) == []
    assert retry_pending_task_merges(root) == []
    assert attempts == ["task_001"]

    action = load_action("task_001:queued_merge", root=root)
    assert action is not None
    assert action["recovery_state"] == "awaiting_owner_decision"
    assert action["failure_classification"] == "owner_decision"
    decision = action["owner_decisions"][0]
    assert decision["owner"] == "feature_team"
    assert decision["metadata"]["evidence"] == {
        "source_sha": "source1",
        "target_sha": "target1",
        "reason": "branch_conflict",
        "conflict_paths": ["cascade/workspace/worker.py"],
    }
    evidence = action["attempts"][-1]["completion_metadata"]
    assert evidence["source_sha"] == "source1"
    assert evidence["target_sha"] == "target1"
    assert evidence["conflict_paths"] == ["cascade/workspace/worker.py"]

    assert execution_view("task_001", root=root)["health"] == "merge_blocked"
    events, _ = read_events("war_room", 0, root=root)
    toasts = events_to_toasts(events)
    assert len(toasts) == 1
    assert toasts[0]["kind"] == "task_merge_blocked"

    # A changed head remains an owner decision until task 004 records a resolution.
    heads[1] = "target2"
    assert retry_pending_task_merges(root) == []
    assert attempts == ["task_001"]


def test_repaired_mechanical_merge_reuses_action_and_completes_once(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    merges: list[str] = []
    rollups: list[str] = []

    def merge(task_id: str, *, root: Path):
        merges.append(task_id)
        if len(merges) == 1:
            return MergeResult(ok=False, reason="merge_target_missing")
        return MergeResult(ok=True, merge_sha="merged")

    monkeypatch.setattr("cascade.boss.merge.merge_task_branch", merge)
    monkeypatch.setattr(
        "cascade.boss.rollup.on_task_merged", lambda task_id, *, root: rollups.append(task_id)
    )
    queue_task_merge("task_001", root=root)

    assert retry_pending_task_merges(root) == []
    before_restart = load_action("task_001:queued_merge", root=root)
    assert before_restart is not None
    assert before_restart["idempotency_key"] == "task_001:queued_merge"
    assert before_restart["recovery_state"] == "repaired"

    # Loading models a new supervisor process: it resumes the same action.
    assert load_action("task_001:queued_merge", root=root)["action_id"] == "task_001:queued_merge"
    assert retry_pending_task_merges(root) == ["task_001"]
    completed = load_action("task_001:queued_merge", root=root)
    assert completed is not None
    assert completed["recovery_state"] == "completed"
    assert completed["idempotency_key"] == "task_001:queued_merge"
    assert merges == ["task_001", "task_001"]
    assert rollups == ["task_001"]

    # A stale queue record is pruned without invoking merge or rollup.
    queue_task_merge("task_001", root=root)
    assert retry_pending_task_merges(root) == []
    assert merges == ["task_001", "task_001"]
    assert rollups == ["task_001"]



def test_semantic_handoff_scope_and_resolution_resume_original_queue(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    merges: list[str] = []

    def merge(task_id: str, *, root: Path):
        merges.append(task_id)
        if len(merges) == 1:
            return MergeResult(
                ok=False,
                reason="branch_conflict",
                conflict_paths=("conflict.py",),
            )
        return MergeResult(ok=True, merge_sha="merged")

    monkeypatch.setattr("cascade.boss.merge.merge_task_branch", merge)
    monkeypatch.setattr("cascade.boss.rollup.on_task_merged", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("cascade.task_rollup._merge_head_pair", lambda *_args: ("source", "target"))
    queue_task_merge("task_001", root=root)

    assert retry_pending_task_merges(root) == []
    action = load_action("task_001:queued_merge", root=root)
    assert action is not None
    decision = action["owner_decisions"][0]
    decision_id = decision["decision_id"]
    assert decision["owner"] == "feature_team"
    assert retry_pending_task_merges(root) == []
    assert merges == ["task_001"]

    # Broader scope is accepted only when explicitly supplied by a supervisor.
    other = handoff_queued_merge_semantic_conflict(
        "task_001",
        root=root,
        scope="cross_feature",
        evidence={
            "source_sha": "source-2",
            "target_sha": "target-2",
            "reason": "branch_conflict",
            "conflict_paths": ["contract.py"],
        },
    )
    assert other["owner_decisions"][-1]["owner"] == "epic_team"
    with pytest.raises(ActionRecoveryError, match="missing or ambiguous"):
        handoff_queued_merge_semantic_conflict(
            "task_001",
            root=root,
            scope=None,
            evidence={
                "source_sha": "source-3",
                "target_sha": "target-3",
                "reason": "branch_conflict",
                "conflict_paths": [],
            },
        )

    # Resolve both decisions; replay is a no-op and the original queue resumes.
    resolve_semantic_conflict(
        "task_001:queued_merge", decision_id, "resolution:1", root=root, metadata={"ok": True}
    )
    epic_decision = load_action("task_001:queued_merge", root=root)["owner_decisions"][-1]
    resolved = resolve_semantic_conflict(
        "task_001:queued_merge", epic_decision["decision_id"], "resolution:2",
        root=root, metadata={"ok": True},
    )
    assert resolved["recovery_state"] == "retryable"
    assert resolve_semantic_conflict(
        "task_001:queued_merge", epic_decision["decision_id"], "resolution:2",
        root=root, metadata={"ok": True},
    ) == resolved
    with pytest.raises(ActionRecoveryError):
        resolve_semantic_conflict(
            "task_001:queued_merge", epic_decision["decision_id"], "resolution:2",
            root=root, metadata={"ok": False},
        )
    assert retry_pending_task_merges(root) == ["task_001"]
    assert merges == ["task_001", "task_001"]


def test_supervisor_handoff_rejects_unlinked_resolution_without_replaying_merge(
    tmp_path: Path, monkeypatch
) -> None:
    """A fresh supervisor only resumes the exact action after its linked decision resolves."""

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    merge_calls: list[str] = []

    def merge(task_id: str, *, root: Path):
        merge_calls.append(task_id)
        if len(merge_calls) == 1:
            return MergeResult(
                ok=False,
                reason="branch_conflict",
                conflict_paths=("contract.py",),
            )
        return MergeResult(ok=True, merge_sha="merged")

    monkeypatch.setattr("cascade.boss.merge.merge_task_branch", merge)
    monkeypatch.setattr("cascade.boss.rollup.on_task_merged", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("cascade.task_rollup._merge_head_pair", lambda *_args: ("source", "target"))
    queue_task_merge("task_001", root=root)

    assert retry_pending_task_merges(root) == []
    action_id = "task_001:queued_merge"
    blocked = load_action(action_id, root=root)
    assert blocked is not None
    decision_id = blocked["owner_decisions"][0]["decision_id"]
    assert blocked["recovery_state"] == "awaiting_owner_decision"

    # Missing and mismatched decision references fail closed; repeated supervision
    # leaves the durable action blocked and emits no additional merge.
    with pytest.raises(ActionRecoveryError, match="owner decision not found"):
        resolve_semantic_conflict(action_id, "semantic-conflict:missing", "resolution:stale", root=root)
    with pytest.raises(ActionNotFound, match="task_999:queued_merge"):
        resolve_semantic_conflict("task_999:queued_merge", decision_id, "resolution:mismatched", root=root)
    assert retry_pending_task_merges(root) == []
    assert load_action(action_id, root=root) == blocked
    assert merge_calls == ["task_001"]

    # An explicit resolution linked to that decision survives supervisor restart
    # and authorizes exactly one retry of the original action identity.
    resolved = resolve_semantic_conflict(
        action_id, decision_id, "resolution:linked", root=root, metadata={"approved": True}
    )
    assert resolved["owner_decisions"][0]["resolution"]["action_id"] == action_id
    restarted = load_action(action_id, root=root)
    assert restarted is not None
    assert restarted["action_id"] == action_id
    assert retry_pending_task_merges(root) == ["task_001"]
    assert retry_pending_task_merges(root) == []
    assert merge_calls == ["task_001", "task_001"]
