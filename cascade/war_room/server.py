"""Loopback HTTP server for the War Room read and human-dispatch API.

Operator entry for War Room + watchdog is ``cascade up`` (see ``cascade.workspace.up``).
This module's ``__main__`` remains a read-only dev shortcut (HTTP only, no watchdog).

Ask-Boss enqueue (``POST /api/ask_boss_dispatch``): appends to queue dest ``boss``
with event type ``BossDispatchRequested``; does not call ``dispatch_*``.
"""

from __future__ import annotations

import json
import mimetypes
import socket
import sys
import threading
import time
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable

from cascade.board.errors import NotFound
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.integration_worktree import merged_board
from cascade.boss.epic_complete import confirm_epic_complete_result
from cascade.boss.graph import install_boss_consumer
from cascade.boss.merge import merge_task_branch
from cascade.boss.orphans import detect_orphans
from cascade.boss.rollup import on_task_merged
from cascade.boss.view import BossView, compute_boss_view
from cascade.epic.boot import install_epic_boot_hook
from cascade.feature.boot import install_feature_boot_hook
from cascade.task.boot import install_task_boot_hook
from cascade.epic.wiring import load_epic_tools
from cascade.feature.wiring import load_feature_tools
from cascade.task.wiring import install_task_wiring
from cascade.war_room.attachment import AttachmentState
from cascade.war_room.serialize import (
    board_view_from_index,
    dispatch_result_to_dict,
    event_to_dict,
    flight_report_to_dict,
    work_doc_to_dict,
)
from cascade.workspace.flight import get_cached_flight_report
from cascade.war_room.amendment_routes import (
    amendment_get_path_exists,
    register_amendment_routes,
    try_handle_amendment_get,
    try_handle_amendment_post,
)
from cascade.war_room.provider_routes import (
    provider_api_path_exists,
    register_provider_routes,
    try_handle_provider_post,
)
from cascade.war_room.review_routes import register_review_routes
from cascade.war_room.room_settings_routes import (
    register_room_settings_routes,
    room_settings_api_path_exists,
    try_handle_room_settings_get,
    try_handle_room_settings_post,
)
from cascade.war_room.sidecar_routes import _parse_graph_id_from_chat_path, register_sidecar_routes
from cascade.war_room.views import render_plan_page, render_war_room_page
from cascade.comments import section_slug
from cascade.comments.store import comment as post_comment
from cascade.comments.store import (
    CommentNotFound,
    CommentStoreError,
    NotARoot,
    read_comments,
    reply_comment,
    resolve_comment,
)
from cascade.war_room.serialize import comment_to_dict
from cascade.workspace.kickoff import deferred_kickoffs
from cascade.watchdog import activate_epic, append_event, dispatch_feature, dispatch_task
from cascade.watchdog.types import Event
from cascade.board.errors import BoardError, GitError
from cascade.workspace.errors import WorkspaceError

_STATIC_DIR = Path(__file__).resolve().parent / "static"
_SKILLS_INVALID = object()
REQUEST_DEADLINE_S = 10.0
EPIC_CLOSE_DEADLINE_S = 60.0
APPROVAL_DEADLINE_S = 60.0
MAX_CONCURRENT_REQUESTS = 16

_APPROVAL_POST_PATHS = frozenset(
    {"/api/approve_epic_plan", "/api/approve_feature"}
)


def _boss_view_to_dict(view: BossView) -> dict[str, object]:
    return {
        "dispatchable_features": list(view.dispatchable_features),
        "dispatchable_tasks": list(view.dispatchable_tasks),
        "slots_free": view.slots_free,
        "failed_tasks": list(view.failed_tasks),
    }


def assert_loopback_host(host: str) -> str:
    """Return `host` if it is a loopback bind address; otherwise raise ValueError."""

    if host.strip() != "127.0.0.1":
        raise ValueError(
            f"war room server must bind to loopback (127.0.0.1), not {host!r}"
        )
    return host


