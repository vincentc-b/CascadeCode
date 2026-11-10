"""Authoritative epic-plan readiness and approval gate (task_015_001_003)."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.approvals import approve_epic_plan, epic_plan_approved
from cascade.board.store import read_doc, write_doc
from cascade.comments.store import comment, resolve_comment
from cascade.epic.plan_readiness import (
    PlanNotReadyForApproval,
    compute_epic_plan_readiness,
    require_epic_plan_ready_for_approval,
)
from cascade.epic.planning_signoffs import (
    canonical_plan_revision,
    sign_off_epic_plan,
)
from tests.support import (
    EPIC_BODY,
    add_doc,
    approve_epic_plan_when_ready,
    commit_board,
    declare_no_dependencies,
    make_repo,
    sign_off_both_planning_roles,
)


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    commit_board(root, "initial")
    declare_no_dependencies("epic_001", root=root)
    return root


def _revision(board: Path) -> str:
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None
    return revision


def _epic_row(payload: dict, epic_id: str = "epic_001") -> dict:
    for column in ("1_backlog", "2_active", "3_completed"):
        for row in payload["epics"][column]:
            if row["id"] == epic_id:
                return row
    raise KeyError(epic_id)


def test_fresh_activation_is_planning_and_blocks_approval(board: Path) -> None:
    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "planning"
    assert readiness.can_approve_plan is False
    assert readiness.approve_disabled_reason == "missing_epic_manager_sign_off"
    assert readiness.sign_offs == {}

    with pytest.raises(PlanNotReadyForApproval):
        approve_epic_plan("epic_001", root=board)


def test_one_sign_off_still_blocks_approval(board: Path) -> None:
    revision = _revision(board)
    sign_off_epic_plan(
        "epic_001",
        "epic_manager",
        revision,
        root=board,
        actor="epic_manager",
    )
    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "planning"
    assert readiness.can_approve_plan is False
    assert readiness.approve_disabled_reason == "missing_epic_architect_sign_off"
    assert set(readiness.sign_offs) == {"epic_manager"}

    with pytest.raises(PlanNotReadyForApproval):
        approve_epic_plan("epic_001", root=board)


def test_open_questions_block_readiness_even_with_sign_offs(board: Path) -> None:
    sign_off_both_planning_roles("epic_001", root=board)
    comment(
        "epic_001",
        "Open questions",
        "Scope?",
        author="human",
        root=board,
    )

    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "planning"
    assert readiness.can_approve_plan is False
    assert readiness.approve_disabled_reason == "unresolved_open_questions"

    with pytest.raises(PlanNotReadyForApproval):
        approve_epic_plan("epic_001", root=board)


def test_both_sign_offs_enable_approval_and_read_model(board: Path) -> None:
    revision = _revision(board)
    sign_off_both_planning_roles("epic_001", root=board)

    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "ready_for_review"
    assert readiness.can_approve_plan is True
    assert readiness.approve_disabled_reason is None
    assert readiness.plan_revision == revision
    assert set(readiness.sign_offs) == {"epic_manager", "epic_architect"}

    require_epic_plan_ready_for_approval("epic_001", root=board)
    approve_epic_plan("epic_001", root=board)
    assert epic_plan_approved("epic_001", root=board)


def test_revision_change_resets_readiness(board: Path) -> None:
    revision_a = _revision(board)
    sign_off_both_planning_roles("epic_001", root=board)
    assert (
        compute_epic_plan_readiness("epic_001", root=board).status == "ready_for_review"
    )

    epic = read_doc("epic_001", root=board)
    epic.body = EPIC_BODY.replace("None yet.", "Revised scope.")
    write_doc(epic, root=board)
    commit_board(board, "plan edit")
    revision_b = _revision(board)
    assert revision_b != revision_a

    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "planning"
    assert readiness.sign_offs == {}
    assert readiness.can_approve_plan is False

    with pytest.raises(PlanNotReadyForApproval):
        approve_epic_plan("epic_001", root=board)


def test_approved_epic_omits_readiness(board: Path) -> None:
    approve_epic_plan_when_ready("epic_001", root=board)
    assert compute_epic_plan_readiness("epic_001", root=board) is None


@pytest.mark.parametrize(
    ("setup", "expected_reason"),
    [
        ("none", "missing_epic_manager_sign_off"),
        ("manager_only", "missing_epic_architect_sign_off"),
    ],
)
def test_readiness_disabled_reasons(
    board: Path,
    setup: str,
    expected_reason: str,
) -> None:
    if setup == "manager_only":
        revision = _revision(board)
        sign_off_epic_plan(
            "epic_001",
            "epic_manager",
            revision,
            root=board,
            actor="epic_manager",
        )
    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.approve_disabled_reason == expected_reason


def test_board_and_doc_read_models_match_commands(board: Path) -> None:
    from cascade.war_room.server import serve

    sign_off_both_planning_roles("epic_001", root=board)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=board, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        board_req = urllib.request.Request(f"http://127.0.0.1:{port}/api/board")
        with urllib.request.urlopen(board_req) as resp:
            board_payload = json.loads(resp.read().decode())
        row = _epic_row(board_payload)
        assert row["plan_readiness"]["status"] == "ready_for_review"
        assert row["plan_readiness"]["can_approve_plan"] is True
        assert row["dependency_status"] == row["plan_readiness"]["dependency_status"]

        doc_req = urllib.request.Request(f"http://127.0.0.1:{port}/api/doc/epic_001")
        with urllib.request.urlopen(doc_req) as resp:
            doc_payload = json.loads(resp.read().decode())
        board_readiness = row["plan_readiness"]
        doc_readiness = doc_payload["plan_readiness"]
        board_observed_at = board_readiness["dependency_status"].pop("observed_at")
        doc_observed_at = doc_readiness["dependency_status"].pop("observed_at")
        assert board_observed_at
        assert doc_observed_at
        assert doc_readiness == board_readiness

        blocked = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/approve_epic_plan",
            method="POST",
            data=json.dumps({"id": "epic_002"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError):
            urllib.request.urlopen(blocked)

        approve = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/approve_epic_plan",
            method="POST",
            data=json.dumps({"id": "epic_001"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(approve) as resp:
            assert resp.status == HTTPStatus.OK
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_resolved_questions_restore_ready_state(board: Path) -> None:
    sign_off_both_planning_roles("epic_001", root=board)
    comment_id = comment(
        "epic_001",
        "Open questions",
        "Scope?",
        author="human",
        root=board,
    )
    blocked = compute_epic_plan_readiness("epic_001", root=board)
    assert blocked is not None
    assert blocked.can_approve_plan is False

    resolve_comment("epic_001", comment_id, author="human", root=board)
    readiness = compute_epic_plan_readiness("epic_001", root=board)
    assert readiness is not None
    assert readiness.status == "ready_for_review"
    assert readiness.can_approve_plan is True


def test_board_projection_reuses_snapshot_but_authorization_refreshes(board, monkeypatch):
    from cascade.epic.plan_readiness import project_epic_plan_readiness
    from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
    import cascade.planning_action_dependencies as boundary
    snapshot = merged_board(board)
    calls = []
    original = boundary.refresh_merged_board
    def refresh(root):
        calls.append(root)
        return original(root)
    monkeypatch.setattr(boundary, 'refresh_merged_board', refresh)
    with merged_board_snapshot(board, snapshot):
        projected = project_epic_plan_readiness('epic_001', root=board, board=snapshot)
        assert projected is not None
        assert not calls
        authoritative = compute_epic_plan_readiness('epic_001', root=board, board=snapshot)
        assert authoritative is not None
        assert len(calls) == 1
    assert projected.status == authoritative.status
    assert projected.dependency_status.outcome == authoritative.dependency_status.outcome


def test_board_serialization_does_not_refresh_per_epic(board, monkeypatch):
    from cascade.war_room.serialize import board_view_from_index
    from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
    import cascade.planning_action_dependencies as boundary
    snapshot = merged_board(board)
    monkeypatch.setattr(boundary, 'refresh_merged_board', lambda root: pytest.fail('read-only board refreshed authorization evidence'))
    with merged_board_snapshot(board, snapshot):
        payload = board_view_from_index(snapshot, root=board)
    assert _epic_row(payload)['plan_readiness']['status'] == 'planning'
