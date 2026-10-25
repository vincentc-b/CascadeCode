"""War Room API routes for editing backlog epic briefs."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.board.errors import GitError
from cascade.brief_cancel_pr import submit_brief_cancel
from cascade.brief_edit_pr import BriefEditError, get_editable_brief, submit_brief_edit

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def register_brief_edit_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/brief/edit", handle_get_brief_edit)
    handler_cls.register_post_route("/api/brief/edit", handle_post_brief_edit)
    handler_cls.register_post_route("/api/brief/cancel", handle_post_brief_cancel)


def _error(handler: WarRoomRequestHandler, exc: BriefEditError) -> None:
    handler._json_response(
        HTTPStatus(exc.status),
        {"ok": False, "error": str(exc), "code": exc.code, "reload": exc.reload},
    )


def handle_get_brief_edit(handler: WarRoomRequestHandler) -> None:
    try:
        handler._json_response(HTTPStatus.OK, get_editable_brief(handler.server.root, handler.path))
    except BriefEditError as exc:
        _error(handler, exc)


def handle_post_brief_edit(handler: WarRoomRequestHandler, body: dict[str, Any]) -> None:
    try:
        mr = submit_brief_edit(handler.server.root, body)
    except BriefEditError as exc:
        _error(handler, exc)
        return
    except (ValueError, GitError, OSError) as exc:
        handler._json_response(
            HTTPStatus.CONFLICT,
            {"ok": False, "error": str(exc), "code": "retryable", "reload": False},
        )
        return
    handler._json_response(
        HTTPStatus.CREATED,
        {
            "ok": True,
            "epic_id": str(body.get("epic_id") or body.get("work_id") or body.get("id")),
            "merge_request_url": mr.url,
            "provider": mr.forge,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
        },
    )


def handle_post_brief_cancel(handler: WarRoomRequestHandler, body: dict[str, Any]) -> None:
    try:
        mr = submit_brief_cancel(handler.server.root, body)
    except BriefEditError as exc:
        _error(handler, exc)
        return
    except (ValueError, GitError, OSError) as exc:
        handler._json_response(
            HTTPStatus.CONFLICT,
            {"ok": False, "error": str(exc), "code": "retryable", "reload": False},
        )
        return
    handler._json_response(
        HTTPStatus.CREATED,
        {
            "ok": True,
            "epic_id": str(body.get("epic_id") or body.get("work_id") or body.get("id")),
            "merge_request_url": mr.url,
        },
    )
