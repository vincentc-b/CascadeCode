"""Authenticated architecture publication through normal planning tools."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    dispatch_planning_tool,
    mcp_tool_catalog,
)
from cascade.board.context import set_project_context
from cascade.board.store import read_doc, write_doc
from cascade.feature.registry import feature_tools
from cascade.feature.wiring import load_feature_tools
from cascade.workspace.architecture import (
    create_architecture_artifact_ref,
    resolve_design_ownership,
)
from cascade.workspace.architecture_review import (
    ArchitectureBaseline,
    ArchitectureProposalError,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
)
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, commit_board, make_repo


@pytest.fixture(autouse=True)
def _clear_project_context():
    set_project_context(None)
    yield
    set_project_context(None)


def test_feature_architect_publishes_explicit_no_change_idempotently(
    tmp_path: Path,
) -> None:
    root, project, revision, proposal = _publication_repo(tmp_path)
    set_project_context(project)
    collector = ToolEffectCollector()
    args = {
        "proposal": proposal.to_dict(),
        "expected_plan_revision": revision,
        "expected_generation": None,
    }

    first = dispatch_planning_tool(
        "feature", "publish_architecture_review", args,
        scope_id="feat_046_001", repo_root=root, collector=collector,
        role="feature_architect",
    )
    replay = dispatch_planning_tool(
        "feature", "publish_architecture_review", args,
        scope_id="feat_046_001", repo_root=root, collector=collector,
        role="feature_architect",
    )

    assert first == replay
    assert first["status"] == "no_diagram_change"
    assert first["render_operation_id"] is None
    assert first["review_unit_id"]
    durable = ArchitectureReviewStore(project).get(first["review_unit_id"])
    assert durable is not None
    assert durable.owner_work_id == "feat_046_001"
    assert durable.authorized_owner == "feature_architect"
    assert durable.architecture_impact == "no_diagram_change"
    assert ArchitectureReviewStore(project).acceptance_hold("feat_046_001") is None


def test_publication_rejects_stale_plan_before_persisting_intent(tmp_path: Path) -> None:
    root, project, revision, proposal = _publication_repo(tmp_path)
    set_project_context(project)
    plan_path = next(root.glob("docs/features/2_active/feat_046_001_*.md"))
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\nChanged.\n", encoding="utf-8")
    subprocess.run(["git", "add", plan_path.as_posix()], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "change plan"], cwd=root, check=True)

    with pytest.raises(ArchitectureProposalError) as raised:
        dispatch_planning_tool(
            "feature", "publish_architecture_review",
            {
                "proposal": proposal.to_dict(),
                "expected_plan_revision": revision,
                "expected_generation": None,
            },
            scope_id="feat_046_001", repo_root=root,
            collector=ToolEffectCollector(), role="feature_architect",
        )

    assert raised.value.code == "stale_revision"
    assert not (root / ".cascade" / "architecture-publications.json").exists()


def test_feature_publication_routes_ancestor_owned_design_to_epic(tmp_path: Path) -> None:
    root, project, revision, proposal = _publication_repo(tmp_path)
    set_project_context(project)
    ancestor_design = replace(
        proposal.design,
        reference=replace(proposal.design.reference, owning_work="epic_046"),
    )
    routed = replace(proposal, design=ancestor_design)

    result = dispatch_planning_tool(
        "feature", "publish_architecture_review",
        {
            "proposal": routed.to_dict(),
            "expected_plan_revision": revision,
            "expected_generation": None,
        },
        scope_id="feat_046_001", repo_root=root,
        collector=ToolEffectCollector(), role="feature_architect",
    )

    assert result["status"] == "routed"
    assert result["amendment_id"].startswith("architecture-amendment-")
    assert result["review_unit_id"] is None
    assert ArchitectureReviewStore(project).units_affecting("epic_046") == ()


def test_publication_is_registered_schema_bound_and_architect_only(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_046", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_046_001", title="Feature", tier="feature",
        status="active", parent="epic_046",
    )
    load_feature_tools()
    assert "publish_architecture_review" in feature_tools()
    schema = mcp_tool_catalog("feature", ["publish_architecture_review"])[0]["inputSchema"]
    assert schema["required"] == [
        "proposal", "expected_plan_revision", "expected_generation"
    ]
    assert schema["additionalProperties"] is False

    with pytest.raises(PermissionError, match="architecture planning role"):
        dispatch_planning_tool(
            "feature", "publish_architecture_review", {},
            scope_id="feat_046_001", repo_root=root,
            collector=ToolEffectCollector(), role="feature_lead",
        )


def _publication_repo(
    tmp_path: Path,
) -> tuple[Path, ProjectContext, str, ArchitectureReviewUnit]:
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_046", title="Epic", tier="epic", status="active")
    feature = add_doc(
        root, id="feat_046_001", title="Feature", tier="feature",
        status="active", parent="epic_046",
    )
    assert epic.sha is not None
    feature.meta.parent_rev = epic.sha
    write_doc(feature, root=root)
    feature = read_doc("feat_046_001", root=root)
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    (root / "DESIGN.md").write_text("# Feature design\n", encoding="utf-8")
    commit_board(root, "architecture publication inputs")
    revision = read_doc("feat_046_001", root=root).sha
    assert revision is not None
    plan_path = feature.meta.path.resolve().relative_to(root)
    plan = PinnedDocumentRef(
        project.target.repository_key, "target", plan_path, revision,
        hashlib.sha256((root / plan_path).read_bytes()).hexdigest(),
    )
    design_ref = create_architecture_artifact_ref(
        project, ".", owning_work="feat_046_001"
    )
    design = PinnedArchitectureArtifact(
        design_ref, hashlib.sha256((root / "DESIGN.md").read_bytes()).hexdigest()
    )
    proposal = ArchitectureReviewUnit(
        owner_work_id="epic_client_spoof",
        authorized_owner="client-spoof",
        target_repository_key=project.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=project.target.repository_key,
        integration_lineage="epic:epic_046",
        documentation_repository_key=project.target_repository_key,
        documentation_repository_role="target",
        documentation_destination_path=Path("."),
        proposed_ancestor_context=None,
        accepted_baseline=ArchitectureBaseline.empty(),
        baseline_pointer_id=None,
        baseline_generation=None,
        rollout_version=1,
        status="draft",
        plan=plan,
        design=design,
        proposed_model=None,
        requirement_citations=("REQ-046-001",),
        decision_citations=("DEC-046-001",),
        view_citations=(),
        affected_work_ids=("feat_046_001",),
        architecture_impact="no_diagram_change",
        impact_reason="The committed plan changes delivery only, not the C4 model.",
    )
    return root, project, revision, proposal
