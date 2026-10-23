import json
from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.boss.merge import MergeResult
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


def test_conflict_is_visible_once_and_retried_after_branch_changes(tmp_path: Path, monkeypatch) -> None:
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
        if read_doc(task_id, root=root).meta.status != "active":
            return MergeResult(ok=False, reason="wrong_column")
        return MergeResult(
            ok=False, reason="branch_conflict", branch="task/task_001",
            target_branch="feat/feat_001", conflict_paths=("cascade/workspace/worker.py",),
        )

    monkeypatch.setattr("cascade.boss.merge.merge_task_branch", conflicting_merge)
    queue_task_merge("task_001", root=root)
    assert retry_pending_task_merges(root) == []
    assert retry_pending_task_merges(root) == []
    assert attempts == ["task_001"]
    assert execution_view("task_001", root=root)["health"] == "merge_blocked"
    events, _ = read_events("war_room", 0, root=root)
    toasts = events_to_toasts(events)
    assert len(toasts) == 1
    assert toasts[0]["kind"] == "task_merge_blocked"
    assert "cascade/workspace/worker.py" in toasts[0]["body"]

    heads[1] = "target2"
    assert retry_pending_task_merges(root) == []
    assert attempts == ["task_001", "task_001"]
    events, _ = read_events("war_room", 0, root=root)
    assert len(events_to_toasts(events)) == 2

    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=root)
    assert retry_pending_task_merges(root) == []
    assert json.loads((root / ".cascade" / "pending-task-merges.json").read_text()) == []
