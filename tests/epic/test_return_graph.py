"""Real production graph return: no injected snapshot or transition capability."""

from __future__ import annotations

import subprocess
import threading
from datetime import datetime, timezone

import pytest

from cascade.board.store import move_doc, read_doc, write_doc
from cascade.epic.lifecycle_gate import lifecycle_gate
from cascade.epic.return_command import (
    return_epic_to_backlog,
    load_return_eligibility_snapshot,
)
from cascade.epic.return_eligibility import evaluate_return_eligibility
from cascade.epic.return_graph import (
    return_home,
    read_manifest,
    holds_turn,
    reactivate_graph,
    recover_returns,
)
from cascade.epic.return_transaction import ActiveToBacklogTransaction, TransitionStep
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    merged_board,
    invalidate_merged_board,
)
from tests.support import add_doc, make_repo


def fixture_graph(tmp_path):
    root = make_repo(tmp_path)
    add_doc(root, id="epic_044", title="Return me", tier="epic")
    wt = ensure_integration_worktree(
        "epic", "epic_044", branch="epic/epic_044", base_ref="main", trunk=root
    )
    move_doc("epic_044", "active", root=wt.path)
    for suffix in ("001", "002", "003"):
        add_doc(
            root,
            id=f"feat_044_{suffix}",
            title=suffix,
            tier="feature",
            parent="epic_044",
        )
    add_doc(root, id="epic_045", title="Unrelated", tier="epic", status="active")
    return root, wt


def test_returns_epic_and_three_unapproved_children_without_touching_trunk(tmp_path):
    root, wt = fixture_graph(tmp_path)
    before = subprocess.check_output(["git", "status", "--porcelain"], cwd=root)
    original = read_doc_resolved("epic_044", root=root).body
    snapshot = load_return_eligibility_snapshot("epic_044", root=root)
    assert evaluate_return_eligibility(snapshot).eligible
    assert len(snapshot.graph) == 4
    result = return_epic_to_backlog("epic_044", "return-44", actor="human", root=root)
    assert result.ok, result.to_dict()
    board = merged_board(root)
    for id in ("epic_044", "feat_044_001", "feat_044_002", "feat_044_003"):
        assert board.by_id[id].status == "backlog"
        assert read_doc_resolved(id, root=root).meta.status == "backlog"
        assert holds_turn(id, root=root)
    assert read_doc_resolved("epic_044", root=root).body == original
    assert board.by_id["epic_045"].status == "active"
    assert wt.path.exists()
    assert subprocess.check_output(["git", "status", "--porcelain"], cwd=root) == before
    assert (
        read_doc("epic_044", root=wt.path).meta.status == "active"
    )  # preserved evidence
    assert return_epic_to_backlog("epic_044", "retry", actor="human", root=root).ok
    assert (
        len(list(return_home(root, "epic_044").rglob("epic-transition-audits/*.json")))
        == 1
    )


def test_approved_children_and_tasks_are_preserved_not_disqualified(tmp_path):
    root, wt = fixture_graph(tmp_path)
    doc = read_doc("feat_044_001", root=root)
    doc.meta.approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    move_doc("feat_044_001", "active", root=root)
    add_doc(
        root,
        id="task_044_001_001",
        title="Child task",
        tier="task",
        parent="feat_044_001",
    )
    assert return_epic_to_backlog("epic_044", "approved", actor="human", root=root).ok
    board = merged_board(root)
    assert board.by_id["feat_044_001"].approved_at == doc.meta.approved_at
    assert board.by_id["feat_044_001"].status == "backlog"
    assert board.by_id["task_044_001_001"].status == "backlog"


def test_missing_declared_child_refuses_before_publication(tmp_path):
    root, wt = fixture_graph(tmp_path)
    doc = read_doc("epic_044", root=wt.path)
    # Model missing on-disk graph provenance rather than weakening validation.
    text = doc.meta.path.read_text().replace(
        "children: []", "children:\n- feat_044_099"
    )
    doc.meta.path.write_text(text)
    invalidate_merged_board(root)
    result = return_epic_to_backlog("epic_044", "missing", actor="human", root=root)
    assert not result.ok
    assert "graph_incomplete" in result.eligibility.reason_codes
    assert read_manifest(root, "epic_044") is None


def test_live_turn_refuses_then_can_retry(tmp_path):
    root, wt = fixture_graph(tmp_path)
    with lifecycle_gate().turn("feat_044_001"):
        result = return_epic_to_backlog("epic_044", "busy", actor="human", root=root)
        assert not result.ok
        assert "turn_not_quiesced" in result.eligibility.reason_codes
    assert read_manifest(root, "epic_044") is None
    assert return_epic_to_backlog("epic_044", "busy", actor="human", root=root).ok


