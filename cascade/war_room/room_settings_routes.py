"""War Room HTTP routes for persisted room settings (task_007_001_001)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.board.errors import NotFound
from cascade.war_room.room_settings import (
    ensure_room_doc_exists,
    read_room_settings,
    write_stacked_pr_enabled,
)
from cascade.war_room.serialize import room_settings_to_dict

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler

_PREFIX = "/api/room-settings/"


def register_room_settings_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    """Room settings use prefix handlers registered on the core server."""


def _parse_graph_id(path: str) -> str | None:
    if not path.startswith(_PREFIX):
        return None
    graph_id = path.removeprefix(_PREFIX).strip("/")
    if not graph_id or "/" in graph_id:
        return None
    return graph_id


def room_settings_api_path_exists(path: str) -> bool:
    return _parse_graph_id(path) is not None


def try_handle_room_settings_get(handler: WarRoomRequestHandler) -> bool:
    graph_id = _parse_graph_id(handler.path.split("?", 1)[0])
    if graph_id is None:
        return False
    try:
        ensure_room_doc_exists(graph_id, root=handler.server.root)
    except NotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {graph_id}")
        return True
    except ValueError as exc:
        handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return True
    settings = read_room_settings(graph_id, root=handler.server.root)
    handler._json_response(HTTPStatus.OK, room_settings_to_dict(settings))
    return True


def try_handle_room_settings_post(
    handler: WarRoomRequestHandler, body: dict[str, Any]
) -> bool:
    graph_id = _parse_graph_id(handler.path.split("?", 1)[0])
    if graph_id is None:
        return False
    raw_enabled = body.get("stacked_pr_enabled")
    if not isinstance(raw_enabled, bool):
        handler._json_error(HTTPStatus.BAD_REQUEST, "stacked_pr_enabled must be a boolean")
        return True
    try:
        ensure_room_doc_exists(graph_id, root=handler.server.root)
    except NotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {graph_id}")
        return True
    except ValueError as exc:
        handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return True
    try:
        settings = write_stacked_pr_enabled(
            graph_id, raw_enabled, root=handler.server.root
        )
    except ValueError as exc:
        handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return True
    handler._json_response(HTTPStatus.OK, room_settings_to_dict(settings))
    return True
