"""Feature Team recovery tools for its own failed Task children."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc, write_doc
from cascade.feature.registry import register_feature_tool
from cascade.watchdog.dispatch import dispatch_task
from cascade.workspace.integration_worktree import doc_filesystem_root, locate_trunk


def revise_task(task_id: str, body: str, *, feature_id: str, root: Path) -> str | None:
    """Replace an owned blocked/backlog Task body before a supervised retry."""

    trunk = locate_trunk(Path(root).resolve())
    feature_root = doc_filesystem_root(feature_id, trunk=trunk)
    try:
        task = read_doc(task_id, root=feature_root)
    except NotFound:
        raise ValueError(f"unknown task {task_id}") from None
    if task.meta.tier != "task" or task.meta.parent != feature_id:
        raise ValueError(f"{task_id} is not a child of {feature_id}")
    if task.meta.status not in ("backlog", "ready_to_plan", "blocked"):
        raise ValueError(f"{task_id} cannot be revised while {task.meta.status}")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("task body must not be empty")
    task.body = body.strip() + "\n"
    return write_doc(task, root=feature_root)


def retry_task(task_id: str, *, feature_id: str, root: Path) -> dict[str, object]:
    """Retry one owned blocked Task through the normal dispatch gates."""

    trunk = locate_trunk(Path(root).resolve())
    feature_root = doc_filesystem_root(feature_id, trunk=trunk)
    try:
        task = read_doc(task_id, root=feature_root)
    except NotFound:
        raise ValueError(f"unknown task {task_id}") from None
    if task.meta.tier != "task" or task.meta.parent != feature_id:
        raise ValueError(f"{task_id} is not a child of {feature_id}")
    if task.meta.status != "blocked":
        raise ValueError(f"{task_id} is not blocked")
    result = dispatch_task(task_id, "boss", root=trunk)
    return {"ok": result.ok, "reason": result.reason, "task_id": task_id}


register_feature_tool("revise_task", revise_task)
register_feature_tool("retry_task", retry_task)
