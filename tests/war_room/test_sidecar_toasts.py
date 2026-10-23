"""Chat sidecar, attach/detach, and toast polling on the War Room server."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus

import pytest

from cascade.war_room.server import serve
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog import activate_epic, append_event, dispatch_feature, read_events
from cascade.watchdog.types import Event
from tests.support import (
    TEST_MODEL_ID,
    add_doc,
    approve_board_feature,
    install_fake_planning_turns,
    make_repo,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, dict | list]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get_expect_error(url: str) -> tuple[int, dict]:
    try:
        _get(url)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict | None = None) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture(autouse=True)
def _sidecar_graph_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    import cascade.epic.boot as epic_boot
    import cascade.feature.boot as feature_boot
    from cascade.epic.graph import clear_epic_graph_sessions
    from cascade.feature.graph import clear_feature_graph_sessions
    from cascade.watchdog.hooks import clear_hooks

    clear_hooks()
    install_fake_planning_turns(monkeypatch)
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    epic_boot._boot_root = None
    feature_boot._boot_root = None
    yield
    clear_hooks()
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    epic_boot._boot_root = None
    feature_boot._boot_root = None


@pytest.fixture
def sidecar_board(tmp_path):
    root = make_repo(tmp_path, git=False, models=True)
    (root / "cascade.toml").write_text(
        f'[models]\nepic = "{TEST_MODEL_ID}"\n'
        f'feature = "{TEST_MODEL_ID}"\n'
        f'task = "{TEST_MODEL_ID}"\n',
        encoding="utf-8",
    )
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task one", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
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


def test_chat_forbidden_without_attach(sidecar_board):
    base, _root = sidecar_board
    status, body = _post_expect_error(f"{base}/api/chat/feat_001", {"body": "hello"})
    assert status == HTTPStatus.FORBIDDEN
    assert body["error"] == "not attached"


def test_attach_detach_and_chat_store_without_reply(sidecar_board):
    base, root = sidecar_board
    status, attach = _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK
    assert attach["doc"]["meta"]["id"] == "feat_001"
    assert "decision_log" in attach
    assert attach["open_comments"] == []
    assert attach["recent_messages"] == []

    status, stored = _post(f"{base}/api/chat/feat_001", {"body": "  human note  "})
    assert status == HTTPStatus.ACCEPTED
    assert stored["graph_id"] == "feat_001"
    assert stored["author"] == "human"
    assert stored["body"] == "human note"
    assert "id" in stored and "ts" in stored

    status, messages = _get(f"{base}/api/chat/feat_001")
    assert status == HTTPStatus.OK
    human = [row for row in messages if row.get("author") == "human"]
    assert len(human) == 1
    assert human[0]["body"] == "human note"

    sidecar = root / "docs" / "_war_room" / "chat" / "feat_001.jsonl"
    assert sidecar.is_file()
    assert "human note" in sidecar.read_text(encoding="utf-8")

    status, detached = _post(f"{base}/api/detach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK
    assert detached == {"ok": True}

    status, _body = _post_expect_error(f"{base}/api/chat/feat_001", {"body": "again"})
    assert status == HTTPStatus.FORBIDDEN


def test_attach_hierarchical_feature_returns_briefing(sidecar_board):
    base, root = sidecar_board
    feature_id = "feat_001_001"
    add_doc(
        root,
        id=feature_id,
        title="Hierarchical feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )

    status, attach = _post(f"{base}/api/attach", {"graph_id": feature_id})

    assert status == HTTPStatus.OK
    assert attach["doc"]["meta"]["id"] == feature_id
    assert attach["recent_messages"] == []
    assert (root / ".cascade" / "checkpoints" / f"{feature_id}.sqlite").is_file()


def test_chat_empty_when_missing_sidecar(sidecar_board):
    base, root = sidecar_board
    add_doc(root, id="epic_002", title="No chat yet", tier="epic", status="backlog")
    status, messages = _get(f"{base}/api/chat/epic_002")
    assert status == HTTPStatus.OK
    assert messages == []


def test_events_to_toasts_epic_orphan_and_task_retry_proposed() -> None:
    ts = datetime.now(timezone.utc)
    events = [
        Event(
            type="Toast",
            ts=ts,
            payload={
                "kind": "epic_ready_to_close",
                "id": "epic_001",
                "epic_id": "epic_001",
                "message": "Epic epic_001 is ready to close",
            },
            dest="war_room",
        ),
        Event(
            type="Toast",
            ts=ts,
            payload={
                "kind": "orphan",
                "id": "feat_orphan",
                "message": "feat_orphan feature without valid parent",
            },
            dest="war_room",
        ),
        Event(
            type="Toast",
            ts=ts,
            payload={
                "kind": "task_retry_proposed",
                "id": "task_007",
                "message": "Retry task_007?",
            },
            dest="war_room",
        ),
    ]
    mapped = events_to_toasts(events)
    assert len(mapped) == 3
    assert mapped[0]["kind"] == "epic_ready_to_close"
    assert mapped[0]["epic_id"] == "epic_001"
    assert mapped[0]["link"] == "/api/doc/epic_001"
    assert mapped[1]["kind"] == "orphan"
    assert mapped[1]["orphan_id"] == "feat_orphan"
    assert mapped[2]["kind"] == "task_retry_proposed"
    assert mapped[2]["task_id"] == "task_007"


def test_toast_offset_pagination(sidecar_board):
    base, root = sidecar_board
    for work_id, message in (
        ("epic_001", "illegal epic move"),
        ("feat_001", "illegal feature move"),
    ):
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload={
                    "kind": "illegal_move",
                    "id": work_id,
                    "message": message,
                    "reason": "unauthorized",
                },
                dest="war_room",
            ),
            root=root,
        )

    status, first = _get(f"{base}/api/toasts?after=0")
    assert status == HTTPStatus.OK
    assert len(first["toasts"]) == 2
    assert first["toasts"][0]["kind"] == "illegal_dispatch"
    assert first["toasts"][0]["body"] == "illegal epic move"
    assert first["toasts"][0]["link"] == "/api/doc/epic_001"
    offset = first["offset"]
    assert offset > 0

    status, second = _get(f"{base}/api/toasts?after={offset}")
    assert status == HTTPStatus.OK
    assert second["toasts"] == []
    assert second["offset"] == offset

    events, end_offset = read_events("war_room", 0, root=root)
    assert len(events) == 2
    status, tail = _get(f"{base}/api/toasts?after={end_offset}")
    assert tail["toasts"] == []


def test_task_tier_chat_rejected_when_attached(sidecar_board):
    base, _root = sidecar_board
    _post(f"{base}/api/attach", {"graph_id": "task_001"})
    status, body = _post_expect_error(f"{base}/api/chat/task_001", {"body": "nope"})
    assert status == HTTPStatus.FORBIDDEN
    assert "task tier" in body["error"]


def test_chat_invalid_graph_id_returns_json(sidecar_board):
    base, _root = sidecar_board
    for bad_id in (".", "..", "bad\\id"):
        code, err = _get_expect_error(f"{base}/api/chat/{bad_id}")
        assert code in (HTTPStatus.BAD_REQUEST, HTTPStatus.NOT_FOUND)
        assert "error" in err

    _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    code, err = _post_expect_error(f"{base}/api/chat/..", {"body": "hi"})
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "invalid graph_id"

    code, err = _post_expect_error(f"{base}/api/chat/feat_001", {"body": "   "})
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "missing body"
