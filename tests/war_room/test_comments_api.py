"""Plan comment GET/POST on the War Room server."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from cascade.comments.store import comment as post_comment
from cascade.comments.store import read_comments
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, read_events
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_error(url: str, payload: dict) -> tuple[int, dict]:
    with pytest.raises(urllib.error.HTTPError) as caught:
        _post(url, payload)
    error = caught.value
    return error.code, json.loads(error.read().decode())


def _initial_commit(root: Path) -> None:
    import subprocess

    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "board"],
        cwd=root,
        check=True,
        capture_output=True,
    )


@pytest.fixture
def comment_board(tmp_path):
    root = make_repo(tmp_path, git=True, models=True, role_skills=True)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    _initial_commit(root)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_comments_empty(comment_board) -> None:
    base, _root = comment_board
    status, body = _get(f"{base}/api/comments/epic_001")
    assert status == 200
    assert body["doc_id"] == "epic_001"
    assert body["comments"] == []


def test_post_comment_persists_and_emits_queue(comment_board) -> None:
    base, root = comment_board
    assert activate_epic("epic_001", "human", root=root).ok

    with patch("cascade.war_room.server.kickoff_graph_queue_event", return_value=True) as kick:
        status, body = _post(
            f"{base}/api/comment",
            {
                "doc_id": "epic_001",
                "section": "Open questions",
                "anchor": "selected plan line",
                "line_start": 8,
                "line_end": 9,
                "doc_sha": "abc123",
                "body": "Please resolve anchor model.",
                "blocking": True,
            },
        )
    assert status == 202
    assert body["ok"] is True
    assert body["comment_id"].startswith("cmt_")
    assert body["kickoff"] is True
    kick.assert_called_once()

    rows = read_comments("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0].section == "Open questions"
    assert rows[0].anchor == "selected plan line"
    assert rows[0].line_start == 8
    assert rows[0].line_end == 9
    assert rows[0].doc_sha == "abc123"
    assert rows[0].blocking is True

    events, _ = read_events("epic_001", 0, root=root)
    posted = next(event for event in events if event.type == "CommentPosted")
    assert posted.payload["anchor"] == "selected plan line"
    assert posted.payload["line_start"] == 8
    assert posted.payload["line_end"] == 9
    assert posted.payload["doc_sha"] == "abc123"

    status, listed = _get(f"{base}/api/comments/epic_001")
    assert status == 200
    assert len(listed["comments"]) == 1
    assert listed["comments"][0]["id"] == body["comment_id"]
    assert listed["comments"][0]["line_start"] == 8


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"line_start": 0}, "invalid line_start"),
        ({"line_start": True}, "invalid line_start"),
        ({"line_end": -1}, "invalid line_end"),
        ({"line_start": 4, "line_end": 3}, "line_end before line_start"),
        ({"doc_sha": 123}, "invalid doc_sha"),
    ],
)
def test_post_comment_rejects_invalid_line_position(
    comment_board, fields, message
) -> None:
    base, root = comment_board
    payload = {
        "doc_id": "epic_001",
        "section": "Scope",
        "body": "Please revise this.",
        **fields,
    }
    status, response = _post_error(f"{base}/api/comment", payload)
    assert status == 400
    assert message in response["error"]
    assert read_comments("epic_001", root=root) == []


def test_post_reply_inherits_context_but_not_line_position(comment_board) -> None:
    base, root = comment_board
    parent_id = post_comment(
        "epic_001",
        "Scope",
        "Question",
        anchor="selected source",
        line_start=4,
        line_end=5,
        doc_sha="abc123",
        author="human",
        root=root,
    )

    with patch(
        "cascade.war_room.server.kickoff_graph_queue_event", return_value=True
    ) as kick:
        status, response = _post(
            f"{base}/api/comment",
            {"doc_id": "epic_001", "parent": parent_id, "body": "Follow-up"},
        )

    assert status == 202
    assert response["kickoff"] is True
    kick.assert_called_once_with("epic_001", root=root, by="human")
    reply = next(
        row
        for row in read_comments("epic_001", root=root)
        if row.id == response["comment_id"]
    )
    assert reply.parent == parent_id
    assert reply.section == "Scope"
    assert reply.anchor == "selected source"
    assert reply.line_start is None
    assert reply.line_end is None
    assert reply.doc_sha is None
