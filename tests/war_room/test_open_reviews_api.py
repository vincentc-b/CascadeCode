"""Open-reviews registry read API (feat_003 / task_007)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get_json(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _write_reviews(root: Path, payload: dict) -> None:
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Root epic", tier="epic")
    add_doc(root, id="epic_002", title="Other epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Open feature",
        tier="feature",
        parent="epic_001",
        status="completed",
    )
    add_doc(
        root,
        id="feat_002",
        title="Closed feature",
        tier="feature",
        parent="epic_002",
        status="completed",
    )
    add_doc(
        root,
        id="feat_003",
        title="Merged feature",
        tier="feature",
        parent="epic_001",
        status="completed",
    )
    _write_reviews(
        root,
        {
            "feat_001": {
                "url": "https://github.example/o/r/pull/1",
                "number": "1",
                "forge": "github",
                "source_branch": "feat/feat_001",
                "target_branch": "epic/epic_001",
                "draft": False,
                "closed": False,
            },
            "feat_002": {
                "url": "https://github.example/o/r/pull/2",
                "number": "2",
                "forge": "github",
                "source_branch": "feat/feat_002",
                "target_branch": "epic/epic_002",
                "draft": False,
                "closed": True,
            },
            "feat_003": {
                "url": "https://github.example/o/r/pull/3",
                "number": "3",
                "forge": "github",
                "source_branch": "feat/feat_003",
                "target_branch": "epic/epic_001",
                "draft": False,
                "closed": True,
            },
        },
    )
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


def test_open_reviews_returns_only_open_registry_rows(war_room_server):
    base, root = war_room_server
    state_path = root / ".cascade" / "reviews.json"
    before = state_path.read_text(encoding="utf-8")

    status, payload = _get_json(f"{base}/api/open-reviews")

    assert status == HTTPStatus.OK
    assert state_path.read_text(encoding="utf-8") == before
    assert [row["id"] for row in payload["reviews"]] == ["feat_001"]
    row = payload["reviews"][0]
    assert row["url"] == "https://github.example/o/r/pull/1"
    assert row["state"] == "awaiting_review"
    assert row["context"] == {
        "feature_id": "feat_001",
        "epic_id": "epic_001",
        "feature_title": "Open feature",
        "epic_title": "Root epic",
    }
