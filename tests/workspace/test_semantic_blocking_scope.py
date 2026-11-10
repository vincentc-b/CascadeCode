"""Scoped semantic blockers across review and lifecycle boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.comments import comment, resolve_comment
from cascade.lifecycle_review_gate import require_lifecycle_review_gate
from cascade.workspace import (
    ArchitectureProposalError,
    ArchitectureReviewStore,
    BlockingScope,
    ProjectContext,
    affected_blocking_threads,
    enable_review_gate,
    validate_review_gate,
)
from tests.support import add_doc, make_repo


@pytest.fixture
def board_repo(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_034",
        title="Architecture",
        tier="epic",
        status="active",
        children=["feat_034_001", "feat_034_002"],
    )
    add_doc(
        root,
        id="feat_034_001",
        title="Review owner",
        tier="feature",
        status="active",
        parent="epic_034",
        children=["task_034_001_001"],
    )
    add_doc(
        root,
        id="task_034_001_001",
        title="Affected task",
        tier="task",
        status="active",
        parent="feat_034_001",
    )
    add_doc(
        root,
        id="feat_034_002",
        title="Sibling feature",
        tier="feature",
        status="active",
        parent="epic_034",
        children=["task_034_002_001", "task_034_002_002"],
    )
    add_doc(
        root,
        id="task_034_002_001",
        title="Dependent task",
        tier="task",
        status="active",
        parent="feat_034_002",
        depends_on=["task_034_001_001"],
    )
    add_doc(
        root,
        id="task_034_002_002",
        title="Unrelated sibling task",
        tier="task",
        status="active",
        parent="feat_034_002",
    )
    add_doc(
        root,
        id="epic_099",
        title="Unrelated epic",
        tier="epic",
        status="active",
        children=["feat_099_001"],
    )
    add_doc(
        root,
        id="feat_099_001",
        title="Unrelated feature",
        tier="feature",
        status="active",
        parent="epic_099",
    )
    return root


def test_explicit_comment_scope_holds_dependents_but_not_unrelated_work(
    board_repo: Path,
) -> None:
    thread_id = comment(
        "feat_034_001",
        "semantic-review",
        "Address the pinned element",
        blocking=True,
        blocks=["task_034_001_001"],
        semantic_anchor=_outdated_anchor(),
        author="human",
        root=board_repo,
    )

    direct = affected_blocking_threads(
        "task_034_001_001", "dispatch", root=board_repo
    )
    dependent = affected_blocking_threads(
        "task_034_002_001", "integration", root=board_repo
    )

    assert direct[0].affected_work_ids == dependent[0].affected_work_ids
    assert direct[0].thread_id == dependent[0].thread_id
    assert direct[0].thread_id == thread_id
    assert direct[0].affected_work_ids == (
        "task_034_001_001",
        "task_034_002_001",
    )
    assert direct[0].reason == "comment_affected_ids"
    assert direct[0].fallback is False
    assert affected_blocking_threads(
        "task_034_002_002", "merge", root=board_repo
    ) == ()
    assert affected_blocking_threads(
        "feat_099_001", "closeout", root=board_repo
    ) == ()
    with pytest.raises(ArchitectureProposalError, match=thread_id):
        require_lifecycle_review_gate(
            "task_034_002_001", "integration", root=board_repo
        )

    resolve_comment(
        "feat_034_001", thread_id, author="human", root=board_repo
    )
    assert affected_blocking_threads(
        "task_034_001_001", "dispatch", root=board_repo
    ) == ()


def test_ambiguous_outdated_anchor_visibly_falls_back_only_to_owner_subtree(
    board_repo: Path,
) -> None:
    comment(
        "feat_034_001",
        "semantic-review",
        "The old target is still unresolved",
        blocking=True,
        semantic_anchor=_outdated_anchor(),
        author="human",
        root=board_repo,
    )

    held = affected_blocking_threads(
        "task_034_001_001", "approval", root=board_repo
    )

    assert held[0].affected_work_ids == (
        "feat_034_001",
        "task_034_001_001",
    )
    assert held[0].reason == "owner_subtree_fallback"
    assert held[0].fallback is True
    assert affected_blocking_threads(
        "task_034_002_001", "dispatch", root=board_repo
    ) == ()


@pytest.mark.parametrize(
    "boundary", ("approval", "dispatch", "integration", "merge", "closeout")
)
def test_every_review_boundary_reports_semantic_scope_before_state_change(
    tmp_path: Path, boundary: str
) -> None:
    root = make_repo(tmp_path, git=False)
    project = ProjectContext.colocated(root)
    store = ArchitectureReviewStore(project)
    enable_review_gate(project, version=1, store=store)
    scope = BlockingScope(
        "cmt_7",
        "feat_034_001",
        ("task_034_001_001",),
        "review_unit_affected_ids",
        boundary,  # type: ignore[arg-type]
        False,
    )

    with pytest.raises(ArchitectureProposalError) as refusal:
        validate_review_gate(
            project,
            work_id="task_034_001_001",
            boundary=boundary,  # type: ignore[arg-type]
            store=store,
            semantic_blockers=(scope,),
        )

    assert refusal.value.code == "review_required"
    assert "cmt_7" in str(refusal.value)
    assert "affected=task_034_001_001" in str(refusal.value)
    assert "fallback=false" in str(refusal.value)
    assert store.gate_policy_version("task_034_001_001") is None


def _outdated_anchor() -> dict[str, object]:
    return {
        "version": 1,
        "kind": "element",
        "target_key": "element.removed",
        "view_key": None,
        "level": None,
        "source_side": "proposed",
        "repository_key": "docs",
        "revision": "a" * 40,
        "review_unit_id": "architecture-review-old",
        "reviewed_tuple_digest": "old",
        "original_source_reference": "old.svg",
        "original_diff_link": "git:old..new",
    }
