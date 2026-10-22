"""Local SQLite checkpointers per task (one file per task id)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from cascade.board.work_ids import tier_of_work_id

_connections: dict[str, sqlite3.Connection] = {}
_savers: dict[str, SqliteSaver] = {}


def _validate_checkpoint_task_id(task_id: str) -> None:
    if "/" in task_id or ".." in task_id:
        raise ValueError(f"invalid task checkpoint id: {task_id!r}")
    tier = tier_of_work_id(task_id)
    if tier != "task":
        raise ValueError(f"checkpoint id must be a task work id: {task_id!r}")


def checkpoint_path(task_id: str, *, root: Path) -> Path:
    _validate_checkpoint_task_id(task_id)
    return root / ".cascade" / "checkpoints" / f"{task_id}.sqlite"


def get_checkpointer(task_id: str, *, root: Path) -> SqliteSaver:
    """Return a cached SqliteSaver for this task's checkpoint file."""

    _validate_checkpoint_task_id(task_id)
    path = checkpoint_path(task_id, root=root).resolve()
    key = str(path)
    if key not in _savers:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        _connections[key] = conn
        _savers[key] = saver
    return _savers[key]


def thread_config(task_id: str) -> dict:
    return {"configurable": {"thread_id": task_id}}


def drop_task_checkpoint(task_id: str, *, root: Path) -> None:
    """Close and remove the SQLite checkpointer file for this task."""

    _validate_checkpoint_task_id(task_id)
    path = checkpoint_path(task_id, root=root).resolve()
    key = str(path)
    conn = _connections.pop(key, None)
    _savers.pop(key, None)
    if conn is not None:
        conn.close()
    if path.is_file():
        path.unlink()
