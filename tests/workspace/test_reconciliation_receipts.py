"""Closeout reconciliation receipts across Task, Feature, and Epic tiers."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.lifecycle_review_gate import (
    require_lifecycle_review_gate,
    require_task_reconciliation_closeout,
)
from cascade.workspace import (
    ArchitectureBaseline,
    ArchitectureProposalError,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
    ProjectContext,
    ReconciledDesign,
    ReconciliationReceipt,
    create_architecture_artifact_ref,
    record_reconciliation_receipt,
    resolve_design_ownership,
    validate_reconciliation_closeout,
)
from tests.support import add_doc, make_repo


@pytest.mark.parametrize(
    ("tier", "work_id", "lineage"),
    (
        ("task", "task_034_006_003", "feature:feat_034_006"),
        ("feature", "feat_034_006", "epic:epic_034"),
        ("epic", "epic_034", "product:main"),
    ),
)
def test_code_only_no_change_receipt_closes_each_tier(
    tmp_path: Path, tier: str, work_id: str, lineage: str
) -> None:
    project, store, design, head = _reviewed_no_change(tmp_path, tier, work_id, lineage)
    current = store.resolve_current(lineage, lineage_revision=head)
    assert current is not None
    receipt = _receipt(
        project, work_id, tier, lineage, head, design,
        pointer=current.pointer_id, generation=current.generation,
    )

    record_reconciliation_receipt(project, receipt, review_store=store)

    assert validate_reconciliation_closeout(
        project, work_id, tier, implementation_revision=head, review_store=store
    ) == receipt


def test_material_mismatch_blocks_then_reviewed_update_receipt_clears(
    tmp_path: Path,
) -> None:
    project, store, design, head = _reviewed_no_change(
        tmp_path, "feature", "feat_034_006", "epic:epic_034"
    )
    current = store.resolve_current("epic:epic_034", lineage_revision=head)
    assert current is not None
    mismatch = replace(
        _receipt(
            project, "feat_034_006", "feature", "epic:epic_034", head, design,
            pointer=current.pointer_id, generation=current.generation,
        ),
        state="material_mismatch",
        mismatch_reasons=("containers view omits the landed worker",),
    )
    record_reconciliation_receipt(project, mismatch, review_store=store)

    with pytest.raises(ArchitectureProposalError, match="material_mismatch"):
        validate_reconciliation_closeout(
            project, "feat_034_006", "feature", implementation_revision=head,
            review_store=store,
        )

    accepted = replace(
        mismatch,
        outcome="accepted_update",
        accepted_review_unit_id=current.accepted_review_unit_id,
        no_change_reason=None,
        state="reconciled",
        mismatch_reasons=(),
    )
    record_reconciliation_receipt(project, accepted, review_store=store)

    assert validate_reconciliation_closeout(
        project, "feat_034_006", "feature", implementation_revision=head,
        review_store=store,
    ) == accepted


def test_stale_implementation_and_pending_split_promotion_hold_closeout(
    tmp_path: Path,
) -> None:
    project, store, design, head = _reviewed_no_change(
        tmp_path, "task", "task_034_006_003", "feature:feat_034_006"
    )
    current = store.resolve_current("feature:feat_034_006", lineage_revision=head)
    assert current is not None
    receipt = _receipt(
        project, "task_034_006_003", "task", "feature:feat_034_006", head, design,
        pointer=current.pointer_id, generation=current.generation,
    )
    record_reconciliation_receipt(project, receipt, review_store=store)
    changed = _commit(project.target.root, "implementation.py", "changed\n")

    with pytest.raises(ArchitectureProposalError, match="stale_reconciliation"):
        validate_reconciliation_closeout(
            project, "task_034_006_003", "task", implementation_revision=changed,
            review_store=store,
        )

    store.set_acceptance_hold(("task_034_006_003",), "promotion-split-1")
    with pytest.raises(ArchitectureProposalError, match="acceptance_pending"):
        validate_reconciliation_closeout(
            project, "task_034_006_003", "task", implementation_revision=head,
            review_store=store,
        )


def test_receipt_is_enforced_by_feature_and_task_terminal_lifecycle_paths(
    tmp_path: Path,
) -> None:
    feature_project, feature_store, feature_design, feature_head = _reviewed_no_change(
        tmp_path / "feature", "feature", "feat_034_006", "epic:epic_034"
    )
    feature_store.enable_gate_rollout(1)
    feature_store.bind_gate_policy("feat_034_006", 1)
    with pytest.raises(ArchitectureProposalError, match="missing_reconciliation"):
        require_lifecycle_review_gate(
            "feat_034_006", "closeout", root=feature_project.target.root
        )
    feature_current = feature_store.resolve_current(
        "epic:epic_034", lineage_revision=feature_head
    )
    assert feature_current is not None
    record_reconciliation_receipt(
        feature_project,
        _receipt(
            feature_project, "feat_034_006", "feature", "epic:epic_034",
            feature_head, feature_design, pointer=feature_current.pointer_id,
            generation=feature_current.generation,
        ),
        review_store=feature_store,
    )
    assert require_lifecycle_review_gate(
        "feat_034_006", "closeout", root=feature_project.target.root
    ).rollout_version == 1

    task_project, task_store, task_design, task_head = _reviewed_no_change(
        tmp_path / "task", "task", "task_034_006_003", "feature:feat_034_006"
    )
    task_store.enable_gate_rollout(1)
    task_store.bind_gate_policy("task_034_006_003", 1)
    with pytest.raises(ArchitectureProposalError, match="missing_reconciliation"):
        require_task_reconciliation_closeout(
            "task_034_006_003", root=task_project.target.root
        )
    task_current = task_store.resolve_current(
        "feature:feat_034_006", lineage_revision=task_head
    )
    assert task_current is not None
    record_reconciliation_receipt(
        task_project,
        _receipt(
            task_project, "task_034_006_003", "task", "feature:feat_034_006",
            task_head, task_design, pointer=task_current.pointer_id,
            generation=task_current.generation,
        ),
        review_store=task_store,
    )
    require_task_reconciliation_closeout(
        "task_034_006_003", root=task_project.target.root
    )

def _reviewed_no_change(
    tmp_path: Path, tier: str, work_id: str, lineage: str
) -> tuple[ProjectContext, ArchitectureReviewStore, PinnedArchitectureArtifact, str]:
    root = make_repo(tmp_path)
    parent = None
    if tier in {"feature", "task"}:
        add_doc(root, id="epic_034", title="Architecture", tier="epic", status="active")
        parent = "epic_034"
    if tier == "task":
        add_doc(
            root, id="feat_034_006", title="Scoped design", tier="feature",
            status="active", parent="epic_034",
        )
        parent = "feat_034_006"
    add_doc(
        root, id=work_id, title="Reconciliation", tier=tier, status="active",
        parent=parent,
    )
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    root.joinpath("DESIGN.md").write_text("# Reconciled design\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add work and architecture")
    head = _git(root, "rev-parse", "HEAD")
    doc_path = next((root / "docs" / f"{tier}s" / "2_active").glob(f"{work_id}_*.md"))
    plan = PinnedDocumentRef(
        project.target.repository_key, "target", doc_path.relative_to(root), head,
        _digest(doc_path.read_bytes()),
    )
    design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work=work_id),
        _digest(root.joinpath("DESIGN.md").read_bytes()),
    )
    unit = ArchitectureReviewUnit(
        owner_work_id=work_id,
        authorized_owner=f"{tier}-team",
        target_repository_key=project.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=project.target.repository_key,
        integration_lineage=lineage,
        documentation_repository_key=project.target_repository_key,
        documentation_repository_role="target",
        documentation_destination_path=Path("."),
        proposed_ancestor_context=None,
        accepted_baseline=ArchitectureBaseline.empty(),
        baseline_pointer_id=None,
        baseline_generation=None,
        rollout_version=1,
        status="staged",
        plan=plan,
        design=design,
        proposed_model=None,
        requirement_citations=("REQ-ROOT-012",),
        decision_citations=("dec_003",),
        view_citations=(),
        affected_work_ids=(work_id,),
        architecture_impact="no_diagram_change",
        impact_reason="The code-only change does not alter the C4 model",
    )
    store = ArchitectureReviewStore(project)
    store.save(unit)
    store.record_review(
        unit.review_unit_id,
        reviewer="architecture-owner",
        decision="reviewed",
        reviewed_at="2026-11-10T12:00:00+00:00",
    )
    store.approve_review_unit(unit.review_unit_id)
    store.accept(unit.review_unit_id, integration_revision=head, expected_generation=None)
    return project, store, design, head


def _receipt(
    project: ProjectContext,
    work_id: str,
    tier: str,
    lineage: str,
    head: str,
    design: PinnedArchitectureArtifact,
    *,
    pointer: str,
    generation: int,
) -> ReconciliationReceipt:
    return ReconciliationReceipt(
        work_id=work_id,
        tier=tier,
        target_repository_key=project.target_repository_key,
        integration_lineage=lineage,
        implementation_revisions=(head,),
        implementation_head=head,
        affected_code_directories=(Path("."),),
        leaf_designs=(ReconciledDesign(design, design),),
        ancestor_designs=(),
        baseline_pointer_id=pointer,
        baseline_generation=generation,
        semantic_artifact_digest=None,
        affected_view_keys=(),
        outcome="no_change",
        no_change_reason="Inspected implementation is code-only; design and C4 views remain accurate.",
    )


def _commit(root: Path, path: str, content: str) -> str:
    root.joinpath(path).write_text(content, encoding="utf-8")
    _git(root, "add", path)
    _git(root, "commit", "-m", f"change {path}")
    return _git(root, "rev-parse", "HEAD")


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
