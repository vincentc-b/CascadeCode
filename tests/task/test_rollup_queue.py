import json
from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.task_rollup import queue_task_merge, retry_pending_task_merges
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
