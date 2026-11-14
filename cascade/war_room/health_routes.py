"""War Room GET /api/health — supervisor readiness for the War Room banner (feat_012_001)."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qsl, urlparse

from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.war_room.audit_status import health_audit_status
from cascade.workspace.supervisor_readiness import supervisor_health_http_payload

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_health_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/health", handle_get_health)
    handler_cls.register_get_route("/api/health/audit", handle_get_health_audit)
    handler_cls.register_get_route(
        "/api/health/audit/coverage", handle_get_health_audit_page
    )
    handler_cls.register_get_route(
        "/api/health/audit/history", handle_get_health_audit_page
    )
    handler_cls.register_post_route("/api/health/audit", handle_post_health_audit)


def handle_get_health(handler: WarRoomRequestHandler) -> None:
    payload = supervisor_health_http_payload(handler.server.root, http_serving=True)
    handler._json_response(HTTPStatus.OK, payload)


def handle_get_health_audit(handler: WarRoomRequestHandler) -> None:
    if urlparse(handler.path).query:
        handler._json_error(HTTPStatus.BAD_REQUEST, "audit status accepts no query")
        return
    handler._json_response(HTTPStatus.OK, health_audit_status(root=handler.server.root))


def handle_get_health_audit_page(handler: WarRoomRequestHandler) -> None:
    """Serve one bounded, epoch-pinned coverage or history page."""

    from cascade.war_room.audit_projection_reader import (
        AuditProjectionRequestError,
        read_audit_projection,
    )

    parsed = urlparse(handler.path)
    section = parsed.path.rsplit("/", 1)[-1]
    try:
        request = _page_request(section, parsed.query)
        payload = read_audit_projection(handler.server.root, request)
    except AuditProjectionRequestError as exc:
        if str(exc) == "cursor does not match request":
            handler._json_response(
                HTTPStatus.CONFLICT,
                {"state": "pending", "reason": "cursor_mismatch", "restart": True},
            )
        else:
            handler._json_error(HTTPStatus.BAD_REQUEST, str(exc))
        return
    status = HTTPStatus.CONFLICT if payload.get("restart") is True else HTTPStatus.OK
    handler._json_response(status, payload)


def _page_request(section: str, query: str):
    from cascade.war_room.audit_projection_reader import (
        AuditPageRequest,
        AuditProjectionRequestError,
    )

    allowed = {"cursor", "limit", "work_id", "owner", "status", "from", "to"}
    values: dict[str, str] = {}
    try:
        pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise AuditProjectionRequestError("query string is malformed") from exc
    for name, value in pairs:
        if name not in allowed:
            raise AuditProjectionRequestError(f"unknown query parameter: {name}")
        if name in values:
            raise AuditProjectionRequestError(f"duplicate query parameter: {name}")
        if not value:
            raise AuditProjectionRequestError(f"{name} query parameter is empty")
        values[name] = value
    raw_limit = values.pop("limit", None)
    if raw_limit is None:
        limit = 50
    else:
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise AuditProjectionRequestError("limit must be an integer") from exc
    return AuditPageRequest(
        section=section,  # type: ignore[arg-type]
        cursor=values.get("cursor"),
        limit=limit,
        work_id=values.get("work_id"),
        owner=values.get("owner"),
        status=values.get("status"),
        occurred_from=values.get("from"),
        occurred_to=values.get("to"),
    )


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
    if admitted is None:
        handler._json_error(HTTPStatus.SERVICE_UNAVAILABLE, "health audit unavailable")
        return
    handler._json_response(
        HTTPStatus.ACCEPTED,
        {
            "ok": True,
            "status": "admitted" if admitted else "coalesced",
        },
    )
