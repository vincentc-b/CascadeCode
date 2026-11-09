"""Persistence and integration-lineage checks for architecture review units."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    ArchitectureBaseline,
    ArchitectureModelBinding,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
    ProjectContext,
    ProposedAncestorContext,
    WorkspaceError,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    resolve_design_ownership,
)


def test_review_unit_round_trips_complete_v1_tuple_and_explicit_empty_baseline(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    ancestor = ProposedAncestorContext("architecture-review-ancestor", None, None)
    unit = _unit(project, plan, design, model, proposed_ancestor_context=ancestor)

    store = ArchitectureReviewStore(project)
    identity = store.save(unit)

    assert store.get(identity) == unit
    assert unit.accepted_baseline == ArchitectureBaseline.empty()
    assert unit.proposed_ancestor_context == ancestor
    assert store.baseline_status(unit).stale is False
    payload = json.loads(store.path.read_text(encoding="utf-8"))
    persisted = payload["review_units"][identity]
    assert persisted["authorized_owner"] == "feature-team"
    assert persisted["code_directory"] == "."
    assert persisted["documentation_destination_path"] == "."
    assert persisted["plan"]["revision"] == plan.revision
    assert persisted["plan"]["content_digest"] == plan.content_digest
    assert persisted["design"]["content_digest"] == design.content_digest
    assert persisted["proposed_model"]["contract"]["reference"]["revision"] == model.contract.reference.revision
    assert persisted["proposed_model"]["sources"][0]["content_digest"] == model.sources[0].content_digest
    assert persisted["proposed_model"]["source_closure_digest"] == "2" * 64
    assert persisted["proposed_model"]["renderer_image_digest"] == "sha256:" + "3" * 64
    assert persisted["proposed_model"]["semantic_artifact_digest"] == "4" * 64
    assert persisted["accepted_baseline"]["kind"] == "empty_baseline"
    assert "implementation_commit" not in persisted

    with pytest.raises(WorkspaceError, match="requires a pinned model closure"):
        replace(unit, proposed_model=None)


def test_save_rejects_content_digest_that_does_not_match_pinned_commit(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    unit = _unit(project, replace(plan, content_digest="0" * 64), design, model)

    with pytest.raises(WorkspaceError, match="digest does not match"):
        ArchitectureReviewStore(project).save(unit)


def test_no_diagram_change_is_explicit_and_preserves_empty_baseline(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    unit = replace(
        _unit(project, plan, design, model),
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="The reviewed plan does not alter architecture diagrams",
    )
    store = ArchitectureReviewStore(project)
    unit_id = store.save(unit)
    revision = _git(project.target.root, "rev-parse", "HEAD")

    accepted = store.accept(
        unit_id,
        integration_revision=revision,
        expected_generation=None,
    )

    assert accepted.baseline == ArchitectureBaseline.empty()
    assert accepted.accepted_design == design


def test_accepted_child_advances_only_its_lineage_with_monotonic_generation(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    repository = project.target.root
    starting_trunk = _git(repository, "rev-parse", "HEAD")
    store = ArchitectureReviewStore(project)
    first = _unit(project, plan, design, model)
    first_id = store.save(first)

    _git(repository, "checkout", "-b", "feature/child")
    repository.joinpath("implementation.txt").write_text("accepted child\n", encoding="utf-8")
    _git(repository, "add", "implementation.txt")
    _git(repository, "commit", "-m", "child implementation")
    child_revision = _git(repository, "rev-parse", "HEAD")
    accepted = store.accept(
        first_id,
        accepted_code_head=child_revision,
        accepted_documentation_head=starting_trunk,
        expected_generation=None,
    )
    assert accepted.generation == 1
    assert accepted.accepted_tuple_digest == first.reviewed_tuple_digest
    assert accepted.accepted_code_head == child_revision
    assert accepted.accepted_documentation_head == starting_trunk
    assert accepted.baseline.model == model
    assert store.accept(
        first_id,
        accepted_code_head=child_revision,
        accepted_documentation_head=starting_trunk,
        expected_generation=None,
    ) == accepted

    assert _git(repository, "rev-parse", "main") == starting_trunk
    assert store.resolve_current("epic:epic_034", lineage_revision=starting_trunk) is None

    _git(repository, "checkout", "main")
    _git(repository, "checkout", "-b", "epic/epic_034")
    _git(repository, "merge", "--no-ff", "feature/child", "-m", "merge accepted child")
    epic_revision = _git(repository, "rev-parse", "HEAD")
    current = store.resolve_current("epic:epic_034", lineage_revision=epic_revision)
    assert current == accepted

    follow_up = replace(
        first,
        accepted_baseline=current.baseline,
        baseline_pointer_id=current.pointer_id,
        baseline_generation=current.generation,
        proposed_ancestor_context=ProposedAncestorContext(
            first_id, current.pointer_id, current.generation
        ),
        impact_reason="Follow-up reviewed against the accepted child",
    )
    assert store.baseline_status(follow_up, lineage_revision=epic_revision).stale is False
    assert store.baseline_status(first, lineage_revision=epic_revision).rebase_required is True

    follow_up_id = store.save(follow_up)
    second = store.accept(
        follow_up_id,
        integration_revision=epic_revision,
        expected_generation=1,
    )
    assert second.generation == 2
    with pytest.raises(WorkspaceError, match="generation changed"):
        store.accept(
            store.save(replace(follow_up, impact_reason="A competing proposal")),
            integration_revision=epic_revision,
            expected_generation=1,
        )


def _unit(
    project: ProjectContext,
    plan: PinnedDocumentRef,
    design: PinnedArchitectureArtifact,
    model: ArchitectureModelBinding,
    *,
    proposed_ancestor_context: ProposedAncestorContext | None = None,
) -> ArchitectureReviewUnit:
    return ArchitectureReviewUnit(
        owner_work_id="feat_034_003",
        authorized_owner="feature-team",
        target_repository_key=project.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=project.target.repository_key,
        integration_lineage="epic:epic_034",
        documentation_repository_key=project.target_repository_key,
        documentation_repository_role="target",
        documentation_destination_path=Path("."),
        proposed_ancestor_context=proposed_ancestor_context,
        accepted_baseline=ArchitectureBaseline.empty(),
        baseline_pointer_id=None,
        baseline_generation=None,
        rollout_version=1,
        status="staged",
        plan=plan,
        design=design,
        proposed_model=model,
        requirement_citations=("REQ-ROOT-001",),
        decision_citations=("dec_001",),
        view_citations=("containers",),
        affected_work_ids=("feat_034_003",),
        architecture_impact="diagram_change",
        impact_reason="The proposal changes the container model",
    )


def _review_repository(tmp_path: Path):
    root = tmp_path / "repository"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "tests@example.test")
    _git(root, "config", "user.name", "Cascade Tests")
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    root.joinpath("DESIGN.md").write_text("# Reviewed design\n", encoding="utf-8")
    plan_path = root / "plans" / "feat_034_003.md"
    plan_path.parent.mkdir()
    plan_path.write_text("# Reviewed plan\n", encoding="utf-8")
    architecture = project.editable_architecture_root
    architecture.mkdir(parents=True, exist_ok=True)
    contract_path = architecture / "workspace.contract.json"
    contract_path.write_text('{"workspace":{"owner":"feat_034_003"}}\n', encoding="utf-8")
    source_path = architecture / "model.dsl"
    source_path.write_text("workspace {}\n", encoding="utf-8")
    _git(root, "add", ".")
    _git(root, "commit", "-m", "reviewed architecture inputs")
    revision = _git(root, "rev-parse", "HEAD")
    plan = PinnedDocumentRef(
        project.target.repository_key,
        "target",
        Path("plans/feat_034_003.md"),
        revision,
        _digest(plan_path.read_bytes()),
    )
    design_ref = create_architecture_artifact_ref(project, ".", owning_work="feat_034_003")
    contract_ref = create_architecture_model_ref(
        project, ".", "workspace.contract.json", owning_work="feat_034_003"
    )
    source_ref = create_architecture_model_ref(
        project, ".", "model.dsl", owning_work="feat_034_003"
    )
    design = PinnedArchitectureArtifact(design_ref, _digest(root.joinpath("DESIGN.md").read_bytes()))
    model = ArchitectureModelBinding(
        contract=PinnedArchitectureArtifact(contract_ref, _digest(contract_path.read_bytes())),
        sources=(PinnedArchitectureArtifact(source_ref, _digest(source_path.read_bytes())),),
        source_closure_digest="2" * 64,
        renderer_image_digest="sha256:" + "3" * 64,
        renderer_settings=(("timeout_seconds", 90.0),),
        semantic_artifact_digest="4" * 64,
    )
    return project, plan, design, model


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode != 0:
        raise AssertionError(result.stderr)
    return result.stdout.strip()
