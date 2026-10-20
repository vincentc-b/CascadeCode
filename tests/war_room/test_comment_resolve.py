"""POST /api/comment/resolve and plan viewer Resolve control (task_087)."""

from __future__ import annotations

import inspect
import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cascade.war_room.server import WarRoomRequestHandler, serve
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo

_STATIC = Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _create_root(base: str) -> str:
    status, body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "section": "Scope", "body": "root thread"},
    )
    assert status == HTTPStatus.ACCEPTED
    return body["comment_id"]


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Beta",
        tier="feature",
        parent="epic_001",
        status="active",
    )
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


def test_resolve_api_plan_viewer_and_no_kickoff(war_room_server, monkeypatch) -> None:
    base, root, _server = war_room_server
    resolve_url = f"{base}/api/comment/resolve"

    kickoff_turn = MagicMock(side_effect=AssertionError("kickoff_turn must not run on resolve"))
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", kickoff_turn)
    handler_source = inspect.getsource(WarRoomRequestHandler._handle_comment_resolve)
    assert "kickoff" not in handler_source

    plan_js = (_STATIC / "plan_viewer.js").read_text(encoding="utf-8")
    assert "/api/comment/resolve" in plan_js
    assert "plan-comment-resolve" in plan_js
    assert "buildResolveControl" in plan_js
    assert '#plan-comments [data-comment-id]' not in plan_js
    assert "data-comment-id" in plan_js
    assert 'root.state !== "resolved"' in plan_js

    root_id = _create_root(base)
    status, reply_body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "parent": root_id, "body": "human reply"},
    )
    assert status == HTTPStatus.ACCEPTED
    reply_id = reply_body["comment_id"]

    status, resolved = _post(resolve_url, {"doc_id": "feat_001", "comment_id": root_id})
    assert status == HTTPStatus.ACCEPTED
    assert resolved == {"ok": True, "comment_id": root_id}

    _status, payload = _get(f"{base}/api/comments/feat_001")
    by_id = {row["id"]: row for row in payload["comments"]}
    assert by_id[root_id]["state"] == "resolved"
    assert by_id[reply_id]["state"] == "resolved"

    status, again = _post(resolve_url, {"doc_id": "feat_001", "comment_id": root_id})
    assert status == HTTPStatus.ACCEPTED
    assert again == {"ok": True, "comment_id": root_id}

    code, err = _post_expect_error(
        resolve_url,
        {"doc_id": "feat_001", "comment_id": reply_id},
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert err.get("error") == "NotARoot"

    code, err = _post_expect_error(
        resolve_url,
        {"doc_id": "feat_001", "comment_id": "cmt_999"},
    )
    assert code == HTTPStatus.NOT_FOUND
    assert "error" in err

    kickoff_turn.assert_not_called()

    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "CommentResolved" for event in events) == 1
