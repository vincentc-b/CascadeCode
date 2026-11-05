"""Canonical backlog priority through the War Room board API."""

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
from cascade.boss.view import compute_boss_view
from cascade.war_room.server import serve
from tests.support import add_doc, approve_board_feature, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post(url: str, payload: dict) -> tuple[int, dict]:
    request = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


def _post_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        return _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


@pytest.fixture
def priority_api(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Other", tier="epic", status="active")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Second", tier="feature", parent="epic_001")
    add_doc(root, id="feat_099", title="Other", tier="feature", parent="epic_002")
    add_doc(
        root,
        id="feat_003",
        title="Active",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    approve_board_feature(root, "feat_001")
    approve_board_feature(root, "feat_002")
    server = serve(root=root, host="127.0.0.1", port=_free_port())
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _projection(board: dict, epic_id: str = "epic_001") -> dict:
    return board["backlog_feature_priorities"][epic_id]


def test_board_projects_and_renders_accepted_order_for_every_client(priority_api) -> None:
    base, root = priority_api
    _status, initial = _get(f"{base}/api/board")
    before_dispatchable = compute_boss_view(root=root).dispatchable_features
    priority = _projection(initial)
    before_readiness = {
        row["id"]: row["readiness"]
        for row in initial["features"]["1_backlog"]
        if row["parent"] == "epic_001"
    }
    assert priority["feature_ids"] == ["feat_001", "feat_002"]
    assert isinstance(priority["token"], str) and priority["token"]

    status, accepted = _post(
        f"{base}/api/reorder_backlog_features",
        {
            "epic_id": "epic_001",
            "feature_ids": ["feat_002", "feat_001"],
            "expected_token": priority["token"],
        },
    )

    assert status == HTTPStatus.OK
    assert accepted["ok"] is True
    assert accepted["feature_ids"] == ["feat_002", "feat_001"]
    assert accepted["token"] != priority["token"]
    _status, second_client = _get(f"{base}/api/board")
    assert _projection(second_client) == {
        "feature_ids": accepted["feature_ids"],
        "token": accepted["token"],
    }
    epic_rows = [
        row["id"]
        for row in second_client["features"]["1_backlog"]
        if row["parent"] == "epic_001"
    ]
    assert epic_rows == ["feat_002", "feat_001"]
    assert {
        row["id"]: row["readiness"]
        for row in second_client["features"]["1_backlog"]
        if row["parent"] == "epic_001"
    } == before_readiness
    assert compute_boss_view(root=root).dispatchable_features == before_dispatchable


def test_board_reconciles_creation_and_departure(priority_api) -> None:
    base, root = priority_api
    _status, initial = _get(f"{base}/api/board")
    initial_priority = _projection(initial)
    add_doc(root, id="feat_004", title="New", tier="feature", parent="epic_001")

    _status, appended = _get(f"{base}/api/board")
    appended_priority = _projection(appended)
    assert appended_priority["feature_ids"] == ["feat_001", "feat_002", "feat_004"]
    assert appended_priority["token"] != initial_priority["token"]

    move_doc("feat_001", "active", root=root)
    _status, compacted = _get(f"{base}/api/board")
    assert _projection(compacted)["feature_ids"] == ["feat_002", "feat_004"]


def test_stale_client_gets_current_projection_without_mutation(priority_api) -> None:
    base, root = priority_api
    _status, board = _get(f"{base}/api/board")
    stale = _projection(board)
    _status, accepted = _post(
        f"{base}/api/reorder_backlog_features",
        {
            "epic_id": "epic_001",
            "feature_ids": ["feat_002", "feat_001"],
            "expected_token": stale["token"],
        },
    )
    state_path = root / ".cascade" / "backlog_feature_priority.json"
    before = state_path.read_bytes()

    status, conflict = _post_error(
        f"{base}/api/reorder_backlog_features",
        {
            "epic_id": "epic_001",
            "feature_ids": ["feat_001", "feat_002"],
            "expected_token": stale["token"],
        },
    )

    assert status == HTTPStatus.CONFLICT
    assert conflict["code"] == "stale_priority"
    assert conflict["feature_ids"] == accepted["feature_ids"]
    assert conflict["token"] == accepted["token"]
    assert state_path.read_bytes() == before


@pytest.mark.parametrize(
    ("feature_ids", "code"),
    [
        (["feat_001", "feat_001"], "duplicate_id"),
        (["feat_001"], "membership_mismatch"),
        (["feat_001", "feat_missing"], "unknown_id"),
        (["feat_001", "feat_099"], "cross_epic_id"),
        (["feat_001", "feat_003"], "non_backlog_id"),
    ],
)
def test_invalid_membership_is_422_and_atomic(priority_api, feature_ids, code) -> None:
    base, root = priority_api
    _status, board = _get(f"{base}/api/board")
    priority = _projection(board)
    state_path = root / ".cascade" / "backlog_feature_priority.json"
    before = state_path.read_bytes()

    status, error = _post_error(
        f"{base}/api/reorder_backlog_features",
        {
            "epic_id": "epic_001",
            "feature_ids": feature_ids,
            "expected_token": priority["token"],
        },
    )

    assert status == HTTPStatus.UNPROCESSABLE_ENTITY
    assert error["ok"] is False
    assert error["code"] == code
    assert state_path.read_bytes() == before


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"epic_id": "epic_001", "feature_ids": "feat_001", "expected_token": "x"},
        {"epic_id": "epic_001", "feature_ids": ["feat_001"], "expected_token": ""},
    ],
)
def test_malformed_reorder_payload_is_400(priority_api, payload) -> None:
    base, _root = priority_api
    status, error = _post_error(f"{base}/api/reorder_backlog_features", payload)
    assert status == HTTPStatus.BAD_REQUEST
    assert "error" in error