@pytest.mark.parametrize("boundary", tuple(TransitionStep))
def test_restart_recovers_every_journal_boundary(tmp_path, monkeypatch, boundary):
    root, wt = fixture_graph(tmp_path)
    original = ActiveToBacklogTransaction._save

    def crash(self, journal):
        original(self, journal)
        if journal.completed_steps[-1] == boundary:
            raise RuntimeError("simulated exit")

    with monkeypatch.context() as patch:
        patch.setattr(ActiveToBacklogTransaction, "_save", crash)
        with pytest.raises(RuntimeError, match="simulated exit"):
            return_epic_to_backlog("epic_044", "crash", actor="human", root=root)
    # Durable intent suppresses stale active copies before recovery finishes.
    invalidate_merged_board(root)
    assert merged_board(root).by_id["epic_044"].status == "backlog"
    assert holds_turn("epic_044", root=root)
    recover_returns(root=root)
    assert read_manifest(root, "epic_044")["state"] == "returned"
    assert (
        len(list(return_home(root, "epic_044").rglob("epic-transition-audits/*.json")))
        == 1
    )


def test_reactivation_restores_same_children_and_allows_another_return(tmp_path):
    root, wt = fixture_graph(tmp_path)
    assert return_epic_to_backlog("epic_044", "first", actor="human", root=root).ok
    reactivate_graph("epic_044", root=root)
    assert merged_board(root).by_id["epic_044"].status == "active"
    assert merged_board(root).by_id["feat_044_001"].status == "backlog"
    assert not holds_turn("epic_044", root=root)
    assert return_epic_to_backlog("epic_044", "second", actor="human", root=root).ok
    assert (
        len(list(return_home(root, "epic_044").rglob("epic-transition-audits/*.json")))
        == 2
    )


def test_actual_http_return_endpoint_and_board(tmp_path):
    from cascade.war_room.server import serve
    from tests.war_room.test_backlog_priority_api import _get, _post

    root, wt = fixture_graph(tmp_path)
    server = serve(root=root, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        _, board = _get(url + "/api/board")
        epic = next(m for m in board["epics"]["2_active"] if m["id"] == "epic_044")
        assert epic["return_to_backlog"]["eligible"]
        status, result = _post(
            url + "/api/return_epic_to_backlog",
            {"epic_id": "epic_044", "request_id": "http-return"},
        )
        assert status == 200 and result["ok"], result
        _, board = _get(url + "/api/board")
        assert any(m["id"] == "epic_044" for m in board["epics"]["1_backlog"])
        _, doc = _get(url + "/api/doc/feat_044_001")
        assert doc["meta"]["status"] == "backlog"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_reactivation_command_uses_retained_tree_and_fresh_checkpoint(
    tmp_path, monkeypatch
):
    from cascade.watchdog.dispatch import _activate_epic

    root, wt = fixture_graph(tmp_path)
    checkpoint = root / ".cascade/checkpoints/epic_044.sqlite"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    checkpoint.write_bytes(b"prior run evidence")
    assert return_epic_to_backlog("epic_044", "first", actor="human", root=root).ok
    monkeypatch.setattr(
        "cascade.watchdog.dispatch._provider_preflight_refusal",
        lambda *args, **kwargs: None,
    )
    result = _activate_epic("epic_044", "human", root)
    assert result.ok, result
    assert not checkpoint.exists()
    assert list((checkpoint.parent / "archive/epic_044").glob("*.sqlite"))
    assert merged_board(root).by_id["epic_044"].status == "active"
    assert read_doc_resolved("feat_044_001", root=root).meta.status == "backlog"
    assert return_epic_to_backlog("epic_044", "first", actor="human", root=root).ok
    assert merged_board(root).by_id["epic_044"].status == "active"


def test_concurrent_production_requests_publish_one_graph(tmp_path):
    root, wt = fixture_graph(tmp_path)
    results = []
    barrier = threading.Barrier(2)

    def request(id):
        barrier.wait(timeout=5)
        results.append(return_epic_to_backlog("epic_044", id, actor="human", root=root))

    workers = [threading.Thread(target=request, args=(id,)) for id in ("a", "b")]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=15)
        assert not worker.is_alive()
    assert len(results) == 2 and all(result.ok for result in results)
    assert (
        len(list(return_home(root, "epic_044").rglob("epic-transition-audits/*.json")))
        == 1
    )
