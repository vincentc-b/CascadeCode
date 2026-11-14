"""Authenticated architecture publication through normal planning tools."""

from __future__ import annotations

import hashlib
import json
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
    review_architecture_proposal,
    stage_architecture_proposal,
)
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
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


def test_publication_and_http_review_use_owning_worktree_lineage(tmp_path: Path) -> None:
    from cascade.workspace.integration_worktree import create_integration_worktree
    from cascade.war_room.architecture_routes import review_projection

    root, project, _revision, proposal = _publication_repo(tmp_path)
    record = create_integration_worktree(
        "feature", "feat_046_001", branch="feat/feat_046_001", base_ref="HEAD", trunk=root,
    )
    plan_path = record.path / proposal.plan.path
    plan_path.write_text(plan_path.read_text() + "\nWorktree-only plan change.\n")
    design_path = record.path / "DESIGN.md"
    design_path.write_text("# Feature design\n\nWorktree-only design change.\n")
    subprocess.run(["git", "add", "."], cwd=record.path, check=True)
    subprocess.run(["git", "commit", "-qm", "worktree architecture"], cwd=record.path, check=True)
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=record.path, text=True).strip()
    proposal = replace(
        proposal,
        # Colocated planning tools can identify a plan by either repository role.
        plan=replace(proposal.plan, repository_role="tracking", revision=revision,
                     content_digest=hashlib.sha256(plan_path.read_bytes()).hexdigest()),
        design=replace(proposal.design, reference=replace(proposal.design.reference, revision=revision),
                       content_digest=hashlib.sha256(design_path.read_bytes()).hexdigest()),
    )
    set_project_context(project)
    result = dispatch_planning_tool(
        "feature", "publish_architecture_review",
        {"proposal": proposal.to_dict(), "expected_plan_revision": revision, "expected_generation": None},
        scope_id="feat_046_001", repo_root=record.path, collector=ToolEffectCollector(), role="feature_architect",
    )
    assert result["status"] == "no_diagram_change", result
    projection = review_projection(root, "feat_046_001")
    assert projection["state"] == "no_diagram_change"
    assert projection["architecture_impact"] == "no_diagram_change"
    assert projection["approval_context"]["review_unit_id"] == result["review_unit_id"]

    # The fix must still reject a genuinely changed artifact on that branch.
    design_path.write_text("# Changed after publication\n")
    subprocess.run(["git", "add", "."], cwd=record.path, check=True)
    subprocess.run(["git", "commit", "-qm", "invalidate design"], cwd=record.path, check=True)
    assert review_projection(root, "feat_046_001")["state"] == "stale_revision"


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


