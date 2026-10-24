"""War Room loopback HTTP read API."""

from __future__ import annotations

import http.client
import json
import socket
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from cascade.war_room.server import (
    WarRoomHTTPServer,
    WarRoomRequestHandler,
    assert_loopback_host,
    serve,
)
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, dict | str, dict[str, str]]:
    with urllib.request.urlopen(url) as resp:
        raw = resp.read()
        headers = dict(resp.headers)
        if resp.headers.get_content_type() == "application/json":
            return resp.status, json.loads(raw.decode()), headers
        return resp.status, raw.decode(), headers


def _get_expect_error(url: str) -> tuple[int, dict]:
    try:
        _get(url)
    except urllib.error.HTTPError as exc:
        body = json.loads(exc.read().decode())
        return exc.code, body
    raise AssertionError("expected HTTP error")


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="feat_001", title="Beta", tier="feature", parent="epic_001", status="backlog")
    add_doc(root, id="task_001", title="Alpha", tier="task", parent="feat_001", status="active")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_assert_loopback_rejects_public_bind(tmp_path):
    with pytest.raises(ValueError, match="loopback"):
        assert_loopback_host("0.0.0.0")
    with pytest.raises(ValueError, match="loopback"):
        assert_loopback_host("localhost")
    with pytest.raises(ValueError, match="loopback"):
        assert_loopback_host("::1")
    from http.server import BaseHTTPRequestHandler

    with pytest.raises(ValueError, match="loopback"):
        WarRoomHTTPServer(
            ("0.0.0.0", 0),
            BaseHTTPRequestHandler,
            root=make_repo(tmp_path, git=False),
        )


def test_server_binds_loopback(war_room_server):
    _base, _root, server = war_room_server
    host, _port = server.server_address
    assert host == "127.0.0.1"


def test_http_listener_starts_without_completion_reconciliation(
    tmp_path, monkeypatch
):
    root = make_repo(tmp_path, git=False)

    def blocked_reconciliation(*_args, **_kwargs):
        raise AssertionError("HTTP startup must not run completion reconciliation")

    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        blocked_reconciliation,
    )
    server = serve(root=root, host="127.0.0.1", port=_free_port())
    server.server_close()


def test_get_board_shape(war_room_server):
    base, _root, _server = war_room_server
    status, payload, _headers = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    assert set(payload) == {"epics", "features", "tasks", "board"}
    assert payload["board"]["completed_epic_display_limit"] == 10
    for tier in ("epics", "features", "tasks"):
        assert set(payload[tier]) == {"1_backlog", "2_active", "3_completed"}
    tasks_active = payload["tasks"]["2_active"]
    assert len(tasks_active) == 1
    assert tasks_active[0]["id"] == "task_001"
    assert tasks_active[0]["created"] == "2026-10-09"
    assert "path" in tasks_active[0]


def test_get_board_marks_approved_epic(war_room_server):
    base, root, _server = war_room_server
    from cascade.board.store import read_doc, write_doc
    from datetime import datetime, timezone

    doc = read_doc("epic_001", root=root)
    doc.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)

    status, payload, _headers = _get(f"{base}/api/board")

    assert status == HTTPStatus.OK
    epic = payload["epics"]["1_backlog"][0]
    assert epic["id"] == "epic_001"
    assert epic["plan_approved"] is True


def test_get_doc_and_missing(war_room_server):
    base, _root, _server = war_room_server
    status, doc, _ = _get(f"{base}/api/doc/task_001")
    assert status == HTTPStatus.OK
    assert doc["meta"]["id"] == "task_001"
    assert "body" in doc
    assert "## Acceptance criteria" in doc["body"]

    code, err = _get_expect_error(f"{base}/api/doc/task_999")
    assert code == HTTPStatus.NOT_FOUND
    assert "error" in err


def test_get_api_health_reads_supervisor_status(war_room_server):
    base, root, _server = war_room_server
    from cascade.workspace.supervisor_status import utc_now_iso, write_supervisor_status

    now = utc_now_iso()
    write_supervisor_status(
        root,
        {
            "state": "update_blocked",
            "worker_pid": 4242,
            "restart_count": 0,
            "last_error": {"message": "preflight failed"},
            "next_action": "Fix the syntax error and save again.",
            "trunk_lock_warning": None,
            "since": now,
            "updated_at": now,
        },
    )
    status, payload, _ = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert payload["state"] == "update_blocked"
    assert payload["last_error"]["message"] == "preflight failed"
    assert payload["next_action"] == "Fix the syntax error and save again."
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is False


def test_get_api_health_null_when_status_file_missing(war_room_server):
    base, _root, _server = war_room_server
    status, payload, _ = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert payload is not None
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is False


