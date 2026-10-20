"""War Room POST /api/comment and GET /api/comments/{doc_id} (task_078)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from cascade.war_room.server import serve
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo


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
    add_doc(
        root,
        id="task_001",
        title="Alpha",
        tier="task",
        parent="feat_001",
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


def test_root_comment_slugifies_section_and_persists_optional_fields(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Memory layout",
            "body": "line bind note",
            "line_start": 2,
            "line_end": 4,
            "doc_sha": "deadbeef",
            "blocks": ["task_001"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = body["comment_id"]

    status, payload = _get(f"{base}/api/comments/feat_001")
    assert status == HTTPStatus.OK
    row = next(c for c in payload["comments"] if c["id"] == root_id)
    assert row["section"] == "memory-layout"
    assert row["line_start"] == 2
    assert row["line_end"] == 4
    assert row["doc_sha"] == "deadbeef"
    assert row["blocks"] == ["task_001"]


def test_reply_inherits_parent_section_and_anchor(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, root_body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Scope",
            "anchor": "quoted snippet",
            "body": "root thread",
            "line_start": 1,
            "line_end": 3,
            "doc_sha": "ignored-on-reply",
            "blocks": ["task_001"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = root_body["comment_id"]

    status, reply_body = _post(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "parent": root_id,
            "body": "human reply",
            "section": "ignored",
            "anchor": "ignored",
            "blocking": True,
            "line_start": 9,
            "line_end": 10,
            "doc_sha": "ignored",
            "blocks": ["task_999"],
        },
    )
    assert status == HTTPStatus.ACCEPTED
    reply_id = reply_body["comment_id"]

    _status, payload = _get(f"{base}/api/comments/feat_001")
    reply = next(c for c in payload["comments"] if c["id"] == reply_id)
    assert reply["section"] == "scope"
    assert reply["anchor"] == "quoted snippet"
    assert reply["parent"] == root_id
    assert reply["line_start"] is None
    assert reply["line_end"] is None
    assert reply["doc_sha"] is None
    assert reply["blocks"] == []


def test_reply_missing_parent_returns_404(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "parent": "cmt_999", "body": "orphan reply"},
    )
    assert code == HTTPStatus.NOT_FOUND
    assert "error" in err


def test_root_empty_section_returns_400(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "section": "   ", "body": "note"},
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "error" in err


def test_root_invalid_line_range_returns_400(war_room_server) -> None:
    base, _root, _server = war_room_server
    code, err = _post_expect_error(
        f"{base}/api/comment",
        {
            "doc_id": "feat_001",
            "section": "Scope",
            "body": "note",
            "line_start": 5,
            "line_end": 3,
        },
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "error" in err


def test_comment_post_appends_graph_queue_events(war_room_server) -> None:
    base, root, _server = war_room_server
    status, root_body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "section": "Scope", "body": "root"},
    )
    assert status == HTTPStatus.ACCEPTED
    root_id = root_body["comment_id"]

    status, _reply_body = _post(
        f"{base}/api/comment",
        {"doc_id": "feat_001", "parent": root_id, "body": "reply"},
    )
    assert status == HTTPStatus.ACCEPTED

    events, _ = read_events("feat_001", 0, root=root)
    types = [event.type for event in events]
    assert "CommentPosted" in types
    assert "CommentReplied" in types
