"""Persistence and integration-lineage checks for architecture review units."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.workspace import (
    ArchitectureBaseline,
    ArchitectureModelBinding,
    ArchitectureProposalError,
    ArchitectureReviewRecord,
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
    C4RenderArtifact,
    C4RenderSettings,
    PinnedArchitectureArtifact,
    PinnedDocumentRef,
    ProjectContext,
    ProposedAncestorContext,
    WorkspaceError,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    materialize_c4_source_closure,
    resolve_design_ownership,
    read_architecture_state,
    review_architecture_proposal,
    stage_architecture_proposal,
)


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_VERSIONED_WORKSPACE = (
    _REPOSITORY_ROOT / "architecture" / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
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


def test_owner_can_stage_inspect_and_review_without_advancing_accepted_state(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    proposal = replace(
        _unit(project, plan, design, model),
        status="draft",
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="The plan changes review workflow but not architecture diagrams",
    )

    staged = stage_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=proposal,
        expected_generation=None,
    )

    assert staged.status == "staged"
    assert staged.accepted is None
    assert staged.semantic_diff and staged.semantic_diff.state == "unchanged"
    inspected = read_architecture_state(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        lineage="epic:epic_034",
    )
    assert inspected == staged

    reviewed = review_architecture_proposal(
        project,
        owner="feature-team",
        unit_id=proposal.review_unit_id,
        expected_tuple_digest=proposal.reviewed_tuple_digest,
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )

    assert reviewed.status == "reviewed"
    assert reviewed.accepted is None
    assert reviewed.review and reviewed.review.reviewer == "feature-team"
    assert reviewed.review.tuple_digest == proposal.reviewed_tuple_digest
    state = json.loads(ArchitectureReviewStore(project).path.read_text(encoding="utf-8"))
    assert state["lineages"] == {}


def test_review_unit_id_stays_stable_across_status_transition(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    staged = _unit(project, plan, design, model)
    store = ArchitectureReviewStore(project)
    store.save(staged)

    reviewed = store.record_review(
        staged.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )

    assert reviewed.review_unit_id == staged.review_unit_id
    assert reviewed.reviewed_tuple_digest == staged.reviewed_tuple_digest
    assert store.get(staged.review_unit_id) == reviewed
    assert store.get_review(staged.review_unit_id) == ArchitectureReviewRecord(
        staged.review_unit_id,
        "feature-team",
        "2026-11-09T12:00:00+00:00",
        staged.reviewed_tuple_digest,
        "reviewed",
    )


def test_owner_scope_and_stale_generation_fail_before_persistence(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    proposal = replace(
        _unit(project, plan, design, model),
        status="draft",
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="No diagram change is needed",
    )

    with pytest.raises(ArchitectureProposalError, match="owner_denied"):
        stage_architecture_proposal(
            project,
            owner="another-team",
            work_id="feat_034_003",
            proposal=proposal,
            expected_generation=None,
        )
    with pytest.raises(ArchitectureProposalError, match="stale_baseline"):
        stage_architecture_proposal(
            project,
            owner="feature-team",
            work_id="feat_034_003",
            proposal=proposal,
            expected_generation=1,
        )
    assert not ArchitectureReviewStore(project).path.exists()

    stage_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=proposal,
        expected_generation=None,
    )
    with pytest.raises(ArchitectureProposalError, match="owner_denied"):
        read_architecture_state(
            project,
            owner="another-team",
            work_id="feat_034_003",
            lineage="epic:epic_034",
        )


def test_claimed_diagram_change_with_invalid_pinned_model_is_not_reviewable(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    settings = (
        ("cpus", "2"),
        ("memory", "1536m"),
        ("pids_limit", 256),
        ("timeout_seconds", 90.0),
        ("tmpfs_size", "512m"),
    )
    proposal = replace(
        _unit(project, plan, design, replace(model, renderer_settings=settings)),
        status="draft",
    )

    with pytest.raises(ArchitectureProposalError, match="model_invalid"):
        stage_architecture_proposal(
            project,
            owner="feature-team",
            work_id="feat_034_003",
            proposal=proposal,
            expected_generation=None,
        )

    assert not ArchitectureReviewStore(project).path.exists()


def test_no_diagram_proposal_stages_at_split_tracking_destination(
    tmp_path: Path,
) -> None:
    target = _git_repository(tmp_path / "target")
    tracking = _git_repository(tmp_path / "tracking")
    project = ProjectContext.split(target, tracking, architecture_destination="tracking")
    resolve_design_ownership(project, ".")
    plan_path = target / "plans" / "feat_034_003.md"
    plan_path.parent.mkdir()
    plan_path.write_text("# Reviewed plan\n", encoding="utf-8")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "record plan and design destination")
    plan_revision = _git(target, "rev-parse", "HEAD")
    design_path = project.design_path()
    design_path.parent.mkdir(parents=True)
    design_path.write_text("# Split reviewed design\n", encoding="utf-8")
    _git(tracking, "add", ".")
    _git(tracking, "commit", "-m", "record split design")
    design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work="feat_034_003"),
        _digest(design_path.read_bytes()),
    )
    plan = PinnedDocumentRef(
        project.target.repository_key,
        "target",
        Path("plans/feat_034_003.md"),
        plan_revision,
        _digest(plan_path.read_bytes()),
    )
    proposal = ArchitectureReviewUnit(
        owner_work_id="feat_034_003",
        authorized_owner="feature-team",
        target_repository_key=project.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=project.target.repository_key,
        integration_lineage="epic:epic_034",
        documentation_repository_key=project.tracking.repository_key,
        documentation_repository_role="tracking",
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
        requirement_citations=("REQ-ROOT-001",),
        decision_citations=("dec_001",),
        view_citations=(),
        affected_work_ids=("feat_034_003",),
        architecture_impact="no_diagram_change",
        impact_reason="The workflow change does not alter diagrams",
    )

    staged = stage_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=proposal,
        expected_generation=None,
    )

    assert staged.unit and staged.unit.documentation_repository_role == "tracking"
    assert staged.unit.design.reference.repository_path == design_path.relative_to(tracking)


def test_diagram_change_runs_pinned_closure_and_render_validation(tmp_path: Path) -> None:
    root = _git_repository(tmp_path / "repository")
    project = ProjectContext.colocated(root)
    resolve_design_ownership(project, ".")
    root.joinpath("DESIGN.md").write_text("# Reviewed design\n", encoding="utf-8")
    plan_path = root / "plans" / "feat_034_003.md"
    plan_path.parent.mkdir()
    plan_path.write_text("# Reviewed plan\n", encoding="utf-8")
    shutil.copytree(_VERSIONED_WORKSPACE, project.editable_architecture_root)
    _git(root, "add", ".")
    _git(root, "commit", "-m", "add reviewable model")
    revision = _git(root, "rev-parse", "HEAD")
    design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work="feat_034_003"),
        _digest(root.joinpath("DESIGN.md").read_bytes()),
    )
    contract = create_architecture_model_ref(
        project, ".", "workspace.contract.json", owning_work="feat_034_002"
    )
    sources = tuple(
        create_architecture_model_ref(project, ".", name, owning_work="feat_034_002")
        for name in ("workspace.dsl", "model.dsl", "views.dsl")
    )
    with tempfile.TemporaryDirectory() as directory:
        closure = materialize_c4_source_closure(
            project, contract, sources, Path(directory) / "source"
        )
        semantic = _semantic_workspace(closure.contract)
    semantic_path = tmp_path / "semantic.json"
    semantic_path.write_bytes(semantic)
    semantic_digest = _digest(semantic)
    settings = C4RenderSettings()
    model = ArchitectureModelBinding(
        contract=PinnedArchitectureArtifact(
            contract,
            _digest((project.editable_architecture_root / "workspace.contract.json").read_bytes()),
        ),
        sources=tuple(
            PinnedArchitectureArtifact(
                reference,
                _digest((root / reference.repository_path).read_bytes()),
            )
            for reference in sources
        ),
        source_closure_digest=closure.digest,
        renderer_image_digest="sha256:c89b54231c42da90484e6bf4e398f36a40123cb4b12c9d5f09c27eef3dc9644c",
        renderer_settings=tuple(sorted(settings.cache_payload().items())),
        semantic_artifact_digest=semantic_digest,
    )
    plan = PinnedDocumentRef(
        project.target.repository_key,
        "target",
        Path("plans/feat_034_003.md"),
        revision,
        _digest(plan_path.read_bytes()),
    )
    proposal = _unit(project, plan, design, model)
    proposal = replace(proposal, status="draft")
    renderer = _ReadyRenderer(semantic_path, semantic_digest)

    staged = stage_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=proposal,
        expected_generation=None,
        renderer=renderer,
    )

    assert staged.semantic_diff and staged.semantic_diff.state == "empty_baseline"
    inspected = read_architecture_state(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        lineage="epic:epic_034",
    )
    assert inspected.semantic_diff == staged.semantic_diff


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


def _git_repository(root: Path) -> Path:
    root.mkdir()
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "tests@example.test")
    _git(root, "config", "user.name", "Cascade Tests")
    root.joinpath("README.md").write_text("repository\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")
    return root


class _ReadyOperation:
    def __init__(self, result: C4RenderArtifact) -> None:
        self.result = result

    def wait(self, timeout: float | None = None) -> C4RenderArtifact:
        return self.result


class _ReadyRenderer:
    def __init__(self, semantic_path: Path, semantic_digest: str) -> None:
        self.semantic_path = semantic_path
        self.semantic_digest = semantic_digest

    def submit(self, closure, settings):
        return _ReadyOperation(
            C4RenderArtifact(
                status="ready",
                closure_digest=closure.digest,
                semantic_workspace=self.semantic_path,
                semantic_workspace_sha256=self.semantic_digest,
                source_diff_reference=f"revision:{closure.revision}",
                view_keys=tuple(sorted(view.key for view in closure.contract.views)),
                revision=closure.revision,
            )
        )


def _semantic_workspace(contract) -> bytes:
    elements = []
    export_ids = {}
    for index, element in enumerate(contract.elements, start=1):
        export_ids[element.dsl_identifier] = str(index)
        elements.append(
            {
                "id": str(index),
                "name": element.dsl_identifier,
                "properties": {"cascade.semanticId": element.semantic_id},
            }
        )
    relationships = []
    for index, relationship in enumerate(contract.relationships, start=100):
        relationships.append(
            {
                "id": str(index),
                "sourceId": export_ids[relationship.source],
                "destinationId": export_ids[relationship.destination],
                "properties": {"cascade.semanticId": relationship.semantic_id},
            }
        )
    views = [
        {
            "key": view.key,
            "elements": [{"id": value} for value in export_ids.values()],
            "relationships": [
                {"id": relationship["id"]} for relationship in relationships
            ],
        }
        for view in contract.views
    ]
    return json.dumps(
        {
            "model": {"softwareSystems": elements, "relationships": relationships},
            "views": {"systemLandscapeViews": views},
        },
        sort_keys=True,
    ).encode()


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