class WarRoomHTTPServer(ThreadingHTTPServer):
    """HTTPServer scoped to a repo root. One request cannot block the rest."""

    daemon_threads = True
    allow_reuse_address = True
    request_queue_size = 64

    def __init__(
        self,
        server_address: tuple[str, int],
        RequestHandlerClass: type[BaseHTTPRequestHandler],
        *,
        root: Path,
    ) -> None:
        host, _port = server_address
        assert_loopback_host(host)
        self.root = Path(root).resolve()
        install_epic_boot_hook(self.root)
        install_feature_boot_hook(self.root)
        install_task_boot_hook(self.root)
        install_task_wiring(self.root)
        install_boss_consumer(self.root)
        from cascade.completion_reconcile import reconcile_completion_with_prompts

        reconcile_completion_with_prompts(root=self.root)
        load_epic_tools()
        load_feature_tools()
        self.attachment = AttachmentState()
        self._request_slots = threading.BoundedSemaphore(MAX_CONCURRENT_REQUESTS)
        super().__init__(server_address, RequestHandlerClass)

    def process_request(self, request: socket.socket, client_address: tuple[str, int]) -> None:
        """Bound handler work so timed-out clients cannot create unlimited threads."""

        if not self._request_slots.acquire(blocking=False):
            body = b'{"error":"server busy"}'
            response = (
                b"HTTP/1.1 503 Service Unavailable\r\n"
                b"Content-Type: application/json; charset=utf-8\r\n"
                b"Cache-Control: no-store\r\n"
                b"Retry-After: 1\r\n"
                + f"Content-Length: {len(body)}\r\n".encode("ascii")
                + b"Connection: close\r\n\r\n"
                + body
            )
            try:
                request.sendall(response)
            except OSError:
                pass
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self._request_slots.release()
            raise

    def process_request_thread(
        self,
        request: socket.socket,
        client_address: tuple[str, int],
    ) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._request_slots.release()


GetRoute = Callable[["WarRoomRequestHandler"], None]
PostRoute = Callable[["WarRoomRequestHandler", dict[str, Any]], None]


