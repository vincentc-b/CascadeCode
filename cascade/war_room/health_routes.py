"""War Room GET /api/health — supervisor status for the War Room banner (feat_018_003)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from cascade.workspace.supervisor_readiness import read_supervisor_health_projection

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_health_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/health", handle_get_health)


def handle_get_health(handler: WarRoomRequestHandler) -> None:
    payload = read_supervisor_health_projection(
        handler.server.root,
        http_serving=True,
    )
    handler._json_response(HTTPStatus.OK, payload)
