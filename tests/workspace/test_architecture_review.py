"""Persistence and integration-lineage checks for architecture review units."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.comments import (
    comment,
    read_change_request_handoffs,
    read_comments,
)
from cascade.epic.impact_decisions import EpicImpactDecision, record_impact_decision
from cascade.feature.comments_tool import escalate_comment_to_epic
from cascade.lifecycle_review_gate import require_lifecycle_review_gate
from cascade.scoped_change_holds import (
    ScopedChangeHoldError,
    create_scoped_change_hold,
    holds_affecting,
    release_revised_change_hold,
)
from cascade.watchdog import read_events

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
    PromotionHeads,
    ProjectContext,
    ProposedAncestorContext,
    WorkspaceError,
    create_architecture_artifact_ref,
    create_architecture_model_ref,
    enable_review_gate,
    materialize_c4_source_closure,
    promote_or_resume,
    resolve_design_ownership,
    read_architecture_state,
    rebase_architecture_proposal,
    reserve_promotion,
    review_architecture_proposal,
    stage_architecture_proposal,
    validate_review_gate,
)
from tests.support import add_doc


_REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
_VERSIONED_WORKSPACE = (
    _REPOSITORY_ROOT / "architecture" / "target-9f61bc6d6f8ae8cb7d196c8b327650d5"
)


def test_living_revision_resumes_only_after_fresh_review_on_accepted_lineage(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    repository = project.target.root
    add_doc(
        repository,
        id="epic_034",
        title="Living Epic",
        tier="epic",
        status="active",
        children=["feat_034_002", "feat_034_003"],
    )
    add_doc(
        repository,
        id="feat_034_002",
        title="Accepted sibling",
        tier="feature",
        status="completed",
        parent="epic_034",
    )
    add_doc(
        repository,
        id="feat_034_003",
        title="Changed active feature",
        tier="feature",
        status="active",
        parent="epic_034",
        children=["task_034_003_001"],
    )
    add_doc(
        repository,
        id="task_034_003_001",
        title="Running implementation",
        tier="task",
        status="active",
        parent="feat_034_003",
    )
    # Accept a sibling on its feature branch, then merge it into the Epic
    # integration lineage. The accepted pointer becomes current only there.
    store = ArchitectureReviewStore(project)
    sibling = replace(
        _unit(project, plan, design, model),
        owner_work_id="feat_034_002",
        affected_work_ids=("feat_034_002",),
        impact_reason="Accepted sibling architecture",
    )
    store.save(sibling)
    starting_head = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "-b", "feature/accepted-sibling")
    repository.joinpath("accepted-sibling.txt").write_text(
        "accepted sibling\n", encoding="utf-8"
    )
    _git(repository, "add", "accepted-sibling.txt")
    _git(repository, "commit", "-m", "implement accepted sibling")
    sibling_head = _git(repository, "rev-parse", "HEAD")
    accepted = store.accept(
        sibling.review_unit_id,
        accepted_code_head=sibling_head,
        accepted_documentation_head=starting_head,
        expected_generation=None,
    )
    _git(repository, "checkout", "main")
    _git(repository, "checkout", "-b", "epic/epic_034")
    _git(
        repository,
        "merge",
        "--no-ff",
        "feature/accepted-sibling",
        "-m",
        "merge accepted sibling",
    )
    epic_head = _git(repository, "rev-parse", "HEAD")
    assert store.resolve_current("epic:epic_034", lineage_revision=epic_head) == accepted

    root_comment_id = comment(
        "feat_034_003",
        "Plan",
        "Revise the active contract after the sibling merge.",
        author="human",
        root=repository,
    )
    escalation = escalate_comment_to_epic(
        root_comment_id,
        "The request changes work based on an accepted sibling.",
        feature_id="feat_034_003",
        affected_work_ids=["feat_034_003"],
        root=repository,
    )
    replayed_escalation = escalate_comment_to_epic(
        root_comment_id,
        "A retry must retain the original accountable handoff.",
        feature_id="feat_034_003",
        affected_work_ids=["feat_034_003"],
        root=repository,
    )
    assert replayed_escalation["id"] == escalation["id"]
    handoffs = read_change_request_handoffs(
        root=repository, source_feature_id="feat_034_003"
    )
    assert [row.purpose for row in handoffs] == [
        "initial_delivery",
        "epic_impact_triage",
    ]
    events, _ = read_events("epic_034", 0, root=repository)
    assert sum(
        event.payload.get("delivery_purpose") == "epic_impact_triage"
        for event in events
    ) == 1

    decision = record_impact_decision(
        str(escalation["id"]),
        "material",
        ["feature_plan"],
        "open_work_amendment",
        "Rebase the open work and obtain fresh review and approval.",
        epic_id="epic_034",
        root=repository,
    )
    assert decision["accepted_sibling_ids"] == ["feat_034_002"]
    replies = [
        row
        for row in read_comments("feat_034_003", root=repository)
        if row.parent == root_comment_id and row.author == "epic_manager"
    ]
    assert len(replies) == 1
    assert replies[0].state == "open"

    request_id = str(escalation["id"])
    create_scoped_change_hold(
        request_id,
        ["feat_034_003"],
        ["integration", "merge"],
        reason="Changed work requires a revised accepted-lineage review.",
        owner="epic_034",
        root=repository,
    )
    assert read_doc("task_034_003_001", root=repository).meta.status == "active"
    with pytest.raises(ArchitectureProposalError, match=request_id):
        require_lifecycle_review_gate(
            "task_034_003_001", "integration", root=repository
        )
    with pytest.raises(ScopedChangeHoldError, match="revised_approval_required"):
        release_revised_change_hold(
            request_id,
            decision_ref=str(decision["id"]),
            review_unit_id=sibling.review_unit_id,
            approval_ref="feature-approval:feat_034_003:revision-2",
            released_by="epic_manager",
            project=project,
        )

    changed = replace(
        _unit(project, plan, design, model),
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="Apply the accepted open-work amendment",
        decision_citations=(str(decision["id"]),),
    )
    staged = rebase_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=changed,
        lineage_revision=epic_head,
    )
    assert staged.unit is not None
    assert staged.accepted == accepted
    assert staged.unit.accepted_baseline == accepted.baseline
    reviewed = review_architecture_proposal(
        project,
        owner="feature-team",
        unit_id=staged.unit.review_unit_id,
        expected_tuple_digest=staged.unit.reviewed_tuple_digest,
        decision="reviewed",
        reviewed_at="2099-01-01T00:00:00+00:00",
        lineage_revision=epic_head,
    )
    assert reviewed.unit is not None
    approved = store.approve_review_unit(reviewed.unit.review_unit_id)
    released = release_revised_change_hold(
        request_id,
        decision_ref=str(decision["id"]),
        review_unit_id=approved.review_unit_id,
        approval_ref="feature-approval:feat_034_003:revision-2",
        released_by="epic_manager",
        project=project,
    )

    assert released.status == "released"
    assert holds_affecting(
        "task_034_003_001", "integration", root=repository
    ) == ()
    resumed = require_lifecycle_review_gate(
        "task_034_003_001", "integration", root=repository
    )
    assert resumed.boundary == "integration"
    assert store.resolve_current("epic:epic_034", lineage_revision=epic_head) == accepted
    assert read_doc("feat_034_002", root=repository).meta.status == "completed"


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


def test_changed_open_work_rebases_on_merged_sibling_and_requires_fresh_review(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    repository = project.target.root
    store = ArchitectureReviewStore(project)
    original = _unit(project, plan, design, model)
    sibling = replace(
        original,
        owner_work_id="feat_034_002",
        affected_work_ids=("feat_034_002",),
        impact_reason="Accepted sibling architecture",
    )
    store.save(sibling)
    store.save(original)

    repository.joinpath("accepted-sibling.txt").write_text(
        "accepted sibling\n", encoding="utf-8"
    )
    _git(repository, "add", "accepted-sibling.txt")
    _git(repository, "commit", "-m", "accept sibling")
    sibling_head = _git(repository, "rev-parse", "HEAD")
    accepted = store.accept(
        sibling.review_unit_id,
        integration_revision=sibling_head,
        expected_generation=None,
    )

    changed = replace(
        original,
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="Revise remaining work after the accepted sibling",
        decision_citations=("decision:living-revision",),
    )
    rebased = rebase_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=changed,
        lineage_revision=sibling_head,
    )

    assert rebased.status == "staged"
    assert rebased.accepted == accepted
    assert rebased.unit is not None
    assert rebased.unit.review_unit_id != original.review_unit_id
    assert rebased.unit.accepted_baseline == accepted.baseline
    assert rebased.unit.baseline_pointer_id == accepted.pointer_id
    assert rebased.unit.baseline_generation == accepted.generation
    assert rebased.unit.proposed_ancestor_context == ProposedAncestorContext(
        original.review_unit_id, accepted.pointer_id, accepted.generation
    )
    assert store.get(original.review_unit_id).status == "stale"  # type: ignore[union-attr]
    assert store.get(sibling.review_unit_id) == sibling
    assert store.resolve_current(
        "epic:epic_034", lineage_revision=sibling_head
    ) == accepted

    assert store.get_review(rebased.unit.review_unit_id) is None
    with pytest.raises(ArchitectureProposalError, match="human review"):
        store.approve_review_unit(rebased.unit.review_unit_id)


def test_changed_work_hold_releases_only_with_rebased_approved_tuple(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    repository = project.target.root
    store = ArchitectureReviewStore(project)
    original = _unit(project, plan, design, model)
    sibling = replace(
        original,
        owner_work_id="feat_034_002",
        affected_work_ids=("feat_034_002",),
        impact_reason="Accepted sibling architecture",
    )
    store.save(sibling)
    store.save(original)
    head = _git(repository, "rev-parse", "HEAD")
    store.accept(sibling.review_unit_id, integration_revision=head, expected_generation=None)
    create_scoped_change_hold(
        "handoff_001",
        ["feat_034_003"],
        ["merge"],
        reason="Open work changed after sibling acceptance",
        owner="epic_034",
        root=repository,
    )

    changed = replace(
        original,
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="Apply the accepted open-work amendment",
        decision_citations=("decision:impact_001",),
    )
    staged = rebase_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=changed,
        lineage_revision=head,
    )
    assert staged.unit is not None
    reviewed = review_architecture_proposal(
        project,
        owner="feature-team",
        unit_id=staged.unit.review_unit_id,
        expected_tuple_digest=staged.unit.reviewed_tuple_digest,
        decision="reviewed",
        reviewed_at="2099-01-01T00:00:00+00:00",
        lineage_revision=head,
    )
    assert reviewed.unit is not None
    approved = store.approve_review_unit(reviewed.unit.review_unit_id)

    decision = EpicImpactDecision(
        id="impact_001",
        handoff_id="handoff_001",
        root_comment_id="comment_001",
        source_feature_id="feat_034_003",
        affected_work_ids=("feat_034_003",),
        accepted_sibling_ids=("feat_034_002",),
        accepted_baseline=None,
        materiality="material",
        impact_reasons=("accepted_work",),
        disposition="open_work_amendment",
        decision_log_reference="decision:impact_001",
        originating_thread_reply_reference="reply_001",
        outcome="Revise the remaining work",
        decided_by="epic_manager",
        decided_at=datetime.now(timezone.utc),
    )
    monkeypatch.setattr(
        "cascade.epic.impact_decisions.read_epic_impact_decisions",
        lambda **_kwargs: [decision],
    )

    released = release_revised_change_hold(
        "handoff_001",
        decision_ref="impact_001",
        review_unit_id=approved.review_unit_id,
        approval_ref="feature-approval:feat_034_003:revision-2",
        released_by="epic_manager",
        project=project,
    )
    assert released.status == "released"
    assert released.release_evidence is not None
    assert released.release_evidence.reviewed_tuple_digest == approved.reviewed_tuple_digest


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


@pytest.mark.parametrize(
    "changed_path",
    (
        Path("plans/feat_034_003.md"),
        Path("DESIGN.md"),
        Path("architecture/target-PLACEHOLDER/workspace.contract.json"),
        Path("architecture/target-PLACEHOLDER/model.dsl"),
    ),
    ids=("plan", "design", "model-contract", "closure-source"),
)
def test_committed_review_artifact_mutation_persists_stale_without_losing_evidence(
    tmp_path: Path, changed_path: Path
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    unit = _unit(project, plan, design, model)
    store = ArchitectureReviewStore(project)
    store.save(unit)
    reviewed = store.record_review(
        unit.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    original_review = store.get_review(unit.review_unit_id)
    original_diff = store.get_diff(unit.review_unit_id)
    if "PLACEHOLDER" in changed_path.as_posix():
        changed_path = Path(
            changed_path.as_posix().replace(
                "target-PLACEHOLDER", project.editable_architecture_root.name
            )
        )
    artifact = project.target.root / changed_path
    artifact.write_text(artifact.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    _git(project.target.root, "add", changed_path.as_posix())
    _git(project.target.root, "commit", "-m", f"change reviewed {changed_path.name}")

    state = read_architecture_state(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        lineage="epic:epic_034",
    )

    assert reviewed.status == "reviewed"
    assert state.status == "stale"
    assert state.invalidation_reasons == ("artifact_changed",)
    assert state.review == original_review
    assert state.semantic_diff == original_diff

    _git(project.target.root, "revert", "--no-edit", "HEAD")
    restored = read_architecture_state(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        lineage="epic:epic_034",
    )
    assert restored.status == "stale"
    assert restored.review == original_review


@pytest.mark.parametrize("mutation", ("edit", "delete"))
def test_uncommitted_review_artifact_mutation_invalidates_active_checkout(
    tmp_path: Path, mutation: str
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    unit = _unit(project, plan, design, model)
    store = ArchitectureReviewStore(project)
    store.save(unit)
    store.record_review(
        unit.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    source = project.target.root / model.sources[0].reference.repository_path
    if mutation == "edit":
        source.write_text(source.read_text(encoding="utf-8") + "changed\n", encoding="utf-8")
    else:
        source.unlink()

    state = read_architecture_state(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        lineage="epic:epic_034",
    )

    assert state.status == "stale"
    assert state.invalidation_reasons == ("artifact_changed",)
    assert state.review is not None


def test_destination_change_invalidates_review_with_stable_reason(tmp_path: Path) -> None:
    target = _git_repository(tmp_path / "target")
    tracking = _git_repository(tmp_path / "tracking")
    original = ProjectContext.split(target, tracking, architecture_destination="target")
    resolve_design_ownership(original, ".")
    target.joinpath("DESIGN.md").write_text("# Design\n", encoding="utf-8")
    plan_path = target / "plan.md"
    plan_path.write_text("# Plan\n", encoding="utf-8")
    _git(target, "add", ".")
    _git(target, "commit", "-m", "review inputs")
    revision = _git(target, "rev-parse", "HEAD")
    design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(original, ".", owning_work="feat_034_003"),
        _digest(target.joinpath("DESIGN.md").read_bytes()),
    )
    plan = PinnedDocumentRef(
        original.target.repository_key, "target", Path("plan.md"), revision,
        _digest(plan_path.read_bytes()),
    )
    proposal = ArchitectureReviewUnit(
        owner_work_id="feat_034_003",
        authorized_owner="feature-team",
        target_repository_key=original.target_repository_key,
        code_directory=Path("."),
        design_owner_directory=Path("."),
        code_repository_key=original.target.repository_key,
        integration_lineage="epic:epic_034",
        documentation_repository_key=original.target_repository_key,
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
        requirement_citations=("REQ-ROOT-001",),
        decision_citations=("dec_001",),
        view_citations=(),
        affected_work_ids=("feat_034_003",),
        architecture_impact="no_diagram_change",
        impact_reason="No diagram change",
    )
    store = ArchitectureReviewStore(original)
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id, reviewer="feature-team", decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    changed = ProjectContext(original.target, original.tracking, architecture_destination="tracking")

    state = read_architecture_state(
        changed, owner="feature-team", work_id="feat_034_003", lineage="epic:epic_034"
    )

    assert state.status == "stale"
    assert state.invalidation_reasons == ("destination_changed",)
    assert state.review is not None


def test_new_accepted_lineage_generation_requires_rebase_and_fresh_review(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    revision = _git(project.target.root, "rev-parse", "HEAD")
    first = replace(
        _unit(project, plan, design, model),
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="Establish the initial accepted lineage",
    )
    store.save(first)
    accepted = store.accept(first.review_unit_id, integration_revision=revision, expected_generation=None)
    proposal = replace(
        first,
        accepted_baseline=accepted.baseline,
        baseline_pointer_id=accepted.pointer_id,
        baseline_generation=accepted.generation,
        proposed_ancestor_context=ProposedAncestorContext(
            first.review_unit_id, accepted.pointer_id, accepted.generation
        ),
        impact_reason="Reviewed follow-up proposal",
    )
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id, reviewer="feature-team", decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    competing = replace(
        proposal,
        owner_work_id="feat_034_004",
        authorized_owner="other-team",
        affected_work_ids=("feat_034_004",),
        impact_reason="Competing accepted proposal",
    )
    store.save(competing)
    store.accept(competing.review_unit_id, integration_revision=revision, expected_generation=1)

    refreshed = store.refresh(proposal.review_unit_id)

    assert refreshed.status == "stale"
    assert store.get_invalidation_reasons(proposal.review_unit_id) == ("stale_baseline",)
    review = store.get_review(proposal.review_unit_id)
    assert review and review.tuple_digest == proposal.reviewed_tuple_digest


def test_enabled_rollout_keeps_minimum_authoring_available(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    enable_review_gate(project, version=1, store=store)

    with pytest.raises(ArchitectureProposalError, match="review_required"):
        validate_review_gate(
            project, work_id="feat_034_003", boundary="dispatch", store=store
        )

    assert store.gate_policy_version("feat_034_003") == 1

    proposal = replace(
        _unit(project, plan, design, model),
        status="draft",
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="The reviewed workflow change does not alter diagrams",
    )
    staged = stage_architecture_proposal(
        project,
        owner="feature-team",
        work_id="feat_034_003",
        proposal=proposal,
        expected_generation=None,
        store=store,
    )
    reviewed = review_architecture_proposal(
        project,
        owner="feature-team",
        unit_id=proposal.review_unit_id,
        expected_tuple_digest=proposal.reviewed_tuple_digest,
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
        store=store,
    )

    approved = validate_review_gate(
        project, work_id="feat_034_003", boundary="approval", store=store
    )
    dispatched = validate_review_gate(
        project, work_id="feat_034_003", boundary="dispatch", store=store
    )

    assert staged.status == "staged"
    assert reviewed.status == "reviewed"
    assert approved.review_unit_id == proposal.review_unit_id
    assert dispatched.tuple_digest == proposal.reviewed_tuple_digest
    assert store.resolve_current("epic:epic_034") is None


def test_approval_pins_reviewed_tuple_for_all_lifecycle_boundaries(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    proposal = replace(
        _unit(project, plan, design, model),
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="The reviewed implementation does not alter diagrams",
        affected_work_ids=("feat_034_003", "task_034_003_004"),
    )
    store = ArchitectureReviewStore(project)
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    enable_review_gate(project, version=1, store=store)

    approved = validate_review_gate(
        project, work_id="feat_034_003", boundary="approval", store=store
    )
    dispatched = validate_review_gate(
        project, work_id="task_034_003_004", boundary="dispatch", store=store
    )
    merged = validate_review_gate(
        project, work_id="feat_034_003", boundary="merge", store=store
    )

    assert approved.review_unit_id == proposal.review_unit_id
    assert dispatched.review_unit_id == proposal.review_unit_id
    assert merged.tuple_digest == proposal.reviewed_tuple_digest
    assert store.get(proposal.review_unit_id).status == "approved"


def test_gate_revalidates_diagram_model_binding_before_approval(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    proposal = _unit(project, plan, design, model)
    store = ArchitectureReviewStore(project)
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    enable_review_gate(project, version=1, store=store)

    with pytest.raises(ArchitectureProposalError) as refusal:
        validate_review_gate(
            project, work_id="feat_034_003", boundary="approval", store=store
        )

    assert refusal.value.code == "model_invalid"
    assert store.get(proposal.review_unit_id).status == "reviewed"


@pytest.mark.parametrize("rollout_enabled", (False, True))
def test_legacy_policy_rejects_invalid_persisted_model_claim(
    tmp_path: Path, rollout_enabled: bool,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    store.save(_unit(project, plan, design, model))
    if rollout_enabled:
        enable_review_gate(project, version=1, store=store)

    with pytest.raises(ArchitectureProposalError) as refusal:
        validate_review_gate(
            project, work_id="feat_034_003", boundary="merge", store=store
        )

    assert refusal.value.code == "model_invalid"
    assert store.gate_policy_version("feat_034_003") == (
        0 if rollout_enabled else None
    )


def test_gate_reports_freshness_and_scoped_acceptance_holds(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    proposal = replace(
        _unit(project, plan, design, model),
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason="No diagram change",
        affected_work_ids=("feat_034_003", "task_034_003_004"),
    )
    store = ArchitectureReviewStore(project)
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    enable_review_gate(project, version=1, store=store)
    validate_review_gate(
        project, work_id="feat_034_003", boundary="approval", store=store
    )
    store.set_acceptance_hold(("task_034_003_004",), "promotion-1")

    with pytest.raises(ArchitectureProposalError, match="acceptance_pending"):
        validate_review_gate(
            project, work_id="task_034_003_004", boundary="dispatch", store=store
        )

    store.set_acceptance_hold(("task_034_003_004",), None)
    project.target.root.joinpath("DESIGN.md").write_text("# Changed design\n", encoding="utf-8")
    with pytest.raises(ArchitectureProposalError, match="artifact_changed"):
        validate_review_gate(
            project, work_id="feat_034_003", boundary="closeout", store=store
        )


def test_promotion_reservation_survives_restart_with_exact_revisions_and_hold(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    proposal = _approve_no_diagram(store, _unit(project, plan, design, model))
    expected = _git(project.target.root, "rev-parse", "HEAD")
    incoming = _incoming_commit(project.target.root, expected, "implementation")
    heads = PromotionHeads(expected, expected, incoming, incoming)

    journal = reserve_promotion(
        project,
        proposal.review_unit_id,
        heads,
        None,
        store=store,
    )

    restarted = ArchitectureReviewStore(project)
    assert restarted.get_promotion(journal.operation_id) == journal
    assert restarted.pending_promotion("epic:epic_034") == journal
    assert restarted.acceptance_hold("feat_034_003") == journal.operation_id
    assert restarted.resolve_current("epic:epic_034") is None
    with pytest.raises(ArchitectureProposalError, match="acceptance_pending"):
        restarted.accept(
            proposal.review_unit_id,
            integration_revision=expected,
            expected_generation=None,
        )
    payload = json.loads(restarted.path.read_text(encoding="utf-8"))
    persisted = payload["promotions"][journal.operation_id]
    assert persisted["approved_tuple_digest"] == proposal.reviewed_tuple_digest
    assert persisted["heads"]["incoming_implementation_commit"] == incoming
    assert persisted["code"] == {"state": "pending", "observed_resulting_head": None}
    assert persisted["documentation"] == {
        "state": "pending", "observed_resulting_head": None
    }


def test_competing_promotion_reservations_leave_one_visible_conflict(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    first = _approve_no_diagram(store, _unit(project, plan, design, model))
    second = _approve_no_diagram(
        store,
        replace(_unit(project, plan, design, model), impact_reason="Competing reviewed tuple"),
    )
    expected = _git(project.target.root, "rev-parse", "HEAD")
    incoming = _incoming_commit(project.target.root, expected, "implementation")
    heads = PromotionHeads(expected, expected, incoming, incoming)

    with ThreadPoolExecutor(max_workers=2) as executor:
        journals = tuple(executor.map(
            lambda unit_id: reserve_promotion(
                project, unit_id, heads, None, store=ArchitectureReviewStore(project)
            ),
            (first.review_unit_id, second.review_unit_id),
        ))

    assert {journal.outcome for journal in journals} == {"reserved", "conflict"}
    winner = next(journal for journal in journals if journal.outcome == "reserved")
    loser = next(journal for journal in journals if journal.outcome == "conflict")
    restarted = ArchitectureReviewStore(project)
    assert loser.error_code == "promotion_conflict"
    assert restarted.get_promotion(loser.operation_id) == loser
    assert restarted.pending_promotion("epic:epic_034") == winner
    assert restarted.acceptance_hold("feat_034_003") == winner.operation_id
    assert restarted.resolve_current("epic:epic_034") is None


def test_colocated_promotion_lands_both_revisions_before_advancing_lineage(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    proposal = _approve_no_diagram(store, _unit(project, plan, design, model))
    expected = _git(project.target.root, "rev-parse", "HEAD")
    implementation = _incoming_commit(project.target.root, expected, "implementation")
    documentation = _incoming_commit(project.target.root, expected, "documentation")
    journal = reserve_promotion(
        project,
        proposal.review_unit_id,
        PromotionHeads(expected, expected, implementation, documentation),
        None,
        store=store,
    )

    accepted = promote_or_resume(project, journal.operation_id, store=store)

    assert accepted.outcome == "accepted"
    assert accepted.code.state == accepted.documentation.state == "landed"
    assert accepted.code.observed_resulting_head == accepted.documentation.observed_resulting_head
    resulting_head = accepted.code.observed_resulting_head
    assert resulting_head is not None
    assert _git(project.target.root, "merge-base", "--is-ancestor", implementation,
                resulting_head) == ""
    assert _git(project.target.root, "merge-base", "--is-ancestor", documentation,
                resulting_head) == ""
    pointer = store.resolve_current("epic:epic_034")
    assert pointer and pointer.accepted_code_head == resulting_head
    assert store.acceptance_hold("feat_034_003") is None
    assert promote_or_resume(project, journal.operation_id, store=store) == accepted


def test_promotion_retry_recovers_merge_that_landed_before_journal_update(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    proposal = _approve_no_diagram(store, _unit(project, plan, design, model))
    expected = _git(project.target.root, "rev-parse", "HEAD")
    implementation = _incoming_commit(project.target.root, expected, "implementation")
    documentation = _incoming_commit(project.target.root, expected, "documentation")
    journal = reserve_promotion(
        project,
        proposal.review_unit_id,
        PromotionHeads(expected, expected, implementation, documentation),
        None,
        store=store,
    )
    persist = store._record_promotion_sides

    def crash_before_journal_update(*args: object, **kwargs: object) -> object:
        raise RuntimeError("simulated crash after Git")

    monkeypatch.setattr(store, "_record_promotion_sides", crash_before_journal_update)
    with pytest.raises(RuntimeError, match="simulated crash"):
        promote_or_resume(project, journal.operation_id, store=store)
    landed_head = _git(project.target.root, "rev-parse", "HEAD")
    assert store.get_promotion(journal.operation_id).outcome == "reserved"

    monkeypatch.setattr(store, "_record_promotion_sides", persist)
    recovered = promote_or_resume(project, journal.operation_id, store=store)

    assert recovered.outcome == "accepted"
    assert recovered.code.observed_resulting_head == landed_head
    assert _git(project.target.root, "rev-parse", "HEAD") == landed_head


@pytest.mark.parametrize(
    "failure",
    ("before_documentation", "after_code_merge", "after_documentation_merge"),
)
def test_split_promotion_recovers_failure_or_crash_without_duplicate_merges(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str,
) -> None:
    colocated, plan, design, model = _review_repository(tmp_path)
    tracking_root = _git_repository(tmp_path / "tracking")
    tracking_root.joinpath("README.md").write_text("# Tracking\n", encoding="utf-8")
    _git(tracking_root, "add", "README.md")
    _git(tracking_root, "commit", "-m", "tracking baseline")
    project = ProjectContext.split(
        colocated.target.root, tracking_root, architecture_destination="tracking"
    )
    resolve_design_ownership(project, ".")
    project.design_path().parent.mkdir(parents=True, exist_ok=True)
    project.design_path().write_text("# Reviewed design\n", encoding="utf-8")
    _git(tracking_root, "add", ".")
    _git(tracking_root, "commit", "-m", "reviewed architecture")
    split_design = PinnedArchitectureArtifact(
        create_architecture_artifact_ref(project, ".", owning_work="feat_034_003"),
        _digest(project.design_path().read_bytes()),
    )
    store = ArchitectureReviewStore(project)
    proposal = replace(
        _unit(colocated, plan, design, model),
        documentation_repository_key=project.architecture_repository.repository_key,
        documentation_repository_role="tracking",
        design=split_design,
        proposed_model=None,
        architecture_impact="no_diagram_change",
        view_citations=(),
    )
    proposal = _approve_no_diagram(store, proposal)
    expected_code = _git(project.target.root, "rev-parse", "HEAD")
    expected_docs = _git(tracking_root, "rev-parse", "HEAD")
    implementation = _incoming_commit(project.target.root, expected_code, "implementation")
    documentation = _incoming_commit(tracking_root, expected_docs, "documentation")
    journal = reserve_promotion(
        project,
        proposal.review_unit_id,
        PromotionHeads(expected_code, expected_docs, implementation, documentation),
        None,
        store=store,
    )
    land = store._land_promotion_side
    record = store._record_promotion_sides
    crashed = False

    def crash_before_documentation(
        current: object, unit: object, side: str, repository: Path,
        expected_head: str, incoming_commit: str,
    ) -> object:
        if failure == "before_documentation" and side == "documentation":
            raise RuntimeError("documentation repository unavailable")
        return land(current, unit, side, repository, expected_head, incoming_commit)

    def crash_after_git(
        operation_id: str,
        *,
        code_head: str | None = None,
        documentation_head: str | None = None,
    ) -> object:
        nonlocal crashed
        should_crash = (
            failure == "after_code_merge" and code_head is not None
        ) or (
            failure == "after_documentation_merge" and documentation_head is not None
        )
        if should_crash and not crashed:
            crashed = True
            raise RuntimeError(f"simulated crash {failure}")
        return record(
            operation_id,
            code_head=code_head,
            documentation_head=documentation_head,
        )

    monkeypatch.setattr(store, "_land_promotion_side", crash_before_documentation)
    monkeypatch.setattr(store, "_record_promotion_sides", crash_after_git)
    with pytest.raises(RuntimeError):
        promote_or_resume(project, journal.operation_id, store=store)
    pending = store.get_promotion(journal.operation_id)
    assert pending and pending.outcome in {"reserved", "acceptance_pending"}
    code_head = _git(project.target.root, "rev-parse", "HEAD")
    documentation_head = _git(tracking_root, "rev-parse", "HEAD")

    monkeypatch.setattr(store, "_land_promotion_side", land)
    monkeypatch.setattr(store, "_record_promotion_sides", record)
    accepted = promote_or_resume(project, journal.operation_id, store=store)

    assert accepted.outcome == "accepted"
    assert _git(project.target.root, "rev-parse", "HEAD") == code_head
    if failure == "after_documentation_merge":
        assert _git(tracking_root, "rev-parse", "HEAD") == documentation_head
    assert accepted.code.observed_resulting_head == code_head
    assert _git(
        project.target.root,
        "merge-base", "--is-ancestor", implementation, code_head,
    ) == ""
    accepted_documentation_head = accepted.documentation.observed_resulting_head
    assert accepted_documentation_head is not None
    assert _git(
        tracking_root,
        "merge-base", "--is-ancestor", documentation, accepted_documentation_head,
    ) == ""
    assert accepted.code.state == accepted.documentation.state == "landed"


def test_promotion_marks_changed_destination_head_for_rereview(tmp_path: Path) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    store = ArchitectureReviewStore(project)
    proposal = _approve_no_diagram(store, _unit(project, plan, design, model))
    expected = _git(project.target.root, "rev-parse", "HEAD")
    incoming = _incoming_commit(project.target.root, expected, "implementation")
    journal = reserve_promotion(
        project,
        proposal.review_unit_id,
        PromotionHeads(expected, expected, incoming, incoming),
        None,
        store=store,
    )
    project.target.root.joinpath("competing.txt").write_text("changed\n", encoding="utf-8")
    _git(project.target.root, "add", "competing.txt")
    _git(project.target.root, "commit", "-m", "competing destination change")

    conflicted = promote_or_resume(project, journal.operation_id, store=store)

    assert conflicted.outcome == "conflict"
    assert conflicted.error_code == "head_conflict"
    assert store.resolve_current("epic:epic_034") is None
    assert store.acceptance_hold("feat_034_003") == journal.operation_id


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
        project, ".", "workspace.contract.json", owning_work="task_034_007_002"
    )
    sources = tuple(
        create_architecture_model_ref(project, ".", name, owning_work="task_034_007_002")
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


def _approve_no_diagram(
    store: ArchitectureReviewStore, proposal: ArchitectureReviewUnit
) -> ArchitectureReviewUnit:
    proposal = replace(
        proposal,
        proposed_model=None,
        architecture_impact="no_diagram_change",
        impact_reason=proposal.impact_reason,
    )
    store.save(proposal)
    store.record_review(
        proposal.review_unit_id,
        reviewer="feature-team",
        decision="reviewed",
        reviewed_at="2026-11-09T12:00:00+00:00",
    )
    return store.approve_review_unit(proposal.review_unit_id)


def _incoming_commit(repository: Path, destination_head: str, name: str) -> str:
    _git(repository, "checkout", "-b", f"incoming-{name}")
    repository.joinpath(f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
    _git(repository, "add", f"{name}.txt")
    _git(repository, "commit", "-m", f"add {name}")
    incoming = _git(repository, "rev-parse", "HEAD")
    _git(repository, "checkout", "--detach", destination_head)
    return incoming


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