class WarRoomRequestHandler(BaseHTTPRequestHandler):
    """GET/POST router. ``register_*_route`` adds paths for later tasks."""

    server: WarRoomHTTPServer
    # HTTP/1.1 so Expect: 100-continue is answered. Browsers withhold a large
    # POST body (a pasted API token) until they see 100 Continue. HTTP/1.0
    # never sends that, the 10s deadline then closes the socket, and fetch
    # rejects with "Failed to fetch".
    protocol_version = "HTTP/1.1"
    timeout = REQUEST_DEADLINE_S
    _extra_get_routes: dict[str, GetRoute] = {}
    _extra_post_routes: dict[str, PostRoute] = {}

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            "%s [%s] %s\n" % (self.log_date_time_string(), self.address_string(), format % args)
        )
        sys.stderr.flush()

    def handle_expect_100(self) -> bool:
        """Send 100 Continue without the final-response ``Connection: close``.

        ``end_headers`` forces that close so the browser does not idle on
        keep-alive. Applying it to the interim 100 response tells the client
        to drop the socket before the token body is sent.
        """

        self.send_response_only(HTTPStatus.CONTINUE)
        BaseHTTPRequestHandler.end_headers(self)
        return True

    def handle(self) -> None:
        """Serve one connection, enforcing the deadline for its lifecycle route."""

        started = time.monotonic()
        finished = threading.Event()

        def interrupt() -> None:
            if finished.wait(REQUEST_DEADLINE_S):
                return
            path = getattr(self, "path", "").split("?", 1)[0]
            deadline = REQUEST_DEADLINE_S
            if getattr(self, "command", "") == "POST":
                if path == "/api/confirm_epic_complete":
                    deadline = EPIC_CLOSE_DEADLINE_S
                elif path in _APPROVAL_POST_PATHS:
                    deadline = APPROVAL_DEADLINE_S
            if deadline > REQUEST_DEADLINE_S and finished.wait(
                deadline - REQUEST_DEADLINE_S
            ):
                return
            self.log_error(
                "deadline exceeded after %.1fs; closing connection",
                deadline,
            )
            try:
                self.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass

        watchdog = threading.Thread(target=interrupt, name="war-room-deadline", daemon=True)
        watchdog.start()
        try:
            super().handle()
        finally:
            finished.set()
            self.log_message(
                "done %s %s %.3fs",
                getattr(self, "command", "-"),
                getattr(self, "path", "-"),
                time.monotonic() - started,
            )

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in self._exact_get_routes():
            self._exact_get_routes()[path](self)
            return
        chat_id = _parse_graph_id_from_chat_path(path)
        if chat_id is not None:
            from cascade.war_room.sidecar_routes import handle_get_chat

            handle_get_chat(self, chat_id)
            return
        if path.startswith("/api/doc/"):
            work_id = path.removeprefix("/api/doc/").strip("/")
            if not work_id or "/" in work_id:
                self._json_error(HTTPStatus.NOT_FOUND, "not found")
                return
            self._handle_doc(work_id)
            return
        if path.startswith("/api/comments/"):
            doc_id = path.removeprefix("/api/comments/").strip("/")
            if not doc_id or "/" in doc_id:
                self._json_error(HTTPStatus.NOT_FOUND, "not found")
                return
            self._handle_comments_list(doc_id)
            return
        if path.startswith("/plan/"):
            work_id = path.removeprefix("/plan/").strip("/")
            if not work_id or "/" in work_id:
                self._serve_plan_not_found()
                return
            self._serve_plan_page(work_id)
            return
        if try_handle_amendment_get(self):
            return
        if try_handle_room_settings_get(self):
            return
        if path in ("/", "/war-room"):
            self._serve_war_room_html()
            return
        if path.startswith("/static/"):
            self._serve_static(path.removeprefix("/static/"))
            return
        self._json_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        # Model turns outlive REQUEST_DEADLINE_S; run them off the request thread.
        with deferred_kickoffs():
            self._do_post()

    def _do_post(self) -> None:
        path = self.path.split("?", 1)[0]
        chat_id = _parse_graph_id_from_chat_path(path)
        if chat_id is not None:
            body = self._read_json_object()
            if body is None:
                return
            from cascade.war_room.sidecar_routes import handle_post_chat

            handle_post_chat(self, chat_id, body)
            return
        body = self._read_json_object()
        if body is None:
            return
        if try_handle_amendment_post(self, body):
            return
        if try_handle_provider_post(self, body):
            return
        if try_handle_room_settings_post(self, body):
            return
        routes = self._exact_post_routes()
        if path not in routes:
            if self._path_exists_for_get(path):
                self._method_not_allowed()
            else:
                self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        routes[path](self, body)

    def do_PUT(self) -> None:
        self._method_not_allowed()

    def do_DELETE(self) -> None:
        self._method_not_allowed()

    def do_PATCH(self) -> None:
        self._method_not_allowed()

    @classmethod
    def _exact_get_routes(cls) -> dict[str, GetRoute]:
        routes = {
            "/api/board": lambda h: h._handle_board(),
            "/api/brief/template": lambda h: h._handle_brief_template(),
            "/api/boss_view": lambda h: h._handle_boss_view(),
            "/api/orphans": lambda h: h._handle_orphans(),
            "/api/flight": lambda h: h._handle_flight(),
        }
        routes.update(cls._extra_get_routes)
        return routes

    @classmethod
    def register_get_route(cls, path: str, handler: GetRoute) -> None:
        """Register a GET handler for an exact path (for task_010+)."""

        cls._extra_get_routes[path] = handler

    @classmethod
    def _exact_post_routes(cls) -> dict[str, PostRoute]:
        routes: dict[str, PostRoute] = {
            "/api/activate_epic": lambda h, b: h._handle_activate_epic(b),
            "/api/dispatch_feature": lambda h, b: h._handle_dispatch_feature(b),
            "/api/dispatch_task": lambda h, b: h._handle_dispatch_task(b),
            "/api/merge_task_branch": lambda h, b: h._handle_merge_task_branch(b),
            "/api/update_integration_branch": lambda h, b: h._handle_update_integration_branch(
                b
            ),
            "/api/ask_boss_dispatch": lambda h, b: h._handle_ask_boss_dispatch(b),
            "/api/confirm_epic_complete": lambda h, b: h._handle_confirm_epic_complete(b),
            "/api/boss_drain": lambda h, b: h._handle_boss_drain(b),
            "/api/comment": lambda h, b: h._handle_comment(b),
            "/api/comment/resolve": lambda h, b: h._handle_comment_resolve(b),
            "/api/briefs": lambda h, b: h._handle_create_brief(b),
            "/api/sync/pull": lambda h, b: h._handle_sync_pull(b),
            "/api/approve_epic_plan": lambda h, b: h._handle_approve_epic_plan(b),
            "/api/approve_feature": lambda h, b: h._handle_approve_feature(b),
        }
        routes.update(cls._extra_post_routes)
        return routes

    @classmethod
    def register_post_route(cls, path: str, handler: PostRoute) -> None:
        """Register a POST handler for an exact path (for task_010+)."""

        cls._extra_post_routes[path] = handler

    def _handle_activate_epic(self, body: dict[str, Any]) -> None:
        work_id = self._require_work_id(body)
        if work_id is None:
            return
        result = activate_epic(work_id, "human", root=self.server.root)
        self._json_response(HTTPStatus.OK, dispatch_result_to_dict(result))

    def _handle_brief_template(self) -> None:
        from cascade.briefs import brief_template

        try:
            payload = brief_template(self.server.root)
        except (ValueError, OSError) as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json_response(HTTPStatus.OK, payload)

    def _handle_create_brief(self, body: dict[str, Any]) -> None:
        from cascade.briefs import create_brief

        try:
            epic_id, mr = create_brief(self.server.root, body)
        except (ValueError, GitError, OSError) as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json_response(
            HTTPStatus.CREATED,
            {
                "ok": True,
                "epic_id": epic_id,
                "merge_request_url": mr.url,
                "provider": mr.forge,
            },
        )

    def _handle_sync_pull(self, body: dict[str, Any]) -> None:
        from cascade.automation import sync_briefs

        try:
            payload = sync_briefs(self.server.root, force=True)
        except (ValueError, BoardError, WorkspaceError, OSError) as exc:
            self._json_error(HTTPStatus.CONFLICT, str(exc))
            return
        self._json_response(HTTPStatus.OK, payload)

    def _handle_approve_epic_plan(self, body: dict[str, Any]) -> None:
        epic_id = self._require_work_id(body)
        if epic_id is None:
            return
        from cascade.approvals import approve_epic_plan

        try:
            payload = approve_epic_plan(epic_id, root=self.server.root)
        except (ValueError, BoardError, OSError) as exc:
            self._json_error(HTTPStatus.CONFLICT, str(exc))
            return
        self._json_response(HTTPStatus.OK, payload)

    def _handle_approve_feature(self, body: dict[str, Any]) -> None:
        feature_id = self._require_work_id(body)
        if feature_id is None:
            return
        from cascade.approvals import approve_feature

        try:
            payload = approve_feature(feature_id, root=self.server.root)
        except (ValueError, BoardError, OSError) as exc:
            self._json_error(HTTPStatus.CONFLICT, str(exc))
            return
        self._json_response(HTTPStatus.OK, payload)

    def _handle_dispatch_feature(self, body: dict[str, Any]) -> None:
        work_id = self._require_work_id(body)
        if work_id is None:
            return
        result = dispatch_feature(work_id, "human", root=self.server.root)
        self._json_response(HTTPStatus.OK, dispatch_result_to_dict(result))

    def _handle_dispatch_task(self, body: dict[str, Any]) -> None:
        work_id = self._require_work_id(body)
        if work_id is None:
            return
        skills = self._parse_optional_skills(body)
        if skills is _SKILLS_INVALID:
            return
        result = dispatch_task(work_id, "human", skills=skills, root=self.server.root)
        self._json_response(HTTPStatus.OK, dispatch_result_to_dict(result))

    def _handle_update_integration_branch(self, body: dict[str, Any]) -> None:
        from cascade.war_room.branch_sync import (
            branch_sync_update_to_dict,
            run_branch_sync_update,
            sync_failure_http_status,
        )

        work_id = self._require_work_id(body)
        if work_id is None:
            return
        result = run_branch_sync_update(work_id, root=self.server.root)
        payload = branch_sync_update_to_dict(result, work_id=work_id)
        if result.ok:
            self._json_response(HTTPStatus.OK, payload)
            return
        self._json_response(sync_failure_http_status(result.reason), payload)

    def _handle_merge_task_branch(self, body: dict[str, Any]) -> None:
        from cascade.war_room.branch_sync import (
            lifecycle_merge_failure_payload,
            sync_failure_http_status,
        )

        task_id = self._require_work_id(body)
        if task_id is None:
            return
        result = merge_task_branch(task_id, root=self.server.root)
        if not result.ok:
            status = sync_failure_http_status(result.reason)
            payload = lifecycle_merge_failure_payload(
                reason=result.reason,
                conflict_paths=result.conflict_paths,
                branch=result.branch,
                task_id=task_id,
            )
            self._json_response(status, payload)
            return
        on_task_merged(task_id, root=self.server.root)
        self._json_response(
            HTTPStatus.OK,
            {
                "ok": True,
                "merge_sha": result.merge_sha,
                "branch": result.branch,
                "task_id": task_id,
            },
        )

    def _handle_confirm_epic_complete(self, body: dict[str, Any]) -> None:
        epic_id = self._require_work_id(body)
        if epic_id is None:
            return
        result = confirm_epic_complete_result(epic_id, "human", root=self.server.root)
        if result.ok:
            self._json_response(HTTPStatus.OK, {"ok": True, "epic_id": epic_id})
            return
        from cascade.war_room.branch_sync import actionable_sync_failure_payload

        payload: dict[str, Any] = {
            "ok": False,
            "reason": result.reason or "close_failed",
            "epic_id": epic_id,
        }
        if result.blocker_ids:
            payload["blocker_ids"] = list(result.blocker_ids)
        if result.reason == "open_human_comments":
            payload["plan_url"] = f"/plan/{epic_id}#plan-comments"
        sync_payload = actionable_sync_failure_payload(
            reason=result.reason,
            conflict_paths=result.conflict_paths,
        )
        for key in ("guidance", "conflict_paths", "merge_aborted"):
            if key in sync_payload:
                payload[key] = sync_payload[key]
        self._json_response(
            HTTPStatus.OK,
            payload,
        )

    def _handle_boss_drain(self, body: dict[str, Any]) -> None:
        feature_id = body.get("feature_id")
        if not isinstance(feature_id, str) or not feature_id.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing feature_id")
            return
        feature_id = feature_id.strip()
        event = Event(
            type="BossDrainRequested",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id, "by": "human"},
            dest="boss",
        )
        append_event("boss", event, root=self.server.root)
        self._json_response(
            HTTPStatus.ACCEPTED,
            {"ok": True, "event": event_to_dict(event)},
        )

    def _handle_boss_view(self) -> None:
        view = compute_boss_view(root=self.server.root)
        self._json_response(HTTPStatus.OK, _boss_view_to_dict(view))

    def _handle_orphans(self) -> None:
        records = detect_orphans(root=self.server.root)
        payload = [
            {"kind": record.kind, "work_id": record.work_id, "message": record.message}
            for record in records
        ]
        self._json_response(HTTPStatus.OK, {"orphans": payload})

    def _handle_flight(self) -> None:
        report = get_cached_flight_report(root=self.server.root)
        self._json_response(
            HTTPStatus.OK,
            flight_report_to_dict(report, root=self.server.root),
        )

    def _handle_comment(self, body: dict[str, Any]) -> None:
        doc_id = body.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing doc_id")
            return
        text = body.get("body")
        if not isinstance(text, str) or not text.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing body")
            return
        parent = body.get("parent")
        if parent is not None:
            if not isinstance(parent, str) or not parent.strip():
                self._json_error(HTTPStatus.BAD_REQUEST, "invalid parent")
                return
            try:
                comment_id = reply_comment(
                    doc_id.strip(),
                    parent.strip(),
                    text,
                    author="human",
                    root=self.server.root,
                )
            except CommentNotFound:
                self._json_error(HTTPStatus.NOT_FOUND, "parent not found")
                return
            except CommentStoreError as exc:
                self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._json_response(
                HTTPStatus.ACCEPTED,
                {"ok": True, "comment_id": comment_id},
            )
            return

        section_raw = body.get("section")
        if not isinstance(section_raw, str) or not section_raw.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing section")
            return
        section = section_slug(section_raw)
        if not section:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing section")
            return
        anchor = body.get("anchor")
        if anchor is not None and not isinstance(anchor, str):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid anchor")
            return
        blocking = body.get("blocking", False)
        if not isinstance(blocking, bool):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid blocking")
            return
        line_start = body.get("line_start")
        if line_start is not None and (type(line_start) is not int or line_start < 1):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid line_start")
            return
        line_end = body.get("line_end")
        if line_end is not None and (type(line_end) is not int or line_end < 1):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid line_end")
            return
        if line_start is not None and line_end is not None and line_end < line_start:
            self._json_error(HTTPStatus.BAD_REQUEST, "line_end before line_start")
            return
        doc_sha = body.get("doc_sha")
        if doc_sha is not None and not isinstance(doc_sha, str):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid doc_sha")
            return
        blocks_raw = body.get("blocks")
        blocks: list[str] | None = None
        if blocks_raw is not None:
            if not isinstance(blocks_raw, list) or any(
                not isinstance(item, str) for item in blocks_raw
            ):
                self._json_error(HTTPStatus.BAD_REQUEST, "invalid blocks")
                return
            blocks = list(blocks_raw)
        try:
            comment_id = post_comment(
                doc_id.strip(),
                section,
                text,
                anchor=anchor,
                blocking=blocking,
                line_start=line_start,
                line_end=line_end,
                doc_sha=doc_sha,
                blocks=blocks,
                author="human",
                root=self.server.root,
                is_attached=self.server.attachment.is_attached,
            )
        except CommentStoreError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json_response(
            HTTPStatus.ACCEPTED,
            {"ok": True, "comment_id": comment_id},
        )

    def _handle_comment_resolve(self, body: dict[str, Any]) -> None:
        doc_id = body.get("doc_id")
        if not isinstance(doc_id, str) or not doc_id.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing doc_id")
            return
        comment_id = body.get("comment_id")
        if not isinstance(comment_id, str) or not comment_id.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing comment_id")
            return
        try:
            resolve_comment(
                doc_id.strip(),
                comment_id.strip(),
                author="human",
                root=self.server.root,
            )
        except CommentNotFound:
            self._json_error(HTTPStatus.NOT_FOUND, "comment not found")
            return
        except NotARoot:
            self._json_error(HTTPStatus.BAD_REQUEST, "NotARoot")
            return
        except CommentStoreError as exc:
            self._json_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._json_response(
            HTTPStatus.ACCEPTED,
            {"ok": True, "comment_id": comment_id.strip()},
        )

    def _handle_comments_list(self, doc_id: str) -> None:
        try:
            doc = read_doc_resolved(doc_id, root=self.server.root)
        except NotFound:
            self._json_error(HTTPStatus.NOT_FOUND, f"not found: {doc_id}")
            return
        if doc.meta.tier not in ("epic", "feature"):
            self._json_error(
                HTTPStatus.BAD_REQUEST,
                "comments are supported for epic and feature plans only",
            )
            return
        rows = read_comments(doc_id, root=self.server.root)
        self._json_response(
            HTTPStatus.OK,
            {"doc_id": doc_id, "comments": [comment_to_dict(row) for row in rows]},
        )

    def _handle_ask_boss_dispatch(self, body: dict[str, Any]) -> None:
        kind = body.get("kind")
        if kind not in ("feature", "task"):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid kind")
            return
        work_id = self._require_work_id(body)
        if work_id is None:
            return
        event = Event(
            type="BossDispatchRequested",
            ts=datetime.now(timezone.utc),
            payload={"kind": kind, "id": work_id, "by": "human"},
            dest="boss",
        )
        append_event("boss", event, root=self.server.root)
        self._json_response(
            HTTPStatus.ACCEPTED,
            {"ok": True, "event": event_to_dict(event)},
        )

    def _read_json_object(self) -> dict[str, Any] | None:
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            length = 0
        raw = self.rfile.read(length) if length else b""
        if not raw:
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid json")
            return None
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid json")
            return None
        if not isinstance(parsed, dict):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid json")
            return None
        return parsed

    def _require_work_id(self, body: dict[str, Any], *, key: str = "id") -> str | None:
        if key not in body or body[key] is None:
            self._json_error(HTTPStatus.BAD_REQUEST, "missing id")
            return None
        work_id = body[key]
        if not isinstance(work_id, str) or not work_id.strip():
            self._json_error(HTTPStatus.BAD_REQUEST, "missing id")
            return None
        return work_id.strip()

    def _parse_optional_skills(self, body: dict[str, Any]) -> list[Path] | None | object:
        if "skills" not in body or body["skills"] is None:
            return None
        raw = body["skills"]
        if not isinstance(raw, list):
            self._json_error(HTTPStatus.BAD_REQUEST, "invalid skills")
            return _SKILLS_INVALID
        paths: list[Path] = []
        for item in raw:
            if not isinstance(item, str) or not item.strip():
                self._json_error(HTTPStatus.BAD_REQUEST, "invalid skills")
                return _SKILLS_INVALID
            paths.append(Path(item.strip()))
        return paths

    def _handle_board(self) -> None:
        board = merged_board(self.server.root)
        payload = board_view_from_index(board, root=self.server.root)
        self._json_response(HTTPStatus.OK, payload)

    def _handle_doc(self, work_id: str) -> None:
        try:
            doc = read_doc_resolved(work_id, root=self.server.root)
        except NotFound:
            self._json_error(HTTPStatus.NOT_FOUND, f"not found: {work_id}")
            return
        self._json_response(HTTPStatus.OK, work_doc_to_dict(doc))

    def end_headers(self) -> None:
        """Finish the response and tell the browser not to wait on this connection."""

        self.close_connection = True
        if getattr(self, "request_version", "HTTP/0.9") != "HTTP/0.9":
            buffered = getattr(self, "_headers_buffer", None) or []
            if not any(line.lower().startswith(b"connection:") for line in buffered):
                self.send_header("Connection", "close")
        super().end_headers()

    def _send_html(self, status: HTTPStatus, html: str) -> None:
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_war_room_html(self) -> None:
        self._send_html(HTTPStatus.OK, render_war_room_page(root=self.server.root))

    def _serve_plan_not_found(self) -> None:
        html = (
            "<!DOCTYPE html><html lang=\"en\"><head>"
            "<meta charset=\"utf-8\" /><title>Plan not found</title></head><body>"
            "<p>Plan not found.</p>"
            "<p><a href=\"/war-room\">Back to War Room</a></p>"
            "</body></html>"
        )
        self._send_html(HTTPStatus.NOT_FOUND, html)

    def _serve_plan_page(self, work_id: str) -> None:
        try:
            read_doc_resolved(work_id, root=self.server.root)
        except NotFound:
            self._serve_plan_not_found()
            return
        self._send_html(HTTPStatus.OK, render_plan_page(work_id))

    def _serve_static(self, rel: str) -> None:
        safe = Path(rel)
        if safe.is_absolute() or ".." in safe.parts:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        static_root = _STATIC_DIR.resolve()
        file_path = (static_root / safe).resolve()
        try:
            file_path.relative_to(static_root)
        except ValueError:
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        if not file_path.is_file():
            self._json_error(HTTPStatus.NOT_FOUND, "not found")
            return
        content_type, _ = mimetypes.guess_type(str(file_path))
        body = file_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_response(self, status: HTTPStatus, payload: Any) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json_error(self, status: HTTPStatus, message: str) -> None:
        self._json_response(status, {"error": message})

    def _path_exists_for_get(self, path: str) -> bool:
        if path in self._exact_get_routes():
            return True
        if _parse_graph_id_from_chat_path(path) is not None:
            return True
        if path.startswith("/api/doc/"):
            work_id = path.removeprefix("/api/doc/").strip("/")
            return bool(work_id and "/" not in work_id)
        if path.startswith("/api/comments/"):
            doc_id = path.removeprefix("/api/comments/").strip("/")
            return bool(doc_id and "/" not in doc_id)
        if path in ("/", "/war-room"):
            return True
        if path.startswith("/plan/"):
            work_id = path.removeprefix("/plan/").strip("/")
            return bool(work_id and "/" not in work_id)
        if path.startswith("/static/"):
            rel = path.removeprefix("/static/")
            safe = Path(rel)
            if safe.is_absolute() or ".." in safe.parts:
                return False
            static_root = _STATIC_DIR.resolve()
            file_path = (static_root / safe).resolve()
            try:
                file_path.relative_to(static_root)
            except ValueError:
                return False
            return file_path.is_file()
        if amendment_get_path_exists(path, root=self.server.root):
            return True
        if provider_api_path_exists(path):
            return True
        if room_settings_api_path_exists(path):
            return True
        return False

    def _method_not_allowed(self) -> None:
        self._json_error(HTTPStatus.METHOD_NOT_ALLOWED, "method not allowed")


def serve(
    *,
    root: Path,
    host: str = "127.0.0.1",
    port: int = 8765,
    handler_class: type[WarRoomRequestHandler] = WarRoomRequestHandler,
) -> WarRoomHTTPServer:
    """Create and return a configured server (caller runs serve_forever or thread)."""

    assert_loopback_host(host)
    return WarRoomHTTPServer((host, port), handler_class, root=root)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Cascade War Room (read API)")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    server = serve(root=args.root, host=args.host, port=args.port)
    print(f"War Room http://{args.host}:{args.port}/ (root={server.root})")
    server.serve_forever()


register_sidecar_routes(WarRoomRequestHandler)
register_amendment_routes(WarRoomRequestHandler)
register_provider_routes(WarRoomRequestHandler)
register_review_routes(WarRoomRequestHandler)
register_room_settings_routes(WarRoomRequestHandler)

if __name__ == "__main__":
    main()
