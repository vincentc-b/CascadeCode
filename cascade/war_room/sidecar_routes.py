"""Register War Room sidecar GET/POST routes (task_010). Import from server."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlparse

from datetime import datetime, timezone

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.workspace.doc_root import (
    BACKLOG_FEATURE_ATTACH_MESSAGE,
    is_backlog_feature_attach_refused,
    read_doc_resolved,
    repair_doc_worktree_for_attach,
)
from cascade.epic.wiring import accept_human_chat as accept_epic_human_chat
from cascade.feature.briefing import build_briefing_pack
from cascade.feature.wiring import accept_human_chat as accept_feature_human_chat
from cascade.war_room.chat_store import (
    TaskTierChatError,
    append_message,
    graph_id_is_valid,
    read_messages,
    remove_message,
)
from cascade.war_room.serialize import (
    briefing_pack_to_dict,
    briefing_stub_to_dict,
    message_to_dict,
)
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog import append_event, read_events
from cascade.watchdog.types import Event

if TYPE_CHECKING:
    from cascade.war_room.server import WarRoomRequestHandler


def _parse_graph_id_from_chat_path(path: str) -> str | None:
    prefix = "/api/chat/"
    if not path.startswith(prefix):
        return None
    graph_id = path[len(prefix) :].strip("/")
    if not graph_id or "/" in graph_id:
        return None
    return graph_id


def handle_get_toasts(handler: WarRoomRequestHandler) -> None:
    parsed = urlparse(handler.path)
    params = parse_qs(parsed.query, keep_blank_values=True)
    raw_after = (params.get("after") or ["0"])[0]
    try:
        after = int(raw_after)
    except (TypeError, ValueError):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid after")
        return
    events, new_offset = read_events("war_room", after, root=handler.server.root)
    toasts = events_to_toasts(events)
    handler._json_response(HTTPStatus.OK, {"toasts": toasts, "offset": new_offset})


def handle_get_chat(handler: WarRoomRequestHandler, graph_id: str) -> None:
    if not graph_id_is_valid(graph_id):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid graph_id")
        return
    messages = read_messages(graph_id, root=handler.server.root)
    handler._json_response(HTTPStatus.OK, messages)


def handle_post_chat(handler: WarRoomRequestHandler, graph_id: str, body: dict[str, Any]) -> None:
    if not graph_id_is_valid(graph_id):
        handler._json_error(HTTPStatus.BAD_REQUEST, "invalid graph_id")
        return
    if not handler.server.attachment.is_attached(graph_id):
        handler._json_error(HTTPStatus.FORBIDDEN, "not attached")
        return
    raw_body = body.get("body")
    if not isinstance(raw_body, str) or not raw_body.strip():
        handler._json_error(HTTPStatus.BAD_REQUEST, "missing body")
        return
    try:
        message = append_message(graph_id, raw_body, root=handler.server.root)
    except TaskTierChatError:
        handler._json_error(HTTPStatus.FORBIDDEN, "task tier has no chat sidecar")
        return
    except ValueError as exc:
        if "invalid graph_id" in str(exc):
            handler._json_error(HTTPStatus.BAD_REQUEST, "invalid graph_id")
            return
        handler._json_error(HTTPStatus.BAD_REQUEST, "missing body")
        return

    raw_model_id = body.get("model_id")
    model_id: str | None
    if isinstance(raw_model_id, str) and raw_model_id.strip():
        model_id = raw_model_id.strip()
    else:
        model_id = None
    try:
        from cascade.boss.model_turn import BOSS_CHAT_GRAPH_ID
        from cascade.boss.wiring import accept_boss_chat

        if graph_id == BOSS_CHAT_GRAPH_ID:
            accept_boss_chat(message, root=handler.server.root, model_id=model_id)
        else:
            accept_epic_human_chat(
                graph_id, message, root=handler.server.root, model_id=model_id
            )
            accept_feature_human_chat(
                graph_id, message, root=handler.server.root, model_id=model_id
            )
    except Exception:
        remove_message(graph_id, message["id"], root=handler.server.root)
        handler._json_error(HTTPStatus.INTERNAL_SERVER_ERROR, "graph ingest failed")
        return
    handler._json_response(HTTPStatus.ACCEPTED, message_to_dict(message))


def _emit_attachment_event(
    handler: WarRoomRequestHandler,
    *,
    graph_id: str,
    tier: str,
    event_type: str,
) -> None:
    append_event(
        graph_id,
        Event(
            type=event_type,
            ts=datetime.now(timezone.utc),
            payload={"graph_id": graph_id, "tier": tier},
            dest=graph_id,
        ),
        root=handler.server.root,
    )


def _attach_briefing_payload(handler: WarRoomRequestHandler, graph_id: str) -> dict | None:
    try:
        doc = read_doc_resolved(graph_id, root=handler.server.root)
    except NotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {graph_id}")
        return None
    if doc.meta.tier == "feature":
        pack = build_briefing_pack(graph_id, root=handler.server.root)
        return briefing_pack_to_dict(pack)
    if doc.meta.tier == "epic":
        return briefing_stub_to_dict(graph_id)
    return briefing_stub_to_dict(graph_id)


def handle_post_attach(handler: WarRoomRequestHandler, body: dict[str, Any]) -> None:
    graph_id = handler._require_work_id(body, key="graph_id")
    if graph_id is None:
        return
    if is_backlog_feature_attach_refused(graph_id, root=handler.server.root):
        handler._json_error(HTTPStatus.BAD_REQUEST, BACKLOG_FEATURE_ATTACH_MESSAGE)
        return
    repair_doc_worktree_for_attach(graph_id, root=handler.server.root)
    try:
        doc = read_doc_resolved(graph_id, root=handler.server.root)
    except NotFound:
        handler._json_error(HTTPStatus.NOT_FOUND, f"not found: {graph_id}")
        return
    handler.server.attachment.attach(graph_id)
    payload = _attach_briefing_payload(handler, graph_id)
    if payload is None:
        return
    _emit_attachment_event(
        handler, graph_id=graph_id, tier=doc.meta.tier, event_type="HumanAttached"
    )
    handler._json_response(HTTPStatus.OK, payload)


def handle_post_detach(handler: WarRoomRequestHandler, body: dict[str, Any]) -> None:
    graph_id = handler._require_work_id(body, key="graph_id")
    if graph_id is None:
        return
    tier = "unknown"
    try:
        doc = read_doc(graph_id, root=handler.server.root)
        tier = doc.meta.tier
    except NotFound:
        pass
    handler.server.attachment.detach(graph_id)
    if tier in ("epic", "feature", "task"):
        _emit_attachment_event(
            handler, graph_id=graph_id, tier=tier, event_type="HumanDetached"
        )
    handler._json_response(HTTPStatus.OK, {"ok": True})


def register_sidecar_routes(handler_cls: type[WarRoomRequestHandler]) -> None:
    handler_cls.register_get_route("/api/toasts", handle_get_toasts)
    handler_cls.register_post_route("/api/attach", handle_post_attach)
    handler_cls.register_post_route("/api/detach", handle_post_detach)
