"""Tier-pinned architecture context and bounded replay evidence."""

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.workspace.architecture_context import (
    ArchitectureContextDenied,
    build_tier_planning_context,
    read_historical_replay,
)
from cascade.workspace.architecture_review import ArchitectureReviewStore
from tests.support import add_doc
from tests.workspace.test_architecture_review import _review_repository, _unit


def test_feature_context_contains_only_owned_pinned_design_and_model_sources(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    add_doc(
        project.tracking.root,
        id="epic_034",
        title="Architecture epic",
        tier="epic",
        status="active",
    )
    add_doc(
        project.tracking.root,
        id="feat_034_003",
        title="Architecture owner",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    unit = _unit(project, plan, design, model)
    ArchitectureReviewStore(project).save(unit)

    context = build_tier_planning_context(project, "feat_034_003")

    assert context.plan_revision == read_doc(
        "feat_034_003", root=project.tracking.root
    ).sha
    assert context.ancestor_revisions == ()
    assert [artifact.kind for artifact in context.artifacts] == [
        "design",
        "model_contract",
        "model_fragment",
    ]
    assert {artifact.reference.revision for artifact in context.artifacts} == {
        design.reference.revision
    }
    assert {artifact.owner_work_id for artifact in context.artifacts} == {
        "feat_034_003"
    }
    assert "Reviewed design" in context.artifacts[0].content
    assert "workspace" in context.artifacts[1].content


def test_context_does_not_promote_cross_owner_sources_from_review_closure(
    tmp_path: Path,
) -> None:
    project, plan, design, model = _review_repository(tmp_path)
    add_doc(
        project.tracking.root,
        id="epic_034",
        title="Architecture epic",
        tier="epic",
        status="active",
    )
    add_doc(
        project.tracking.root,
        id="feat_034_003",
        title="Architecture owner",
        tier="feature",
        status="active",
        parent="epic_034",
    )
    foreign_source = replace(
        model.sources[0],
        reference=replace(model.sources[0].reference, owning_work="feat_foreign"),
    )
    unit = replace(
        _unit(project, plan, design, replace(model, sources=(foreign_source,))),
        proposed_model=replace(model, sources=(foreign_source,)),
    )
    ArchitectureReviewStore(project).save(unit)

    context = build_tier_planning_context(project, "feat_034_003")

    assert [artifact.kind for artifact in context.artifacts] == [
        "design",
        "model_contract",
    ]


def test_historical_replay_is_related_completed_and_explicitly_scoped(
    tmp_path: Path,
) -> None:
    project, _, _, _ = _review_repository(tmp_path)
    root = project.tracking.root
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Owner", tier="feature", status="active",
        parent="epic_001",
    )
    add_doc(
        root, id="feat_002", title="Other", tier="feature", status="active",
        parent="epic_001",
    )
    completed = add_doc(
        root,
        id="task_001",
        title="Completed child",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Unrelated",
        tier="task",
        status="completed",
        parent="feat_002",
    )
    add_doc(
        root,
        id="task_003",
        title="Cancelled child",
        tier="task",
        status="cancelled",
        parent="feat_001",
    )

    evidence = read_historical_replay(
        project,
        "feat_001",
        "task_001",
        ("work_record", "git", "review"),
    )

    assert evidence.work_record == {
        "id": "task_001",
        "tier": "task",
        "title": "Completed child",
        "parent": "feat_001",
        "revision": completed.sha,
        "body": completed.body,
    }
    assert evidence.git == {
        "plan_revision": completed.sha,
        "integration_branch": None,
        "architecture_promotions": [],
    }
    assert evidence.reviews == ()

    with pytest.raises(ArchitectureContextDenied, match="outside the owner scope"):
        read_historical_replay(
            project, "feat_001", "task_002", ("work_record",)
        )
    with pytest.raises(ArchitectureContextDenied, match="non-cancelled"):
        read_historical_replay(
            project, "feat_001", "task_003", ("work_record",)
        )
    with pytest.raises(ArchitectureContextDenied, match="evidence scope"):
        read_historical_replay(project, "feat_001", "task_001", ("repository",))


def test_replay_omits_unrequested_record_and_repository_content(tmp_path: Path) -> None:
    project, _, _, _ = _review_repository(tmp_path)
    root = project.tracking.root
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root, id="feat_001", title="Owner", tier="feature", status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Completed child",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    root.joinpath("secret.txt").write_text("must not be replayed\n", encoding="utf-8")

    evidence = read_historical_replay(
        project, "feat_001", "task_001", ("git",)
    ).to_dict()

    assert evidence["work_record"] is None
    assert evidence["reviews"] == []
    assert "secret" not in repr(evidence)

