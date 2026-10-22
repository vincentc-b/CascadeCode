"""Local SQLite checkpointers per epic (one file per epic id)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from cascade.board.work_ids import tier_of_work_id

_connections: dict[str, sqlite3.Connection] = {}
_savers: dict[str, SqliteSaver] = {}


def _validate_checkpoint_epic_id(epic_id: str) -> None:
    if "/" in epic_id or ".." in epic_id:
        raise ValueError(f"invalid epic checkpoint id: {epic_id!r}")
    tier = tier_of_work_id(epic_id)
    if tier != "epic":
        raise ValueError(f"checkpoint id must be an epic work id: {epic_id!r}")


def checkpoint_path(epic_id: str, *, root: Path) -> Path:
    _validate_checkpoint_epic_id(epic_id)
    return root / ".cascade" / "checkpoints" / f"{epic_id}.sqlite"


def get_checkpointer(epic_id: str, *, root: Path) -> SqliteSaver:
    """Return a cached SqliteSaver for this epic's checkpoint file."""

    _validate_checkpoint_epic_id(epic_id)
    path = checkpoint_path(epic_id, root=root).resolve()
    key = str(path)
    if key not in _savers:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        _connections[key] = conn
        _savers[key] = saver
    return _savers[key]


def thread_config(epic_id: str) -> dict:
    return {"configurable": {"thread_id": epic_id}}
