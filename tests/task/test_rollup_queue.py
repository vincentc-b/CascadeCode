import json
from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.boss.merge import MergeResult
from cascade.task.action_recovery import load_action
from cascade.task.execution import execution_view, mark_queued
from cascade.task_rollup import queue_task_merge, retry_pending_task_merges
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
