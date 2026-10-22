"""Persisted per-room settings for Epic and Feature War Rooms (feat_007_001)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from cascade.board.store import read_doc
from cascade.war_room.chat_store import graph_id_is_valid
from cascade.workspace.integration_worktree import locate_trunk
from cascade.watchdog.lock import process_lock

_ROOM_GRAPH_PREFIXES = ("epic_", "feat_")


@dataclass(frozen=True)
class RoomSettings:
    graph_id: str
    stacked_pr_enabled: bool


def is_room_graph_id(graph_id: str) -> bool:
    return graph_id.startswith(_ROOM_GRAPH_PREFIXES)


def _state_path(trunk: Path) -> Path:
    return trunk / ".cascade" / "room_settings.json"


def _load(trunk: Path) -> dict[str, dict[str, object]]:
    path = _state_path(trunk)
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    rooms = raw.get("rooms")
    if not isinstance(rooms, dict):
        return {}
    out: dict[str, dict[str, object]] = {}
    for key, value in rooms.items():
        if isinstance(key, str) and isinstance(value, dict):
            out[key] = dict(value)
    return out


def _save(trunk: Path, rooms: dict[str, dict[str, object]]) -> None:
    path = _state_path(trunk)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"rooms": rooms}
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def _read_stacked_pr_enabled(record: dict[str, object] | None) -> bool:
    if not record:
        return False
    value = record.get("stacked_pr_enabled")
    return value is True


def read_room_settings(graph_id: str, *, root: Path) -> RoomSettings:
    """Return durable room settings; missing fields default to disabled."""

    _validate_room_graph_id(graph_id)
    trunk = locate_trunk(root)
    record = _load(trunk).get(graph_id)
    return RoomSettings(
        graph_id=graph_id,
        stacked_pr_enabled=_read_stacked_pr_enabled(record),
    )


def stacked_pr_enabled(graph_id: str, *, root: Path) -> bool:
    """Convenience read for dispatch eligibility (future-only; no PR side effects)."""

    return read_room_settings(graph_id, root=root).stacked_pr_enabled


def write_stacked_pr_enabled(
    graph_id: str, enabled: bool, *, root: Path
) -> RoomSettings:
    """Persist the stacked-PR opt-in for one room graph id."""

    _validate_room_graph_id(graph_id)
    if not isinstance(enabled, bool):
        raise ValueError("stacked_pr_enabled must be a boolean")

    trunk = locate_trunk(root)
    with process_lock:
        rooms = _load(trunk)
        record = dict(rooms.get(graph_id) or {})
        record["stacked_pr_enabled"] = enabled
        rooms[graph_id] = record
        _save(trunk, rooms)
    return RoomSettings(graph_id=graph_id, stacked_pr_enabled=enabled)


def _validate_room_graph_id(graph_id: str) -> None:
    if not graph_id_is_valid(graph_id):
        raise ValueError(f"invalid graph_id: {graph_id!r}")
    if not is_room_graph_id(graph_id):
        raise ValueError("room settings require an epic or feature graph id")


def ensure_room_doc_exists(graph_id: str, *, root: Path) -> None:
    """Raise NotFound when the graph id is not a persisted epic/feature doc."""

    _validate_room_graph_id(graph_id)
    doc = read_doc(graph_id, root=root)
    if doc.meta.tier not in ("epic", "feature"):
        raise ValueError("room settings require an epic or feature graph id")
