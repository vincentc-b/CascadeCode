"""Local SQLite checkpointers per epic (one file per epic id)."""

from __future__ import annotations

import os
import sqlite3
import uuid
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


def begin_activation_run(epic_id: str, *, root: Path) -> str:
    """Start a new Epic execution run without reusing an older checkpoint.

    An Epic can return to the reviewed backlog and later be activated again.
    Its old graph state is evidence of the previous run, not input to the new
    one, so keep it in an archive and leave the canonical checkpoint path
    empty for the boot hook to seed again.
    """

    path = checkpoint_path(epic_id, root=root).resolve()
    key = str(path)
    saver = _savers.pop(key, None)
    connection = _connections.pop(key, None)
    if connection is not None:
        connection.close()
    # ``SqliteSaver`` owns no independent resource, but dropping it before
    # moving the database prevents a cached saver from reviving old state.
    del saver

    run_id = uuid.uuid4().hex
    if path.exists():
        archive = path.parent / "archive" / epic_id / f"{run_id}.sqlite"
        archive.parent.mkdir(parents=True, exist_ok=True)
        os.replace(path, archive)
    return run_id


def thread_config(epic_id: str) -> dict:
    return {"configurable": {"thread_id": epic_id}}
