"""War Room HTTP routes for brief provider/model inventory (task_006_001_003)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.briefs import fetch_brief_provider_inventory

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_brief_inventory_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/brief/inventory", handle_get_brief_inventory)
    handler_cls.register_post_route(
        "/api/brief/inventory/refresh", handle_post_brief_inventory_refresh
    )


def handle_get_brief_inventory(handler: WarRoomRequestHandler) -> None:
    payload = fetch_brief_provider_inventory(handler.server.root)
    handler._json_response(HTTPStatus.OK, payload)


def handle_post_brief_inventory_refresh(
    handler: WarRoomRequestHandler, _body: dict[str, Any]
) -> None:
    payload = fetch_brief_provider_inventory(handler.server.root, force_refresh=True)
    handler._json_response(HTTPStatus.OK, payload)


def brief_inventory_api_path_exists(path: str) -> bool:
    return path in ("/api/brief/inventory", "/api/brief/inventory/refresh")
