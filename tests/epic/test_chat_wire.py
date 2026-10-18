"""War Room POST /api/chat wired into the epic LangGraph."""

from __future__ import annotations

import importlib
import json
import socket
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

import cascade.epic.boot as epic_boot
from cascade.epic.graph import clear_epic_graph_sessions
import cascade.epic.stubs as epic_stubs
from cascade.epic import (
    clear_epic_tools,
    ensure_epic_graph,
    epic_tools,
    invoke_tool,
    load_epic_tools,
)
from cascade.epic.checkpoint import checkpoint_path, thread_config
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature
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
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


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
def _epic_graph_isolation(monkeypatch: pytest.MonkeyPatch) -> None:
    from cascade.watchdog.hooks import clear_hooks
    from tests.support import install_fake_planning_turns

    clear_hooks()
    install_fake_planning_turns(monkeypatch)
    clear_epic_tools()
    clear_epic_graph_sessions()
    epic_boot._boot_root = None
    yield
    clear_hooks()
    clear_epic_tools()
    clear_epic_graph_sessions()
    epic_boot._boot_root = None


def test_epic_chat_forbidden_without_attach(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False, role_skills=True)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        _run_epic_chat_forbidden(base, root)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _run_epic_chat_forbidden(base: str, root: Path) -> None:
    req = urllib.request.Request(
        f"{base}/api/chat/epic_001",
        method="POST",
        data=json.dumps({"body": "nope"}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.FORBIDDEN
    assert not checkpoint_path("epic_001", root=root).exists()


def test_epic_post_chat_sidecar_and_graph(chat_wire_board) -> None:
    base, root = chat_wire_board
    _post(f"{base}/api/attach", {"graph_id": "epic_001"})
    status, stored = _post(f"{base}/api/chat/epic_001", {"body": "Plan the MVP"})
    assert status == HTTPStatus.ACCEPTED
    assert stored["body"] == "Plan the MVP"

    sidecar = root / "docs" / "_war_room" / "chat" / "epic_001.jsonl"
    assert sidecar.is_file()
    assert "Plan the MVP" in sidecar.read_text(encoding="utf-8")

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state(thread_config("epic_001")).values
    assert state is not None
    roles = [m.get("role") for m in state["messages"]]
    assert roles.count("human") == 1
    assert roles.count("epic_manager") == 1
    assert roles.count("epic_architect") == 1
    human = next(m for m in state["messages"] if m.get("role") == "human")
    assert human["content"] == "Plan the MVP"


def test_feature_post_chat_does_not_create_epic_checkpoint(chat_wire_board) -> None:
    base, root = chat_wire_board
    _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    status, stored = _post(f"{base}/api/chat/feat_001", {"body": "feature note"})
    assert status == HTTPStatus.ACCEPTED
    assert stored["graph_id"] == "feat_001"
    from cascade.feature.checkpoint import checkpoint_path as feature_checkpoint_path

    assert feature_checkpoint_path("feat_001", root=root).is_file()
    assert not checkpoint_path("epic_001", root=root).exists()


def test_load_epic_tools_registers_all_tools() -> None:
    clear_epic_tools()
    load_epic_tools()
    names = set(epic_tools())
    assert {
        "mint_feature",
        "list_children",
        "record_decision",
        "read_doc",
        "write_doc",
        "reply_comment",
        "resolve_comment",
        "resolve_amendment",
    } <= names


def test_load_epic_tools_reregisters_after_clear() -> None:
    clear_epic_tools()
    importlib.reload(epic_stubs)
    load_epic_tools()
    assert "mint_feature" in epic_tools()


def test_invoke_mint_feature_after_load(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    load_epic_tools()
    feature_id = invoke_tool(
        "epic_001",
        "mint_feature",
        {"title": "New feature", "epic_id": "epic_001", "root": root},
        root=root,
    )
    assert isinstance(feature_id, str)
    assert feature_id.startswith("feat_")


def test_invoke_reply_comment_on_epic_thread(tmp_path: Path) -> None:
    from cascade.comments.store import comment, read_comments

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    load_epic_tools()
    root_id = comment("epic_001", "Intent", "question", author="human", root=root)
    invoke_tool(
        "epic_001",
        "reply_comment",
        {
            "comment_id": root_id,
            "body": "hi",
            "epic_id": "epic_001",
            "root": root,
        },
        root=root,
    )
    rows = read_comments("epic_001", root=root)
    assert len(rows) == 2
    assert rows[1].body == "hi"
