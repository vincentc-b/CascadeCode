"""Read projection and authenticated acknowledgement for Feature attention."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from cascade.board.errors import BoardError, SchemaError
from cascade.board.work_ids import parse_work_id_parts
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.feature_attention import (
    AttentionUnavailable,
    mark_feature_seen,
    project_feature_attention,
)
from cascade.workspace.integration_worktree import merged_board

if TYPE_CHECKING:
    from cascade.board.types import BoardIndex
    from cascade.feature_attention import AttentionSnapshot
    from cascade.war_room.server import WarRoomRequestHandler


MARK_SEEN_PATH = "/api/feature_attention/mark_seen"


def register_feature_attention_routes(
    handler_cls: type[WarRoomRequestHandler],
) -> None:
    handler_cls.register_post_route(MARK_SEEN_PATH, handle_mark_seen)


def attention_projection(
    snapshot: AttentionSnapshot,
    board: BoardIndex,
) -> dict[str, Any]:
    return project_feature_attention(snapshot, board)


def handle_mark_seen(
    handler: WarRoomRequestHandler,
    body: dict[str, Any],
) -> None:
    if set(body) != {"feature_id"}:
        handler._json_error(
            HTTPStatus.BAD_REQUEST, "body must contain exactly feature_id"
        )
        return
    feature_id = body.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id.strip():
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid feature_id")
        return
    feature_id = feature_id.strip()
    try:
        if parse_work_id_parts(feature_id).tier != "feature":
            raise ValueError("not a Feature ID")
    except (SchemaError, ValueError):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid feature_id")
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
            "Mark seen requires an authenticated local human",
        )
        return

    try:
        board = merged_board(handler.server.root)
    except (BoardError, OSError) as exc:
        handler._json_error(HTTPStatus.SERVICE_UNAVAILABLE, f"Board unavailable: {exc}")
        return
    meta = board.by_id.get(feature_id)
    if meta is None or meta.tier != "feature":
        handler._json_error(HTTPStatus.NOT_FOUND, "feature not found")
        return

    try:
        snapshot = mark_feature_seen(
            handler.server.root,
            feature_id,
            human.subject,
        )
    except KeyError:
        handler._json_error(
            HTTPStatus.SERVICE_UNAVAILABLE,
            "feature attention record unavailable",
        )
        return
    except AttentionUnavailable as exc:
        handler._json_error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
        return

    attention = project_feature_attention(snapshot, board)["features"][feature_id]
    handler._json_response(
        HTTPStatus.OK,
        {
            "ok": True,
            "feature_id": feature_id,
            "revision": snapshot.revision,
            "attention": attention,
        },
    )
