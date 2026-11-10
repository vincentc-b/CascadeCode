"""Accountable feature-comment routing and replay behavior."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    dispatch_planning_tool,
    mcp_tool_catalog,
)
from cascade.comments import (
    CommentHandoffError,
    comment,
    read_change_request_handoffs,
    read_comments,
    reply_comment,
    route_feature_comment,
)
from cascade.epic.stubs import read_comment as epic_read_comment
from cascade.epic.stubs import reply_comment as epic_reply_comment
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
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
        title="Backlog feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    return root


def test_live_feature_comment_has_one_durable_feature_handoff(board: Path) -> None:
    comment_id = comment(
        "feat_001",
        "API contracts",
        "Keep this compatible",
        anchor="Widget.open",
        line_start=12,
        line_end=14,
        doc_sha="abc123",
        semantic_anchor={"symbol": "Widget.open"},
        blocks=["task_001"],
        author="human",
        root=board,
    )

    rows = read_change_request_handoffs(root=board)
    assert len(rows) == 1
    handoff = rows[0]
    assert handoff.root_comment_id == comment_id
    assert handoff.thread_id == comment_id
    assert handoff.source_feature_id == "feat_001"
    assert handoff.affected_work_ids == ("feat_001", "task_001")
    assert handoff.receiving_owner == "feat_001"
    assert handoff.receiving_team == "feature"
    assert handoff.purpose == "initial_delivery"
    assert handoff.status == "delivered"
    assert handoff.event_identity.startswith("CommentPosted:crh_")
    assert handoff.source_context["anchor"] == "Widget.open"
    assert handoff.source_context["semantic_anchor"] == {"symbol": "Widget.open"}

    record = next(
        row for row in read_comments("feat_001", root=board) if row.id == comment_id
    )
    replay = route_feature_comment(record, root=board)
    assert replay is not None and replay.id == handoff.id
    events, _ = read_events("feat_001", 0, root=board)
    assert [event.payload["handoff_id"] for event in events] == [handoff.id]

    # Simulate a process dying after queue append but before its ledger status
    # update.  Retry discovers the event identity and does not fan out a turn.
    ledger = board / "docs" / "_comments" / "_change_request_handoffs.jsonl"
    persisted = json.loads(ledger.read_text(encoding="utf-8"))
    persisted[0]["status"] = "pending"
    persisted[0]["delivered_at"] = None
    ledger.write_text(json.dumps(persisted), encoding="utf-8")
    retried = route_feature_comment(record, root=board)
    assert retried is not None and retried.status == "delivered"
    events, _ = read_events("feat_001", 0, root=board)
    assert [event.payload["handoff_id"] for event in events] == [handoff.id]

    # Corrupt durable identity must fail closed rather than fan out a new turn.
    ledger.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(CommentHandoffError, match="ledger is malformed"):
        route_feature_comment(record, root=board)
    events, _ = read_events("feat_001", 0, root=board)
    assert [event.payload["handoff_id"] for event in events] == [handoff.id]


def test_backlog_feature_comment_routes_once_to_active_epic_with_context(
    board: Path,
) -> None:
    comment_id = comment(
        "feat_002",
        "Scope",
        "Please include the accepted sibling",
        anchor="Dependencies",
        author="human",
        root=board,
    )

    feature_events, _ = read_events("feat_002", 0, root=board)
    assert feature_events == []
    epic_events, _ = read_events("epic_001", 0, root=board)
    assert len(epic_events) == 1
    event = epic_events[0]
    assert event.type == "CommentPosted"
    assert event.payload["feature_id"] == "feat_002"
    assert event.payload["root_comment_id"] == comment_id
    assert event.payload["thread_id"] == comment_id
    assert event.payload["anchor"] == "Dependencies"
    assert event.payload["delivery_purpose"] == "initial_delivery"

    [handoff] = read_change_request_handoffs(root=board, source_feature_id="feat_002")
    assert handoff.receiving_owner == "epic_001"
    assert handoff.receiving_team == "epic"

    assert (
        epic_read_comment(
            comment_id, epic_id="epic_001", doc_id="feat_002", root=board
        )["body"]
        == "Please include the accepted sibling"
    )
    reply_id = epic_reply_comment(
        comment_id,
        "We will account for it.",
        epic_id="epic_001",
        doc_id="feat_002",
        root=board,
    )
    reply = next(
        row for row in read_comments("feat_002", root=board) if row.id == reply_id
    )
    assert reply.parent == comment_id


def test_live_feature_has_one_explicit_epic_escalation(board: Path) -> None:
    comment_id = comment(
        "feat_001", "Plan", "Change the contract", author="human", root=board
    )
    reply_id = reply_comment(
        "feat_001",
        comment_id,
        "I am escalating this for impact triage.",
        author="feature_lead",
        root=board,
    )
    [catalog_entry] = mcp_tool_catalog("feature", ["escalate_comment_to_epic"])
    assert catalog_entry["inputSchema"]["required"] == ["comment_id", "reason"]
    collector = ToolEffectCollector()
    first = dispatch_planning_tool(
        "feature",
        "escalate_comment_to_epic",
        {
            "comment_id": comment_id,
            "reason": "The request changes a sibling contract.",
            "affected_work_ids": ["feat_001", "feat_002"],
        },
        scope_id="feat_001",
        repo_root=board,
        collector=collector,
    )
    replay = dispatch_planning_tool(
        "feature",
        "escalate_comment_to_epic",
        {
            "comment_id": comment_id,
            "reason": "A retried escalation must retain its first accepted scope.",
            "affected_work_ids": ["feat_001"],
        },
        scope_id="feat_001",
        repo_root=board,
        collector=collector,
    )
    assert [effect.tool for effect in collector.effects] == [
        "escalate_comment_to_epic",
        "escalate_comment_to_epic",
    ]
    assert replay["id"] == first["id"]
    assert replay["affected_work_ids"] == ["feat_001", "feat_002"]
    assert first["purpose"] == "epic_impact_triage"
    assert first["receiving_owner"] == "epic_001"
    source_context = first["source_context"]
    assert isinstance(source_context, dict)
    assert source_context["escalation_reason"] == (
        "The request changes a sibling contract."
    )
    assert [row["id"] for row in source_context["source_thread"]] == [
        comment_id,
        reply_id,
    ]

    events, _ = read_events("epic_001", 0, root=board)
    escalation_events = [
        event
        for event in events
        if event.payload.get("delivery_purpose") == "epic_impact_triage"
    ]
    assert len(escalation_events) == 1
    handoffs = read_change_request_handoffs(root=board, source_feature_id="feat_001")
    assert [row.purpose for row in handoffs] == [
        "initial_delivery",
        "epic_impact_triage",
    ]
