"""Feature attach briefing pack and HumanAttached / HumanDetached events."""

from __future__ import annotations

import json
import socket
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

import cascade.feature.boot as feature_boot
import cascade.feature.graph as feature_graph
from cascade.board.store import pin_parent
from cascade.comments.store import comment
from cascade.feature.briefing import build_briefing_pack, extract_decision_log
from cascade.feature import clear_feature_tools
from cascade.war_room.serialize import briefing_pack_to_dict
from cascade.war_room.server import serve
from cascade.watchdog import read_events
from cascade.watchdog import activate_epic, dispatch_feature
from tests.support import FEATURE_BODY, add_doc, commit_board, make_repo, approve_board_feature


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_feature_tools()
    feature_graph._graph_cache.clear()
    feature_boot._boot_root = None
    yield
    clear_feature_tools()
    feature_graph._graph_cache.clear()
    feature_boot._boot_root = None


@pytest.fixture
def briefing_board(tmp_path: Path):
    root = make_repo(tmp_path, git=True)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    pin_parent("feat_001", "epic_001", root=root)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    commit_board(root)
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


def test_extract_decision_log_slice() -> None:
    excerpt = extract_decision_log(FEATURE_BODY)
    assert excerpt == "None yet."


def test_build_briefing_pack_open_comments_and_parent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    pin_parent("feat_001", "epic_001", root=root)
    comment("feat_001", "Scope", "please clarify", author="human", root=root)

    pack = build_briefing_pack("feat_001", root=root)
    assert pack.doc.meta.id == "feat_001"
    assert len(pack.open_comments) == 1
    assert pack.open_comments[0].section == "Scope"
    assert pack.parent_constraints is not None
    assert pack.parent_constraints.meta.id == "epic_001"
    assert pack.parent_constraints.sha is not None
    assert pack.recent_messages == []

    payload = briefing_pack_to_dict(pack)
    assert payload["doc"]["meta"]["id"] == "feat_001"
    assert payload["decision_log"] == "None yet."
    assert len(payload["open_comments"]) == 1
    assert payload["parent_constraints"]["meta"]["tier"] == "epic"


def test_attach_returns_briefing_and_emits_human_attached(briefing_board) -> None:
    base, root = briefing_board
    status, attach = _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK
    assert attach["doc"]["meta"]["id"] == "feat_001"
    assert "decision_log" in attach
    assert attach["recent_messages"] == []

    events, _ = read_events("feat_001", 0, root=root)
    assert any(
        e.type == "HumanAttached"
        and e.payload.get("graph_id") == "feat_001"
        and e.payload.get("tier") == "feature"
        for e in events
    )


def test_attach_accepts_hierarchical_feature_id(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=True)
    feature_id = "feat_007_001"
    add_doc(root, id="epic_007", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id=feature_id, title="Feature", tier="feature", parent="epic_007")
    pin_parent(feature_id, "epic_007", root=root)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    commit_board(root)
    assert activate_epic("epic_007", "human", root=root).ok
    approve_board_feature(root, feature_id)
    assert dispatch_feature(feature_id, "human", root=root).ok

    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, attach = _post(
            f"http://127.0.0.1:{port}/api/attach",
            {"graph_id": feature_id},
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert status == HTTPStatus.OK
    assert attach["doc"]["meta"]["id"] == feature_id
    assert (root / ".cascade" / "checkpoints" / f"{feature_id}.sqlite").is_file()


def test_detach_emits_human_detached(briefing_board) -> None:
    base, root = briefing_board
    _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    status, _ = _post(f"{base}/api/detach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK

    events, _ = read_events("feat_001", 0, root=root)
    assert any(e.type == "HumanDetached" for e in events)
