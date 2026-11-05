"""The visible epic backlog has one durable, guarded order for all clients."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.board.store import move_doc
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url, method="POST", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as exc:
        return exc.code, json.load(exc)


@pytest.fixture
def epic_api(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    for epic_id in ("epic_001", "epic_002", "epic_003"):
        add_doc(root, id=epic_id, title=epic_id, tier="epic")
    add_doc(root, id="epic_099", title="Active", tier="epic", status="active")
    server = serve(root=root, host="127.0.0.1", port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_reorder_survives_refresh_and_rejects_stale_or_invalid_writes(epic_api) -> None:
    base, root = epic_api
    initial = _get(f"{base}/api/board")["backlog_epic_priority"]
    assert initial["epic_ids"] == ["epic_001", "epic_002", "epic_003"]
    wanted = ["epic_003", "epic_001", "epic_002"]
    status, accepted = _post(
        f"{base}/api/reorder_backlog_epics",
        {"epic_ids": wanted, "expected_token": initial["token"]},
    )
    assert status == HTTPStatus.OK
    assert accepted["epic_ids"] == wanted
    board = _get(f"{base}/api/board")
    assert [row["id"] for row in board["epics"]["1_backlog"]] == wanted
    assert board["backlog_epic_priority"]["token"] == accepted["token"]

    state_path = root / ".cascade" / "backlog_epic_priority.json"
    before = state_path.read_bytes()
    status, stale = _post(
        f"{base}/api/reorder_backlog_epics",
        {"epic_ids": list(reversed(wanted)), "expected_token": initial["token"]},
    )
    assert status == HTTPStatus.CONFLICT
    assert stale["code"] == "stale_priority"
    assert stale["epic_ids"] == wanted
    assert state_path.read_bytes() == before

    for invalid, code in (
        (["epic_001", "epic_001", "epic_003"], "duplicate_id"),
        (["epic_001", "epic_002"], "membership_mismatch"),
        (["epic_001", "epic_002", "epic_099"], "non_backlog_id"),
    ):
        status, error = _post(
            f"{base}/api/reorder_backlog_epics",
            {"epic_ids": invalid, "expected_token": accepted["token"]},
        )
        assert status == HTTPStatus.UNPROCESSABLE_ENTITY
        assert error["code"] == code
        assert state_path.read_bytes() == before


def test_new_backlog_epic_appends_and_departed_epic_compacts(epic_api) -> None:
    base, root = epic_api
    first = _get(f"{base}/api/board")["backlog_epic_priority"]
    add_doc(root, id="epic_004", title="New", tier="epic")
    appended = _get(f"{base}/api/board")["backlog_epic_priority"]
    assert appended["epic_ids"] == ["epic_001", "epic_002", "epic_003", "epic_004"]
    assert appended["token"] != first["token"]
    move_doc("epic_002", "active", root=root)
    compacted = _get(f"{base}/api/board")["backlog_epic_priority"]
    assert compacted["epic_ids"] == ["epic_001", "epic_003", "epic_004"]
    assert compacted["token"] != appended["token"]


def test_visible_epic_cards_drag_to_saved_order_in_browser(epic_api) -> None:
    playwright = pytest.importorskip("playwright.sync_api")
    base, _root = epic_api
    with playwright.sync_playwright() as runtime:
        try:
            browser = runtime.chromium.launch(headless=True)
        except playwright.Error as exc:
            pytest.skip(f"Chromium is unavailable: {exc}")
        try:
            page = browser.new_page(viewport={"width": 1600, "height": 1000})
            page.goto(base, wait_until="domcontentloaded")
            source = page.locator(
                '[data-tier="epics"] [data-id="epic_002"] .backlog-drag-hint'
            )
            target = page.locator('[data-tier="epics"] [data-id="epic_001"]')
            source.wait_for()
            assert source.is_visible()
            source.drag_to(target, target_position={"x": 20, "y": 8})
            page.wait_for_function(
                """() => [...document.querySelectorAll(
                  '[data-tier="epics"] [data-column="1_backlog"] .board-row'
                )].map(row => row.dataset.id).join(',') === 'epic_002,epic_001,epic_003'"""
            )
            assert _get(f"{base}/api/board")["backlog_epic_priority"]["epic_ids"] == [
                "epic_002", "epic_001", "epic_003"
            ]
        finally:
            browser.close()
