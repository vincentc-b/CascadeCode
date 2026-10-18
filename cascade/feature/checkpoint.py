"""Local SQLite checkpointers per feature (one file per feature id)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver

from cascade.board.paths import parse_work_id

_connections: dict[str, sqlite3.Connection] = {}
_savers: dict[str, SqliteSaver] = {}


def _validate_checkpoint_feature_id(feature_id: str) -> None:
    if "/" in feature_id or ".." in feature_id:
        raise ValueError(f"invalid feature checkpoint id: {feature_id!r}")
    tier, _ = parse_work_id(feature_id)
    if tier != "feature":
        raise ValueError(f"checkpoint id must be a feature work id: {feature_id!r}")


def checkpoint_path(feature_id: str, *, root: Path) -> Path:
    _validate_checkpoint_feature_id(feature_id)
    return root / ".cascade" / "checkpoints" / f"{feature_id}.sqlite"


def get_checkpointer(feature_id: str, *, root: Path) -> SqliteSaver:
    """Return a cached SqliteSaver for this feature's checkpoint file."""

    _validate_checkpoint_feature_id(feature_id)
    path = checkpoint_path(feature_id, root=root).resolve()
    key = str(path)
    if key not in _savers:
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        saver = SqliteSaver(conn)
        saver.setup()
        _connections[key] = conn
        _savers[key] = saver
    return _savers[key]


def thread_config(feature_id: str) -> dict:
    return {"configurable": {"thread_id": feature_id}}
