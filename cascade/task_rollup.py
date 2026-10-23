"""Durable retry queue for automatic task-to-feature merges."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import _run
from cascade.board.store import read_doc
from cascade.task.execution import execution_view, mark_merge_blocked
from cascade.watchdog.events import append_event
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event


def _path(root: Path) -> Path:
    return root / ".cascade" / "pending-task-merges.json"


def _read(root: Path) -> list[str]:
    path = _path(root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(item) for item in raw if isinstance(item, str)] if isinstance(raw, list) else []


def _write(root: Path, task_ids: list[str]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(sorted(set(task_ids)), indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def queue_task_merge(task_id: str, *, root: Path) -> None:
    repo = resolve_root(root)
    with process_lock:
        pending = _read(repo)
        if task_id not in pending:
            pending.append(task_id)
            _write(repo, pending)


def pending_task_merges(root: Path) -> set[str]:
    repo = resolve_root(root)
    with process_lock:
        return set(_read(repo))


def retry_pending_task_merges(root: Path) -> list[str]:
    """Retry durable task merges and return ids completed on this pass."""

    repo = resolve_root(root)
    completed: list[str] = []
    terminal: list[str] = []
    with process_lock:
        pending = _read(repo)
    for task_id in pending:
        from cascade.boss.merge import merge_task_branch

        if _same_conflict_still_blocked(task_id, repo):
            continue
        result = merge_task_branch(task_id, root=repo)
        if not result.ok:
            if result.reason in {"task_not_found", "wrong_column", "not_mergeable"}:
                terminal.append(task_id)
            elif result.reason != "busy":
                _record_merge_refusal(task_id, result, repo)
            continue
        completed.append(task_id)
        from cascade.boss.rollup import on_task_merged

        try:
            on_task_merged(task_id, root=repo)
        except Exception:
            # The task merge itself is complete. Feature closeout is scanned on
            # every automation tick and can recover independently.
            pass
    if completed or terminal:
        with process_lock:
            latest = _read(repo)
            removed = set(completed) | set(terminal)
            _write(repo, [task_id for task_id in latest if task_id not in removed])
    return completed


def _merge_head_pair(task_id: str, root: Path) -> tuple[str, str] | None:
    """The source and target refs that determine a task merge conflict."""

    try:
        task = read_doc(task_id, root=root)
    except NotFound:
        return None
    if task.meta.status != "active" or not task.meta.parent:
        return None
    refs = (f"refs/heads/task/{task_id}", f"refs/heads/feat/{task.meta.parent}")
    heads: list[str] = []
    for ref in refs:
        result = _run(["rev-parse", "--verify", ref], root, check=False)
        if result.returncode != 0:
            return None
        heads.append(result.stdout.strip())
    return heads[0], heads[1]


def _same_conflict_still_blocked(task_id: str, root: Path) -> bool:
    view = execution_view(task_id, root=root)
    if view is None or view.get("phase") != "merge_blocked":
        return False
    blocker = view.get("merge_blocker")
    if not isinstance(blocker, dict) or blocker.get("reason") != "branch_conflict":
        return False
    heads = _merge_head_pair(task_id, root)
    return heads is not None and heads == (
        blocker.get("source_sha"), blocker.get("target_sha")
    )


def _record_merge_refusal(task_id: str, result, root: Path) -> None:
    heads = _merge_head_pair(task_id, root)
    source_sha, target_sha = heads if heads is not None else (None, None)
    reason = result.reason or "merge_refused"
    paths = tuple(result.conflict_paths)
    if not mark_merge_blocked(
        task_id,
        root=root,
        reason=reason,
        conflict_paths=paths,
        source_sha=source_sha,
        target_sha=target_sha,
    ):
        return
    detail = f" Conflicting files: {', '.join(paths)}." if paths else ""
    recovery = (
        "Resolve the Task branch against its Feature branch, then retry Merge task."
        if reason == "branch_conflict"
        else "Check the merge refusal, then retry Merge task."
    )
    message = f"Task {task_id} could not merge ({reason}).{detail} {recovery}"
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "task_merge_blocked",
                "id": task_id,
                "reason": reason,
                "conflict_paths": list(paths),
                "message": message,
            },
            dest="war_room",
        ),
        root=root,
    )
