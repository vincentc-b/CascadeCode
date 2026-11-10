"""Epic impact triage, evidence, relay, and replay behavior."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.comments import comment, read_change_request_handoffs, read_comments
from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.epic.impact_decisions import (
    EpicImpactDecisionError,
    read_epic_impact_decisions,
    record_impact_decision,
)
from cascade.feature.comments_tool import escalate_comment_to_epic
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Live feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Accepted sibling",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_003",
        title="Backlog feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    return root


def test_active_material_request_records_evidence_and_relays_once(board: Path) -> None:
    comment_id = comment(
        "feat_001", "Plan", "Keep this local", author="human", root=board
    )
    escalation = escalate_comment_to_epic(
        comment_id,
        "A sibling has already merged.",
        feature_id="feat_001",
        root=board,
        affected_work_ids=["feat_001"],
    )

    first = record_impact_decision(
        str(escalation["id"]),
        "material",
        ["feature_plan"],
        "open_work_amendment",
        "Revise the open feature plan and obtain fresh review.",
        epic_id="epic_001",
        root=board,
    )
    replay = record_impact_decision(
        str(escalation["id"]),
        "material",
        ["feature_plan"],
        "open_work_amendment",
        "Revise the open feature plan and obtain fresh review.",
        epic_id="epic_001",
        root=board,
    )

    assert replay == first
    assert first["accepted_sibling_ids"] == ["feat_002"]
    assert first["affected_work_ids"] == ["feat_001"]
    assert first["impact_reasons"] == ["feature_plan", "accepted_work"]
    assert first["decision_log_reference"] == "dec_001"
    assert first["originating_thread_reply_reference"]
    assert first["relayed"] is True
    [decision] = read_epic_impact_decisions(root=board)
    assert decision.id == first["id"]

    thread = read_comments("feat_001", root=board)
    relays = [row for row in thread if row.parent == comment_id and row.author == "epic_manager"]
    assert len(relays) == 1
    assert relays[0].state == "open"
    epic_body = next(
        path for path in (board / "docs" / "epics" / "2_active").glob("epic_001_*.md")
    ).read_text(encoding="utf-8")
    assert epic_body.count("Feature change impact triage") == 1


def test_backlog_request_uses_initial_epic_handoff(board: Path) -> None:
    comment_id = comment(
        "feat_003", "Scope", "Change sequencing", author="human", root=board
    )
    [handoff] = read_change_request_handoffs(
        root=board, source_feature_id="feat_003"
    )
    assert handoff.root_comment_id == comment_id
    assert handoff.purpose == "initial_delivery"

    decision = record_impact_decision(
        handoff.id,
        "material",
        ["sequencing"],
        "contract_amendment",
        "Update the dependency contract before dispatch.",
        epic_id="epic_001",
        root=board,
    )

    assert decision["source_feature_id"] == "feat_003"
    assert decision["accepted_sibling_ids"] == ["feat_002"]
    reply = next(
        row
        for row in read_comments("feat_003", root=board)
        if row.id == decision["originating_thread_reply_reference"]
    )
    assert reply.parent == comment_id
    assert reply.state == "open"


def test_active_initial_delivery_cannot_bypass_explicit_escalation(board: Path) -> None:
    comment(
        "feat_001", "Plan", "Change accepted work", author="human", root=board
    )
    [handoff] = read_change_request_handoffs(
        root=board, source_feature_id="feat_001"
    )

    with pytest.raises(
        EpicImpactDecisionError, match="delivered Epic handoff"
    ):
        record_impact_decision(
            handoff.id,
            "material",
            ["accepted_work"],
            "corrective_feature",
            "Create separately reviewed corrective work.",
            epic_id="epic_001",
            root=board,
        )


def test_duplicate_handoff_cannot_change_disposition(board: Path) -> None:
    comment_id = comment(
        "feat_003", "Scope", "Change architecture", author="human", root=board
    )
    [handoff] = read_change_request_handoffs(
        root=board, source_feature_id="feat_003"
    )
    record_impact_decision(
        handoff.id,
        "material",
        ["architecture"],
        "corrective_feature",
        "Create corrective work.",
        epic_id="epic_001",
        root=board,
    )

    with pytest.raises(EpicImpactDecisionError, match="different Epic decision"):
        record_impact_decision(
            handoff.id,
            "material",
            ["architecture"],
            "human_blocker",
            "Create corrective work.",
            epic_id="epic_001",
            root=board,
        )
    assert all(row.state == "open" for row in read_comments("feat_003", root=board))
    assert comment_id


def test_planning_dispatch_attributes_architect_decision(board: Path) -> None:
    comment(
        "feat_003", "Architecture", "Change the baseline", author="human", root=board
    )
    [handoff] = read_change_request_handoffs(
        root=board, source_feature_id="feat_003"
    )

    result = dispatch_planning_tool(
        "epic",
        "record_impact_decision",
        {
            "handoff_id": handoff.id,
            "materiality": "material",
            "impact_reasons": ["architecture"],
            "disposition": "open_work_amendment",
            "outcome": "Rebase the proposal and renew its review.",
        },
        scope_id="epic_001",
        repo_root=board,
        collector=ToolEffectCollector(),
        role="epic_architect",
    )

    assert isinstance(result, dict)
    assert result["decided_by"] == "epic_architect"
    reply = next(
        row
        for row in read_comments("feat_003", root=board)
        if row.id == result["originating_thread_reply_reference"]
    )
    assert reply.author == "epic_architect"
