"""Corrective-feature approval isolation and visible human blockers."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.approvals import approve_feature
from cascade.board.store import read_doc, write_doc
from cascade.comments import comment, read_change_request_handoffs, read_comments
from cascade.epic.change_dispositions import (
    apply_impact_disposition,
    read_impact_disposition_outcomes,
    require_corrective_feature_ready_for_approval,
    sign_off_corrective_plan,
)
from cascade.epic.impact_decisions import record_impact_decision
from tests.support import add_doc, declare_no_dependencies, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    (root / "cascade.toml").write_text("[automation]\nenabled = false\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Changed backlog feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    accepted = add_doc(
        root,
        id="feat_002",
        title="Accepted sibling",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    accepted.meta.approved_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    write_doc(accepted, root=root)
    epic = read_doc("epic_001", root=root)
    epic.meta.plan_approved_at = datetime(2026, 11, 1, tzinfo=timezone.utc)
    epic.meta.provider = "codex"
    epic.meta.models = {
        "epic_manager": "offered",
        "epic_architect": "offered",
        "swe": "offered",
    }
    write_doc(epic, root=root)
    declare_no_dependencies("epic_001", root=root)
    return root


def _decision(board: Path, disposition: str) -> tuple[str, str]:
    comment_id = comment(
        "feat_001",
        "Scope",
        "The accepted sibling changes this plan.",
        author="human",
        root=board,
    )
    handoff = next(
        row
        for row in read_change_request_handoffs(root=board)
        if row.root_comment_id == comment_id
    )
    decision = record_impact_decision(
        handoff.id,
        "material",
        ["accepted_work"],
        disposition,
        "Apply the safe Epic disposition.",
        epic_id="epic_001",
        root=board,
    )
    return str(decision["id"]), comment_id


def _inventory() -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def test_corrective_feature_has_accepted_dependency_and_fresh_revision_gate(
    board: Path,
) -> None:
    decision_id, comment_id = _decision(board, "corrective_feature")

    applied = apply_impact_disposition(
        decision_id,
        title="Repair accepted behavior",
        plan="Restore the accepted API without rewriting its history.",
        epic_id="epic_001",
        root=board,
    )
    replay = apply_impact_disposition(
        decision_id,
        title="Repair accepted behavior",
        plan="Restore the accepted API without rewriting its history.",
        epic_id="epic_001",
        root=board,
    )

    assert replay == applied
    corrective_id = str(applied["corrective_feature_id"])
    corrective = read_doc(corrective_id, root=board)
    assert corrective.meta.status == "backlog"
    assert corrective.meta.depends_on == ["feat_002"]
    assert corrective.meta.approved_at is None
    assert decision_id in corrective.body
    assert comment_id in corrective.body
    assert "feat_001" in corrective.body
    assert applied["ready_for_human_approval"] is False
    assert applied["human_approved"] is False
    assert len(read_impact_disposition_outcomes(root=board)) == 1

    revision = str(applied["plan_revision"])
    with pytest.raises(ValueError, match="epic_manager, epic_architect"):
        require_corrective_feature_ready_for_approval(corrective_id, root=board)
    with pytest.raises(ValueError, match="current-revision sign-off"):
        approve_feature(corrective_id, root=board, inventory=_inventory())
    sign_off_corrective_plan(
        decision_id,
        revision,
        epic_id="epic_001",
        root=board,
        author="epic_manager",
    )

    corrective = read_doc(corrective_id, root=board)
    corrective.body += "\n\nRevised after review.\n"
    write_doc(corrective, root=board)
    current_revision = str(
        apply_impact_disposition(
            decision_id,
            title="Repair accepted behavior",
            plan="Restore the accepted API without rewriting its history.",
            epic_id="epic_001",
            root=board,
        )["plan_revision"]
    )
    assert current_revision != revision
    with pytest.raises(ValueError, match="stale corrective plan revision"):
        sign_off_corrective_plan(
            decision_id,
            revision,
            epic_id="epic_001",
            root=board,
            author="epic_architect",
        )
    for role in ("epic_manager", "epic_architect"):
        signed = sign_off_corrective_plan(
            decision_id,
            current_revision,
            epic_id="epic_001",
            root=board,
            author=role,
        )
    assert signed["ready_for_human_approval"] is True
    require_corrective_feature_ready_for_approval(corrective_id, root=board)
    approved = approve_feature(corrective_id, root=board, inventory=_inventory())
    assert approved["newly_approved"] is True
    assert read_doc(corrective_id, root=board).meta.approved_at is not None
    after_approval = apply_impact_disposition(
        decision_id,
        title="Repair accepted behavior",
        plan="Restore the accepted API without rewriting its history.",
        epic_id="epic_001",
        root=board,
    )
    assert after_approval["plan_revision"] == current_revision
    assert after_approval["ready_for_human_approval"] is True
    assert after_approval["human_approved"] is True

    replies = [
        row
        for row in read_comments("feat_001", root=board)
        if row.parent == comment_id and "Corrective feature" in row.body
    ]
    assert len(replies) == 1
    assert "Affected work remains held" in replies[0].body
    assert read_doc("feat_002", root=board).meta.status == "completed"


def test_human_blocker_is_actionable_durable_and_does_not_reset_work(
    board: Path,
) -> None:
    decision_id, comment_id = _decision(board, "human_blocker")
    before = {
        work_id: (read_doc(work_id, root=board).meta.status, read_doc(work_id, root=board).meta.approved_at)
        for work_id in ("feat_001", "feat_002")
    }

    action = "Choose a replacement feature or authorize a revised Epic plan."
    first = apply_impact_disposition(
        decision_id,
        requested_human_action=action,
        epic_id="epic_001",
        root=board,
    )
    replay = apply_impact_disposition(
        decision_id,
        requested_human_action=action,
        epic_id="epic_001",
        root=board,
    )

    assert replay == first
    assert first["disposition"] == "human_blocker"
    assert first["corrective_feature_id"] is None
    assert first["affected_work_ids"] == ["feat_001"]
    assert {
        work_id: (read_doc(work_id, root=board).meta.status, read_doc(work_id, root=board).meta.approved_at)
        for work_id in ("feat_001", "feat_002")
    } == before
    replies = [
        row
        for row in read_comments("feat_001", root=board)
        if row.parent == comment_id and "Human decision required" in row.body
    ]
    assert len(replies) == 1
    assert action in replies[0].body
    assert "No work was returned to backlog" in replies[0].body
    assert len(read_impact_disposition_outcomes(root=board)) == 1


def test_disposition_kind_rejects_the_other_kind_inputs(board: Path) -> None:
    decision_id, _ = _decision(board, "human_blocker")
    with pytest.raises(ValueError, match="human blocker does not accept"):
        apply_impact_disposition(
            decision_id,
            title="Not authorized",
            plan="Must not mint.",
            requested_human_action="Replace it.",
            epic_id="epic_001",
            root=board,
        )
