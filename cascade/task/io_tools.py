"""Task-scoped swe_read / swe_write and read_doc."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc as board_read_doc
from cascade.board.types import WorkDoc
from cascade.task.guard import TaskToolDenied, task_tool_guard
from cascade.task.registry import register_task_tool
from cascade.task.worktree import TaskRun, get_task_run

_COMMENT_PREFIX = "_comments/"


def swe_read(path: str | Path, *, task_id: str, task_run: TaskRun, root: Path) -> str:
    """Read a file under the task worktree after guard check."""

    repo = Path(root).resolve()
    if task_run.task_id != task_id:
        raise TaskToolDenied(
            f"task_run.task_id {task_run.task_id!r} != task_id {task_id!r}"
        )
    wt = task_run.worktree.resolve()
    if not task_tool_guard(
        path,
        "read",
        task_id=task_id,
        worktree_root=wt,
        board_root=repo,
    ):
        raise TaskToolDenied(f"read denied for {path}")
    target = _resolve_path(path, wt)
    if not target.is_file():
        raise FileNotFoundError(str(target))
    return target.read_text(encoding="utf-8")


def swe_write(
    path: str | Path,
    content: str,
    *,
    task_id: str,
    task_run: TaskRun,
    root: Path,
) -> None:
    """Write a file under the task worktree after guard check."""

    repo = Path(root).resolve()
    if task_run.task_id != task_id:
        raise TaskToolDenied(
            f"task_run.task_id {task_run.task_id!r} != task_id {task_id!r}"
        )
    wt = task_run.worktree.resolve()
    if not task_tool_guard(
        path,
        "write",
        task_id=task_id,
        worktree_root=wt,
        board_root=repo,
    ):
        raise TaskToolDenied(f"write denied for {path}")
    target = _resolve_path(path, wt)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def task_read_doc(work_id: str, *, task_id: str, root: Path) -> WorkDoc:
    """Read own Task doc or parent Feature at pinned parent_rev."""

    repo = Path(root).resolve()
    task = _load_task(task_id, repo)

    if work_id.startswith(("_war_room/", "_queue/", "_amendments/")):
        raise TaskToolDenied(f"read denied for sidecar {work_id!r}")

    if work_id.startswith(_COMMENT_PREFIX):
        raise TaskToolDenied(f"comment read denied for {work_id!r}")

    parent_id = task.meta.parent
    if parent_id is not None and work_id == parent_id:
        if task.meta.parent_rev is None:
            raise TaskToolDenied(
                "parent feature read requires parent_rev; pin on boot or via pin_parent"
            )
        doc = board_read_doc(parent_id, rev=task.meta.parent_rev, root=repo)
        if doc.meta.tier != "feature":
            raise TaskToolDenied(f"{parent_id} is not a feature")
        return doc

    if work_id == task_id:
        return board_read_doc(task_id, root=repo)

    try:
        doc = board_read_doc(work_id, root=repo)
    except NotFound:
        raise TaskToolDenied(f"unknown work id {work_id}") from None

    if doc.meta.tier == "epic":
        raise TaskToolDenied(f"task team cannot read epic {work_id}")
    if doc.meta.tier == "feature":
        raise TaskToolDenied(f"task team cannot read feature {work_id}")
    if doc.meta.tier == "task":
        raise TaskToolDenied(f"task team cannot read task {work_id}")
    raise TaskToolDenied(f"read denied for {work_id}")


def read_doc(work_id: str, *, task_id: str, root: Path) -> WorkDoc:
    """Tool wrapper: task-scoped read_doc."""

    return task_read_doc(work_id, task_id=task_id, root=root)


def _swe_read_tool(path: str, *, task_id: str, root: Path) -> str:
    run = get_task_run(task_id)
    if run is None:
        raise TaskToolDenied(f"no active task run for {task_id}")
    return swe_read(path, task_id=task_id, task_run=run, root=root)


def _swe_write_tool(path: str, content: str, *, task_id: str, root: Path) -> None:
    run = get_task_run(task_id)
    if run is None:
        raise TaskToolDenied(f"no active task run for {task_id}")
    swe_write(path, content, task_id=task_id, task_run=run, root=root)


def register_task_io_tools() -> None:
    """Register swe_read, swe_write, and read_doc on the task tool registry (idempotent)."""

    from cascade.task.registry import task_tools

    expected = ("swe_read", "swe_write", "read_doc")
    if all(name in task_tools() for name in expected):
        return
    register_task_tool("swe_read", _swe_read_tool)
    register_task_tool("swe_write", _swe_write_tool)
    register_task_tool("read_doc", read_doc)


def _load_task(task_id: str, root: Path):
    try:
        task = board_read_doc(task_id, root=root)
    except NotFound:
        raise TaskToolDenied(f"unknown task {task_id}") from None
    if task.meta.tier != "task":
        raise TaskToolDenied(f"{task_id} is not a task")
    return task


def _resolve_path(path: str | Path, worktree: Path) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = worktree / candidate
    return candidate.resolve()
