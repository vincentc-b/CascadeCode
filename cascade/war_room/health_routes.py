"""War Room GET /api/health — supervisor readiness for the War Room banner (feat_012_001)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING

from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.workspace.supervisor_readiness import supervisor_health_http_payload

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_health_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/health", handle_get_health)
    handler_cls.register_post_route("/api/health/audit", handle_post_health_audit)


def handle_get_health(handler: WarRoomRequestHandler) -> None:
    payload = supervisor_health_http_payload(handler.server.root, http_serving=True)
    handler._json_response(HTTPStatus.OK, payload)


def handle_post_health_audit(
    handler: WarRoomRequestHandler, body: dict[str, object]
) -> None:
    """Admit an authenticated manual audit without granting repair authority."""

    if body:
        handler._json_error(HTTPStatus.BAD_REQUEST, "manual audit accepts no body")
        return
    verifier = handler.server.human_identity_verifier
    human = (
        verifier.verify_request(
            method=handler.command,
            path=handler.path.split("?", 1)[0],
            headers=handler.headers,
            client_address=handler.client_address,
        )
        if verifier is not None
        else None
    )
    if not isinstance(human, AuthenticatedHuman):
        handler._json_error(
            HTTPStatus.UNAUTHORIZED,
            "manual audit requires an authenticated local human",
        )
        return
    request = handler.server.health_audit_request
    if request is None:
        handler._json_error(HTTPStatus.SERVICE_UNAVAILABLE, "health audit unavailable")
        return
    admitted = request()
    handler._json_response(
        HTTPStatus.ACCEPTED,
        {
            "ok": True,
            "status": "admitted" if admitted else "coalesced",
        },
    )
