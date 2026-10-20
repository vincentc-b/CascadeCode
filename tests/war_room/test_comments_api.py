"""Plan comment GET/POST on the War Room server."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

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
    assert rows[0].blocking is True

    events, _ = read_events("epic_001", 0, root=root)
    assert any(event.type == "CommentPosted" for event in events)

    status, listed = _get(f"{base}/api/comments/epic_001")
    assert status == 200
    assert len(listed["comments"]) == 1
    assert listed["comments"][0]["id"] == body["comment_id"]
