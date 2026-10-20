"""Durable retry queue for automatic task-to-feature merges."""

from __future__ import annotations

import json
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock


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


def retry_pending_task_merges(root: Path) -> list[str]:
    """Retry durable task merges and return ids completed on this pass."""

    repo = resolve_root(root)
    completed: list[str] = []
    terminal: list[str] = []
    with process_lock:
        pending = _read(repo)
    for task_id in pending:
        from cascade.boss.merge import merge_task_branch

        result = merge_task_branch(task_id, root=repo)
        if not result.ok:
            if result.reason in {"task_not_found", "wrong_column", "not_mergeable"}:
                terminal.append(task_id)
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
