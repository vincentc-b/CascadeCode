"""Compatibility baseline for authoritative dependency status (feat_038_001)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.board.context import resolve_tracking_root, set_project_context
from cascade.board.store import read_doc
from cascade.dependency_evaluation import evaluate_dependencies
from cascade.stacked_dispatch import feature_dependency_ready
from cascade.watchdog.dispatch import activate_epic, dispatch_feature, dispatch_task
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from cascade.workspace.types import ProjectContext
from tests.support import (
    SyntheticDependencyLifecycle,
    add_doc,
    approve_board_feature,
    make_repo,
)


def _open_feature_review(root: Path, feature_id: str) -> None:
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                feature_id: {
                    "url": f"https://github.example/o/r/pull/{feature_id}",
                    "source_branch": f"feat/{feature_id}",
                    "target_branch": "epic/epic_001",
                    "forge": "github",
                    "closed": False,
                }
            }
        )
        + "\n",
        encoding="utf-8",
    )


def test_planning_documents_and_dependencies_are_owned_by_tracking_root(
    tmp_path: Path,
) -> None:
    target = make_repo(tmp_path / "target", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    set_project_context(ProjectContext.split(target, tracking))

    add_doc(target, id="epic_001", title="Epic", tier="epic")
    add_doc(
        target,
        id="feat_001",
        title="Dependency",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        target,
        id="feat_002",
        title="Dependent",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )

    canonical_root = resolve_tracking_root(target)
    board = merged_board(canonical_root)
    dependent = board.by_id["feat_002"]

    assert canonical_root == tracking.resolve()
    assert read_doc("feat_001", root=target).meta.path.is_relative_to(tracking)
    assert not list((target / "docs").rglob("*.md"))
    assert feature_dependency_ready(dependent, board, root=canonical_root)
    assert evaluate_dependencies(dependent, root=target).satisfied


def test_synthetic_canonical_completion_precedes_stale_registered_copy(
    synthetic_dependency_lifecycle: SyntheticDependencyLifecycle,
) -> None:
    scenario = synthetic_dependency_lifecycle
    root = scenario.root

    board = merged_board(root)
    visible = board.by_id[scenario.dependency_id]

    assert visible.status == "completed"
    assert visible.path.parent.name == "3_completed"
    assert visible.path.is_relative_to(root / "docs")
    assert evaluate_dependencies(board.by_id[scenario.owner_id], root=root).satisfied


def test_dependency_evaluation_distinguishes_lifecycle_and_availability(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Complete",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Open",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_003",
        title="Cancelled",
        tier="feature",
        status="cancelled",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_004",
        title="Mismatch",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_005",
        title="Dependent",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001", "feat_002", "feat_003", "feat_004"],
    )
    board = merged_board(root)
    board.by_id["feat_005"].depends_on.append("feat_999")
    board.by_id["feat_004"].path = (
        root / "docs" / "features" / "2_active" / "feat_004_mismatch.md"
    )

    result = evaluate_dependencies(board.by_id["feat_005"], root=root, board=board)

    assert result.outcome == "dependency_status_unavailable"
    assert [row.work_id for row in result.dependencies] == [
        "feat_001",
        "feat_002",
        "feat_003",
        "feat_004",
        "feat_999",
    ]
    assert [row.reason for row in result.dependencies] == [
        None,
        "dependency_incomplete",
        "dependency_cancelled",
        "dependency_status_column_mismatch",
        "dependency_not_found",
    ]


def test_dependency_evaluation_empty_list_and_source_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    empty = add_doc(root, id="epic_001", title="Empty", tier="epic").meta
    dependent = add_doc(
        root,
        id="epic_002",
        title="Dependent",
        tier="epic",
        depends_on=["epic_001"],
    ).meta

    def fail_board(_root: Path):
        raise OSError("private source detail")

    monkeypatch.setattr("cascade.dependency_evaluation.merged_board", fail_board)

    assert evaluate_dependencies(empty, root=root).satisfied
    result = evaluate_dependencies(dependent, root=root)
    assert result.outcome == "dependency_status_unavailable"
    assert [(row.work_id, row.reason) for row in result.dependencies] == [
        ("epic_001", "dependency_source_unavailable")
    ]


def test_request_snapshot_stays_fixed_then_observes_board_invalidation(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    initial = merged_board(root)

    with merged_board_snapshot(root, initial):
        add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
        assert merged_board(root) is initial
        assert "feat_001" not in merged_board(root).by_id

    refreshed = merged_board(root)
    assert refreshed is not initial
    assert "feat_001" in refreshed.by_id


@pytest.mark.parametrize(
    ("stacked_enabled", "expected_ok", "expected_reason"),
    [(False, False, "feature_awaiting_merge"), (True, True, None)],
)
def test_completed_dependency_does_not_replace_stacked_dispatch_gate(
    tmp_path: Path,
    stacked_enabled: bool,
    expected_ok: bool,
    expected_reason: str | None,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    assert activate_epic("epic_001", "human", root=root).ok
    write_stacked_pr_enabled("epic_001", stacked_enabled, root=root)
    add_doc(
        root,
        id="feat_001",
        title="Dependency",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Dependent",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    approve_board_feature(root, "feat_002")
    _open_feature_review(root, "feat_001")

    board = merged_board(root)
    assert feature_dependency_ready(board.by_id["feat_002"], board, root=root)

    result = dispatch_feature("feat_002", "human", root=root)
    assert result.ok is expected_ok
    assert result.reason == expected_reason


def test_completed_feature_dependency_does_not_replace_task_review_gate(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Parent", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Reviewed dependency",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Dependent task",
        tier="task",
        parent="feat_001",
        depends_on=["feat_002"],
    )
    _open_feature_review(root, "feat_002")

    dependency = merged_board(root).by_id["feat_002"]
    assert dependency.status == "completed"
    assert dependency.path.parent.name == "3_completed"

    result = dispatch_task("task_001", "human", root=root)
    assert result.ok is False
    assert result.reason == "feature_awaiting_merge"
