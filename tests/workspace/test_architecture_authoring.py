"""Scoped architecture authoring and owner-amendment routing."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import mcp_tool_catalog as planning_tool_catalog
from cascade.task.swe_mcp import mcp_tool_catalog as task_tool_catalog
from cascade.watchdog.events import read_events
from cascade.architecture_context_tools import (
    read_epic_architecture_amendments,
    read_feature_architecture_amendments,
)
from cascade.workspace import (
    ArchitectureAuthoringIntent,
    ArchitectureProposalError,
    ArchitectureReviewStore,
    read_owner_amendments,
    review_architecture_proposal,
    stage_owned_architecture_change,
)
from tests.support import add_doc
from tests.workspace.test_architecture_review import _review_repository, _unit


@pytest.mark.parametrize(
    ("work_id", "tier", "actor"),
    (
        ("epic_034", "epic", "epic-team"),
        ("feat_034_006", "feature", "feature-team"),
        ("task_034_006_002", "task", "task-team"),
    ),
)
def test_each_tier_can_stage_and_review_its_owned_design(
    tmp_path: Path, work_id: str, tier: str, actor: str
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    parent = None
    if tier in {"feature", "task"}:
        add_doc(
            project.tracking.root,
            id="epic_034",
            title="Parent epic",
            tier="epic",
            status="active",
        )
        parent = "epic_034"
    if tier == "task":
        add_doc(
            project.tracking.root,
            id="feat_034_006",
            title="Parent feature",
            tier="feature",
            status="active",
            parent="epic_034",
        )
        parent = "feat_034_006"
    add_doc(
        project.tracking.root,
        id=work_id,
        title="Architecture owner",
        tier=tier,  # type: ignore[arg-type]
        status="active",
        parent=parent,
    )
    proposal = _owned_proposal(
        project, plan, design, model, work_id=work_id, actor=actor
    )

    result = stage_owned_architecture_change(
        project,
        ArchitectureAuthoringIntent(work_id, actor, proposal, None),
    )

    assert result.disposition == "owner_staged_review"
    assert result.staged is not None
    assert result.staged.status == "staged"
    reviewed = review_architecture_proposal(
        project,
        owner=actor,
        unit_id=result.staged.unit.review_unit_id,
        expected_tuple_digest=result.staged.unit.reviewed_tuple_digest,
        decision="reviewed",
    )
    assert reviewed.status == "reviewed"


def test_task_owned_change_stages_but_feature_summary_routes_to_feature_owner(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    root = project.tracking.root
    add_doc(root, id="epic_034", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_034_006",
        title="Feature owner",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    add_doc(
        root,
        id="task_034_006_002",
        title="Task author",
        tier="task",
        status="active",
        parent="feat_034_006",
    )
    proposal = _owned_proposal(
        project,
        plan,
        design,
        model,
        work_id="feat_034_006",
        actor="feature-team",
    )
    intent = ArchitectureAuthoringIntent(
        "task_034_006_002",
        "task-team",
        proposal,
        None,
        "cmt_closeout_001",
    )

    first = stage_owned_architecture_change(project, intent)
    retried = stage_owned_architecture_change(project, intent)

    assert first.disposition == "routed_owner_amendment"
    assert retried.amendment == first.amendment
    assert ArchitectureReviewStore(project).get(proposal.review_unit_id) is None
    assert read_owner_amendments(
        project, owning_work_id="feat_034_006"
    ) == (first.amendment,)
    assert read_feature_architecture_amendments(
        feature_id="feat_034_006", root=root
    ) == [first.amendment.to_dict()]
    assert read_epic_architecture_amendments(epic_id="epic_034", root=root) == []
    events, _ = read_events("feat_034_006", 0, root=root)
    routed = [event for event in events if event.type == "ArchitectureAmendmentRequested"]
    assert len(routed) == 1
    assert routed[0].payload["originating_comment_id"] == "cmt_closeout_001"
    assert routed[0].payload["requirement_ids"] == ["REQ-ROOT-001"]

    owner_result = stage_owned_architecture_change(
        project,
        ArchitectureAuthoringIntent(
            "feat_034_006", "feature-team", proposal, None, "cmt_closeout_001"
        ),
    )
    assert owner_result.disposition == "owner_staged_review"
    assert owner_result.staged is not None


def test_external_amendment_read_schemas_do_not_accept_owner_overrides() -> None:
    catalogs = (
        planning_tool_catalog("epic", ["read_architecture_amendments"]),
        planning_tool_catalog("feature", ["read_architecture_amendments"]),
        task_tool_catalog(["read_architecture_amendments"]),
    )

    for catalog in catalogs:
        schema = catalog[0]["inputSchema"]
        assert schema["properties"] == {}
        assert schema["additionalProperties"] is False


def test_feature_to_epic_architecture_change_routes_to_epic_owner(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    root = project.tracking.root
    add_doc(root, id="epic_034", title="Epic owner", tier="epic", status="active")
    add_doc(
        root,
        id="feat_034_006",
        title="Feature author",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    proposal = _owned_proposal(
        project,
        plan,
        design,
        model,
        work_id="epic_034",
        actor="epic-team",
    )

    result = stage_owned_architecture_change(
        project,
        ArchitectureAuthoringIntent(
            "feat_034_006", "feature-team", proposal, None, "cmt_arch_001"
        ),
    )

    assert result.amendment is not None
    assert result.amendment.owning_work_id == "epic_034"
    assert result.amendment.proposal == proposal
    assert ArchitectureReviewStore(project).get(proposal.review_unit_id) is None


def test_cross_owner_and_mixed_shared_fragment_requests_write_nothing(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    root = project.tracking.root
    add_doc(root, id="epic_034", title="Epic", tier="epic", status="active")
    add_doc(root, id="epic_999", title="Other epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_034_006",
        title="Feature author",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    foreign = _owned_proposal(
        project,
        plan,
        design,
        model,
        work_id="epic_999",
        actor="other-epic-team",
    )

    with pytest.raises(ArchitectureProposalError, match="ancestor scope"):
        stage_owned_architecture_change(
            project,
            ArchitectureAuthoringIntent(
                "feat_034_006", "feature-team", foreign, None
            ),
        )

    mixed = replace(
        foreign,
        owner_work_id="epic_034",
        authorized_owner="epic-team",
        design=replace(
            foreign.design,
            reference=replace(foreign.design.reference, owning_work="feat_034_006"),
        ),
    )
    with pytest.raises(ArchitectureProposalError, match="share the proposal owner"):
        stage_owned_architecture_change(
            project,
            ArchitectureAuthoringIntent(
                "feat_034_006", "feature-team", mixed, None
            ),
        )

    assert not (root / "architecture" / "owner-amendments.json").exists()
    assert not ArchitectureReviewStore(project).path.exists()


def _owned_proposal(
    project, plan, design, model, *, work_id: str, actor: str
):
    owned_design = replace(
        design,
        reference=replace(design.reference, owning_work=work_id),
    )
    return replace(
        _unit(project, plan, owned_design, model),
        owner_work_id=work_id,
        authorized_owner=actor,
        status="draft",
        proposed_model=None,
        affected_work_ids=(work_id,),
        architecture_impact="no_diagram_change",
        impact_reason="The reviewed requirement and design change has no C4 impact",
    )
