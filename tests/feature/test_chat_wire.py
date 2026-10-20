"""War Room POST /api/chat wired into the feature LangGraph."""

from __future__ import annotations

import importlib
import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

import cascade.epic.boot as epic_boot
import cascade.feature.boot as feature_boot
from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
import cascade.feature.stubs as feature_stubs
from cascade.epic.checkpoint import checkpoint_path as epic_checkpoint_path
from cascade.feature import (
    clear_feature_tools,
    ensure_feature_graph,
    feature_tools,
    load_feature_tools,
)
from cascade.feature.checkpoint import checkpoint_path, thread_config
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.workspace.kickoff import wait_for_background_kickoffs
from tests.support import add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    payload = dict(payload or {})
    payload.setdefault("model_id", "test-model")
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode("utf-8"),
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


@pytest.fixture
def chat_wire_board(tmp_path: Path):
    root = make_repo(tmp_path, git=False, role_skills=True)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
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


@pytest.fixture(autouse=True)
def _graph_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    from cascade.epic import clear_epic_tools
    from cascade.watchdog.hooks import clear_hooks
    from tests.support import install_fake_planning_turns

    clear_hooks()
    install_fake_planning_turns(monkeypatch)
    clear_epic_tools()
    clear_feature_tools()
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    epic_boot._boot_root = None
    feature_boot._boot_root = None
    yield
    clear_hooks()
    clear_epic_tools()
    clear_feature_tools()
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    epic_boot._boot_root = None
    feature_boot._boot_root = None


def test_post_chat_graph_ingest_failure_not_reported_success(
    chat_wire_board, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, root = chat_wire_board
    _post(f"{base}/api/attach", {"graph_id": "feat_001"})

    def _fail_ingest(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated ingest failure")

    monkeypatch.setattr(
        "cascade.war_room.sidecar_routes.accept_feature_human_chat",
        _fail_ingest,
    )
    status, body = _post_expect_error(
        f"{base}/api/chat/feat_001",
        {"body": "Should not succeed"},
    )
    assert status == HTTPStatus.INTERNAL_SERVER_ERROR
    assert body["error"] == "graph ingest failed"

    sidecar = root / "docs" / "_war_room" / "chat" / "feat_001.jsonl"
    assert not sidecar.exists() or "Should not succeed" not in sidecar.read_text(
        encoding="utf-8"
    )


def test_feature_post_chat_sidecar_and_graph(chat_wire_board) -> None:
    base, root = chat_wire_board
    _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    status, stored = _post(f"{base}/api/chat/feat_001", {"body": "Ship the API"})
    assert status == HTTPStatus.ACCEPTED
    assert stored["body"] == "Ship the API"

    sidecar = root / "docs" / "_war_room" / "chat" / "feat_001.jsonl"
    assert sidecar.is_file()
    assert "Ship the API" in sidecar.read_text(encoding="utf-8")
    epic_sidecar = root / "docs" / "_war_room" / "chat" / "epic_001.jsonl"
    assert not epic_sidecar.exists()

    assert wait_for_background_kickoffs()
    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state(thread_config("feat_001")).values
    assert state is not None
    roles = [m.get("role") for m in state["messages"]]
    assert roles.count("human") == 1
    assert roles.count("feature_lead") == 1
    assert roles.count("feature_architect") == 1
    human = next(m for m in state["messages"] if m.get("role") == "human")
    assert human["content"] == "Ship the API"


def test_feature_chat_does_not_touch_epic_checkpoint(chat_wire_board) -> None:
    base, root = chat_wire_board
    _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    _post(f"{base}/api/chat/feat_001", {"body": "feature note"})
    assert checkpoint_path("feat_001", root=root).is_file()
    with pytest.raises(ValueError):
        epic_checkpoint_path("feat_001", root=root)
    assert not epic_checkpoint_path("epic_001", root=root).exists()


def test_load_feature_tools_registers_all_tools() -> None:
    clear_feature_tools()
    load_feature_tools()
    names = set(feature_tools())
    assert {
        "mint_task",
        "list_children",
        "record_decision",
        "read_doc",
        "write_doc",
        "reply_comment",
        "resolve_comment",
        "propose_epic_amendment",
    } <= names


def test_load_feature_tools_reregisters_after_clear() -> None:
    clear_feature_tools()
    importlib.reload(feature_stubs)
    load_feature_tools()
    assert "propose_epic_amendment" in feature_tools()