def test_get_api_health_exposes_readiness_projection_shape(war_room_server):
    from cascade.workspace.supervisor_readiness import record_loop_success

    base, _root, _server = war_room_server
    record_loop_success("watchdog", at="2026-01-01T00:00:01+00:00")
    status, payload, _ = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert set(payload.keys()) >= {"http", "automation", "loops", "recovery"}
    assert payload["loops"]["watchdog"]["last_success_at"] == "2026-01-01T00:00:01+00:00"
    assert "phase" in payload["automation"]
    assert "degraded_reasons" in payload["automation"]


def test_get_api_health_served_while_draining(war_room_server):
    base, root, server = war_room_server
    from cascade.workspace.drain import reset_drain_for_tests
    from cascade.workspace.supervisor_status import utc_now_iso, write_supervisor_status

    now = utc_now_iso()
    write_supervisor_status(
        root,
        {
            "state": "draining",
            "worker_pid": 1,
            "restart_count": 0,
            "last_error": None,
            "next_action": None,
            "trunk_lock_warning": None,
            "since": now,
            "updated_at": now,
        },
    )
    server._draining.set()
    try:
        status, payload, _ = _get(f"{base}/api/health")
        assert status == HTTPStatus.OK
        assert payload["state"] == "draining"
        req = urllib.request.Request(
            f"{base}/api/comment",
            method="POST",
            data=b'{"id":"epic_001","body":"probe"}',
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as exc_info:
            urllib.request.urlopen(req)
        assert exc_info.value.code == HTTPStatus.SERVICE_UNAVAILABLE
        assert json.loads(exc_info.value.read().decode())["error"] == "updating"
    finally:
        server._draining.clear()
        reset_drain_for_tests()


def test_get_brief_template(war_room_server):
    base, _root, _server = war_room_server
    status, payload, _ = _get(f"{base}/api/brief/template")
    assert status == HTTPStatus.OK
    assert payload["provider"] == "cursor"
    assert payload["providers"] == ["cursor", "claude", "codex"]
    assert set(payload["provider_models"]) == {"cursor", "claude", "codex"}
    assert set(payload["suggestions"]) == {"epic_manager", "epic_architect"}


def test_get_index_shell(war_room_server):
    base, _root, _server = war_room_server
    status, html, headers = _get(f"{base}/")
    assert status == HTTPStatus.OK
    assert "text/html" in headers.get("Content-type", headers.get("Content-Type", ""))
    assert headers.get("Connection", headers.get("connection", "")).lower() == "close"
    assert "War Room" in html


def test_unknown_route_and_method(war_room_server):
    base, _root, _server = war_room_server
    code, err = _get_expect_error(f"{base}/api/nope")
    assert code == HTTPStatus.NOT_FOUND

    req = urllib.request.Request(
        f"{base}/api/nope",
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.NOT_FOUND
    assert json.loads(exc_info.value.read().decode())["error"] == "not found"

    req = urllib.request.Request(f"{base}/api/board", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.METHOD_NOT_ALLOWED


def test_slow_request_is_interrupted_within_deadline(tmp_path):
    def _slow(handler: WarRoomRequestHandler) -> None:
        time.sleep(30)
        handler._json_response(HTTPStatus.OK, {"ok": True})

    WarRoomRequestHandler.register_get_route("/api/slow-deadline", _slow)
    root = make_repo(tmp_path)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    started = time.monotonic()
    try:
        with pytest.raises((urllib.error.URLError, http.client.RemoteDisconnected, ConnectionError)):
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/slow-deadline", timeout=15)
        elapsed = time.monotonic() - started
        assert elapsed < 12
    finally:
        WarRoomRequestHandler._extra_get_routes.pop("/api/slow-deadline", None)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_server_rejects_work_beyond_handler_limit(tmp_path):
    entered = threading.Event()
    release = threading.Event()

    def _occupied(handler: WarRoomRequestHandler) -> None:
        entered.set()
        release.wait(timeout=5)
        handler._json_response(HTTPStatus.OK, {"ok": True})

    WarRoomRequestHandler.register_get_route("/api/occupied", _occupied)
    root = make_repo(tmp_path)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    server._request_slots = threading.BoundedSemaphore(1)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    first_error: list[Exception] = []

    def first_request() -> None:
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/api/occupied").read()
        except Exception as exc:  # pragma: no cover - diagnostic for assertion below
            first_error.append(exc)

    first = threading.Thread(target=first_request, daemon=True)
    first.start()
    try:
        assert entered.wait(timeout=2)
        code, body = _get_expect_error(f"http://127.0.0.1:{port}/api/board")
        assert code == HTTPStatus.SERVICE_UNAVAILABLE
        assert body == {"error": "server busy"}
    finally:
        release.set()
        first.join(timeout=2)
        WarRoomRequestHandler._extra_get_routes.pop("/api/occupied", None)
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert not first_error
