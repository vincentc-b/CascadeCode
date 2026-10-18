"""Branch diff summary and awaiting-merge signaling (no merge)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.gitutil import _run
from cascade.task.worktree import TaskRun
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event


def summarize_diff(task_run: TaskRun, *, root: Path) -> str:
    """Short diff stat vs the parent feature branch; not a full patch."""

    from cascade.board.errors import NotFound
    from cascade.board.store import read_doc
    from cascade.workspace.integration_worktree import doc_filesystem_root

    repo = Path(root).resolve()
    branch = task_run.branch
    diff_root = repo
    try:
        task = read_doc(task_run.task_id, root=repo)
        if task.meta.parent:
            diff_root = doc_filesystem_root(task.meta.parent, trunk=repo)
    except NotFound:
        pass
    result = _run(["diff", "--stat", f"HEAD...{branch}"], diff_root, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git diff HEAD...{branch} failed")
    return result.stdout.strip()


def mark_awaiting_merge(task_id: str, task_run: TaskRun, *, root: Path) -> None:
    """Mark the run awaiting human merge and surface branch + diff in War Room."""

    from cascade.board.store import read_doc

    repo = Path(root).resolve()
    branch = f"task/{task_id}"
    summary = summarize_diff(task_run, root=repo)
    task_run.state = "awaiting_merge"

    target = "feat/{feature_id}"
    try:
        task = read_doc(task_id, root=repo)
        if task.meta.parent:
            target = f"feat/{task.meta.parent}"
    except Exception:
        pass
    body_parts = [f"Branch {branch} is ready to merge into {target}."]
    if summary:
        body_parts.append(summary)
    body = "\n\n".join(body_parts)

    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "task_ready",
                "id": task_id,
                "message": body,
                "body": body,
            },
            dest="war_room",
        ),
        root=repo,
    )
