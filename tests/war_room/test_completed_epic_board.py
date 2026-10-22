"""Completed-epic display limit and board metadata on /api/board."""

from __future__ import annotations

import subprocess
import threading
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo
from tests.war_room.test_http_read import _free_port, _get

from cascade.war_room.server import serve


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _completed_epic_ids(payload: dict) -> list[str]:
    return [row["id"] for row in payload["epics"]["3_completed"]]


@pytest.fixture
def war_room_server(tmp_path):
    root = make_repo(tmp_path, git=True)
    _git(root, "remote", "add", "origin", "https://github.com/acme/cascade.git")
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
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


def test_board_bounds_completed_epics_to_default_ten(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    for n in range(1, 13):
        add_doc(
            root,
            id=f"epic_{n:03d}",
            title=f"Done {n}",
            tier="epic",
            status="completed",
        )
    add_doc(root, id="epic_014", title="Still on", tier="epic", status="active")

    payload = board_view_from_index(merged_board(root), root=root)

    assert len(_completed_epic_ids(payload)) == 10
    assert _completed_epic_ids(payload) == [f"epic_{n:03d}" for n in range(3, 13)]
    assert payload["epics"]["2_active"][0]["id"] == "epic_014"
    assert payload["board"]["completed_epic_display_limit"] == 10


def test_board_respects_configured_completed_epic_limit(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    (root / "cascade.toml").write_text(
        "[war_room]\ncompleted_epic_display_limit = 2\n",
        encoding="utf-8",
    )
    for n in range(1, 6):
        add_doc(
            root,
            id=f"epic_{n:03d}",
            title=f"Done {n}",
            tier="epic",
            status="completed",
        )

    payload = board_view_from_index(merged_board(root), root=root)

    assert _completed_epic_ids(payload) == ["epic_004", "epic_005"]
    assert payload["board"]["completed_epic_display_limit"] == 2


@pytest.mark.parametrize(
    ("toml", "expected"),
    [
        ("", 10),
        ("[war_room]\ncompleted_epic_display_limit = 0\n", 10),
        ("[war_room]\ncompleted_epic_display_limit = -3\n", 10),
        ('[war_room]\ncompleted_epic_display_limit = "five"\n', 10),
        ("[war_room]\ncompleted_epic_display_limit = true\n", 10),
        ("[war_room]\ncompleted_epic_display_limit = 4\n", 4),
    ],
)
def test_invalid_completed_epic_limit_falls_back(
    tmp_path: Path, toml: str, expected: int
) -> None:
    root = make_repo(tmp_path, git=False)
    if toml:
        (root / "cascade.toml").write_text(toml, encoding="utf-8")
    for n in range(1, 8):
        add_doc(
            root,
            id=f"epic_{n:03d}",
            title=f"Done {n}",
            tier="epic",
            status="completed",
        )

    payload = board_view_from_index(merged_board(root), root=root)

    assert payload["board"]["completed_epic_display_limit"] == expected
    assert len(_completed_epic_ids(payload)) == min(expected, 7)


def test_completed_features_and_tasks_are_not_bounded(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    for n in range(2, 14):
        add_doc(
            root,
            id=f"feat_001_{n:03d}",
            title=f"Done feat {n}",
            tier="feature",
            parent="epic_001",
            status="completed",
        )
        add_doc(
            root,
            id=f"task_{n:03d}",
            title=f"Done task {n}",
            tier="task",
            parent="feat_001",
            status="completed",
        )

    payload = board_view_from_index(merged_board(root), root=root)

    assert len(payload["features"]["3_completed"]) == 12
    assert len(payload["tasks"]["3_completed"]) == 12


def test_board_exposes_completed_epics_history_metadata(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, payload, _headers = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    history = payload["board"]["completed_epics_history"]
    assert history["path"] == "docs/epics/3_completed"
    assert history["available"] is True
    assert history["url"] == "https://github.com/acme/cascade/tree/main/docs/epics/3_completed"


def test_board_history_unavailable_without_git_remote(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Done", tier="epic", status="completed")
    payload = board_view_from_index(merged_board(root), root=root)
    history = payload["board"]["completed_epics_history"]
    assert history["available"] is False
    assert history["url"] is None
    assert history["path"] == "docs/epics/3_completed"


def test_board_exposes_history_when_no_completed_epics(war_room_server) -> None:
    base, _root, _server = war_room_server
    status, payload, _headers = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    assert payload["epics"]["3_completed"] == []
    history = payload["board"]["completed_epics_history"]
    assert history["path"] == "docs/epics/3_completed"
    assert history["available"] is True
    assert "docs/epics/3_completed" in history["url"]


def test_board_http_renders_when_history_unavailable(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, payload, _headers = _get(f"{base}/api/board")
        assert status == HTTPStatus.OK
        history = payload["board"]["completed_epics_history"]
        assert history["available"] is False
        assert history["url"] is None

        status, home_html, _headers = _get(f"{base}/")
        assert status == HTTPStatus.OK
        assert 'id="war-room-board"' in home_html
        epics_tier = home_html.split('data-tier="epics"')[1].split('data-tier="features"')[0]
        assert "data-board-completed-history" in epics_tier
        assert "board-column-completed-collapsed" in epics_tier
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