def test_owned_branch_publication_retries_changed_bytes_and_refreshes_stale_review(
    tmp_path: Path,
) -> None:
    root, project, _, proposal = _publication_repo(tmp_path)
    worktree = _owner_worktree(root, "feature", "feat_046_001")
    plan_path = next(worktree.glob("docs/features/2_active/feat_046_001_*.md"))
    plan_path.write_text(plan_path.read_text(encoding="utf-8") + "\nOwned revision.\n", encoding="utf-8")
    (worktree / "DESIGN.md").write_text("# Owned feature design\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "owned architecture inputs"], cwd=worktree, check=True)
    owned_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=worktree, text=True
    ).strip()
    plan = replace(
        proposal.plan,
        revision=owned_head,
        content_digest=hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    )
    design = replace(
        proposal.design,
        reference=replace(proposal.design.reference, revision=owned_head),
        content_digest=hashlib.sha256((worktree / "DESIGN.md").read_bytes()).hexdigest(),
    )
    owned = replace(proposal, plan=plan, design=design)
    set_project_context(project)
    args = {
        "proposal": owned.to_dict(),
        "expected_plan_revision": owned_head,
        "expected_generation": None,
    }
    original_design = (worktree / "DESIGN.md").read_bytes()
    (worktree / "DESIGN.md").write_text("# Uncommitted replacement\n", encoding="utf-8")

    failed = dispatch_planning_tool(
        "feature", "publish_architecture_review", args,
        scope_id="feat_046_001", repo_root=worktree,
        collector=ToolEffectCollector(), role="feature_architect",
    )
    assert failed["status"] == "superseded"
    assert failed["reason_code"] == "artifact_changed"
    failed_proposal = json.loads(
        (root / ".cascade" / "architecture-publications.json").read_text(encoding="utf-8")
    )["operations"][failed["operation_id"]]["proposal"]

    (worktree / "DESIGN.md").write_bytes(original_design)
    retried = dispatch_planning_tool(
        "feature", "publish_architecture_review", args,
        scope_id="feat_046_001", repo_root=worktree,
        collector=ToolEffectCollector(), role="feature_architect",
    )
    assert retried["operation_id"] == failed["operation_id"]
    assert retried["status"] == "no_diagram_change"
    ledger = json.loads(
        (root / ".cascade" / "architecture-publications.json").read_text(encoding="utf-8")
    )
    row = ledger["operations"][retried["operation_id"]]
    assert row["proposal"] == failed_proposal
    assert row["failure_history"][-1]["reason_code"] == "artifact_changed"

    reviewed = review_architecture_proposal(
        project,
        owner="feature_architect",
        unit_id=str(retried["review_unit_id"]),
        expected_tuple_digest=str(retried["reviewed_tuple_digest"]),
        decision="reviewed",
        reviewed_at="2026-11-13T00:00:00+00:00",
    )
    assert reviewed.unit is not None and reviewed.unit.status == "reviewed"

    (root / "unrelated.txt").write_text("trunk movement\n", encoding="utf-8")
    subprocess.run(["git", "add", "unrelated.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "unrelated trunk movement"], cwd=root, check=True)
    trunk_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()
    unchanged = ArchitectureReviewStore(project).refresh(
        str(retried["review_unit_id"]), lineage_revision=trunk_head
    )
    assert unchanged.status == "reviewed"

    (worktree / "DESIGN.md").write_text("# Later design refresh\n", encoding="utf-8")
    subprocess.run(["git", "add", "DESIGN.md"], cwd=worktree, check=True)
    subprocess.run(["git", "commit", "-m", "refresh design"], cwd=worktree, check=True)
    refreshed = ArchitectureReviewStore(project).refresh(
        str(retried["review_unit_id"]), lineage_revision=trunk_head
    )
    assert refreshed.status == "stale"
    assert ArchitectureReviewStore(project).get_invalidation_reasons(
        refreshed.review_unit_id
    ) == ("artifact_changed",)


def test_split_owned_heads_keep_tracking_plan_and_product_design_distinct(
    tmp_path: Path,
) -> None:
    target_parent = tmp_path / "target"
    tracking_parent = tmp_path / "tracking"
    target_parent.mkdir()
    tracking_parent.mkdir()
    target = make_repo(target_parent)
    tracking = make_repo(tracking_parent)
    project = ProjectContext.split(target, tracking)
    resolve_design_ownership(project, ".")
    (target / "DESIGN.md").write_text("# Trunk design\n", encoding="utf-8")
    commit_board(target, "target architecture base")
    commit_board(tracking, "tracking base")
    target_worktree = _owner_worktree(target, "feature", "feat_046_001")
    tracking_worktree = _owner_worktree(tracking, "feature", "feat_046_001")
    (target_worktree / "DESIGN.md").write_text("# Owned product design\n", encoding="utf-8")
    subprocess.run(["git", "add", "DESIGN.md"], cwd=target_worktree, check=True)
    subprocess.run(["git", "commit", "-m", "owned product design"], cwd=target_worktree, check=True)
    plan_path = tracking_worktree / "plans" / "feat_046_001.md"
    plan_path.parent.mkdir()
    plan_path.write_text("# Owned tracking plan\n", encoding="utf-8")
    subprocess.run(["git", "add", "plans/feat_046_001.md"], cwd=tracking_worktree, check=True)
    subprocess.run(["git", "commit", "-m", "owned tracking plan"], cwd=tracking_worktree, check=True)
    product_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=target_worktree, text=True
    ).strip()
    tracking_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=tracking_worktree, text=True
    ).strip()
    plan = PinnedDocumentRef(
        project.tracking.repository_key,
        "tracking",
        Path("plans/feat_046_001.md"),
        tracking_head,
        hashlib.sha256(plan_path.read_bytes()).hexdigest(),
    )
    design_reference = create_architecture_artifact_ref(
        project, ".", owning_work="feat_046_001"
    )
    design = PinnedArchitectureArtifact(
        replace(design_reference, revision=product_head),
        hashlib.sha256((target_worktree / "DESIGN.md").read_bytes()).hexdigest(),
    )
    proposal = ArchitectureReviewUnit(
        owner_work_id="feat_046_001",
        authorized_owner="feature_architect",
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
        impact_reason="The split-repository change does not alter diagrams.",
    )

    staged = stage_architecture_proposal(
        project,
        owner="feature_architect",
        work_id="feat_046_001",
        proposal=proposal,
        expected_generation=None,
        lineage_revision=product_head,
        plan_work_id="feat_046_001",
    )
    assert staged.unit is not None
    assert staged.unit.plan.revision == tracking_head
    assert staged.unit.design.reference.revision == product_head
    reviewed = review_architecture_proposal(
        project,
        owner="feature_architect",
        unit_id=staged.unit.review_unit_id,
        expected_tuple_digest=staged.unit.reviewed_tuple_digest,
        decision="reviewed",
        reviewed_at="2026-11-13T00:00:00+00:00",
    )
    assert reviewed.unit is not None and reviewed.unit.status == "reviewed"

    plan_path.write_text("# Changed tracking plan\n", encoding="utf-8")
    refreshed = ArchitectureReviewStore(project).refresh(staged.unit.review_unit_id)
    assert refreshed.status == "stale"
    assert ArchitectureReviewStore(project).get_invalidation_reasons(
        refreshed.review_unit_id
    ) == ("artifact_changed",)


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


def _owner_worktree(root: Path, kind: str, work_id: str) -> Path:
    prefix = {"epic": "epic", "feature": "feat", "task": "task"}[kind]
    branch = f"{prefix}/{work_id}"
    worktree = root / ".cascade" / "worktrees" / f"{prefix}_{work_id}"
    worktree.parent.mkdir(parents=True, exist_ok=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    subprocess.run(
        ["git", "worktree", "add", "-qb", branch, str(worktree)], cwd=root, check=True
    )
    save_registry(
        root,
        [IntegrationWorktree(kind, work_id, branch, worktree, base)],
    )
    return worktree
