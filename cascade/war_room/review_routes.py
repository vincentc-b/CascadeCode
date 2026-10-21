"""War Room HTTP routes for the durable open-reviews registry (feat_003 / task_007)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from cascade.review import list_open_reviews
from cascade.war_room.serialize import open_review_to_dict

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_review_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/open-reviews", handle_get_open_reviews)


def handle_get_open_reviews(handler: WarRoomRequestHandler) -> None:
    reviews = list_open_reviews(root=handler.server.root)
    payload = {"reviews": [open_review_to_dict(row) for row in reviews]}
    handler._json_response(HTTPStatus.OK, payload)
