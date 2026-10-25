"""Persisted stacked-PR room settings API (task_007_001_001)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.war_room.room_settings import (
    effective_stacked_pr_enabled,
    read_room_settings,
    stacked_pr_enabled,
)
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture
def war_room_board(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="epic_002", title="Other epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        status="backlog",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
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
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_default_stacked_pr_enabled_when_unset(war_room_board) -> None:
    base, root = war_room_board
    status, body = _get(f"{base}/api/room-settings/epic_001")
    assert status == HTTPStatus.OK
    assert body == {"graph_id": "epic_001", "stacked_pr_enabled": True}
    assert stacked_pr_enabled("epic_001", root=root) is True
    assert read_room_settings("feat_001", root=root).stacked_pr_enabled is True
    assert effective_stacked_pr_enabled("feat_001", "epic_001", root=root) is True


def test_toggle_persists_per_room(war_room_board) -> None:
    base, root = war_room_board
    status, body = _post(
        f"{base}/api/room-settings/epic_001", {"stacked_pr_enabled": True}
    )
    assert status == HTTPStatus.OK
    assert body["stacked_pr_enabled"] is True

    status, body = _post(
        f"{base}/api/room-settings/feat_001", {"stacked_pr_enabled": False}
    )
    assert status == HTTPStatus.OK
    assert body["stacked_pr_enabled"] is False

    assert read_room_settings("epic_001", root=root).stacked_pr_enabled is True
    assert read_room_settings("feat_001", root=root).stacked_pr_enabled is False
    assert read_room_settings("epic_002", root=root).stacked_pr_enabled is True

    path = root / ".cascade" / "room_settings.json"
    assert path.is_file()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["rooms"]["epic_001"]["stacked_pr_enabled"] is True
    assert "stacked_pr_enabled" not in reloaded["rooms"].get("feat_001", {}) or (
        reloaded["rooms"]["feat_001"]["stacked_pr_enabled"] is False
    )


def test_feature_room_shows_inherited_epic_setting_until_overridden(war_room_board) -> None:
    base, root = war_room_board
    _post(f"{base}/api/room-settings/epic_001", {"stacked_pr_enabled": True})

    status, body = _get(f"{base}/api/room-settings/feat_001")
    assert status == HTTPStatus.OK
    assert body == {"graph_id": "feat_001", "stacked_pr_enabled": True}
    assert read_room_settings("feat_001", root=root).stacked_pr_enabled is True

    _post(f"{base}/api/room-settings/feat_001", {"stacked_pr_enabled": False})
    _, body = _get(f"{base}/api/room-settings/feat_001")
    assert body["stacked_pr_enabled"] is False


def test_legacy_room_record_without_field_defaults_on(war_room_board) -> None:
    _base, root = war_room_board
    path = root / ".cascade" / "room_settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"rooms": {"epic_001": {"other_flag": True}}}) + "\n",
        encoding="utf-8",
    )
    assert read_room_settings("epic_001", root=root).stacked_pr_enabled is True


def test_explicit_epic_disable_is_inherited_by_feature(war_room_board) -> None:
    base, root = war_room_board
    _post(f"{base}/api/room-settings/epic_001", {"stacked_pr_enabled": False})

    assert read_room_settings("epic_001", root=root).stacked_pr_enabled is False
    assert read_room_settings("feat_001", root=root).stacked_pr_enabled is False
    assert effective_stacked_pr_enabled("feat_001", "epic_001", root=root) is False


def test_task_graph_rejected(war_room_board) -> None:
    base, _root = war_room_board
    code, err = _post_expect_error(
        f"{base}/api/room-settings/task_001", {"stacked_pr_enabled": True}
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert "epic or feature" in err["error"]
