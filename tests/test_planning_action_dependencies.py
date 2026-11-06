"""Fresh dependency evidence at planning action boundaries."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.approvals import approve_epic_plan, approve_feature
from cascade.board.store import move_doc, read_doc
from cascade.epic.mint import mint_feature
from cascade.epic.plan_readiness import compute_epic_plan_readiness
from cascade.epic.planning_signoffs import (
    canonical_plan_revision,
    read_plan_sign_offs,
    sign_off_epic_plan,
)
from cascade.planning_action_dependencies import (
    DependencyActionRefused,
    evaluate_action_dependencies,
)
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from tests.support import add_doc, make_repo, sign_off_both_planning_roles


def test_action_refresh_ignores_cached_and_request_scoped_board(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    move_doc("epic_001", "completed", root=root)

    with merged_board_snapshot(root, stale):
        assert merged_board(root) is stale
        assert evaluate_action_dependencies("epic_002", root=root).outcome == "satisfied"


def test_sign_off_refuses_unmet_dependency_without_writing_sidecar(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    revision = canonical_plan_revision("epic_002", root=root)
    assert revision is not None

    with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
        sign_off_epic_plan(
            "epic_002",
            "epic_manager",
            revision,
            root=root,
            actor="epic_manager",
        )

    assert read_plan_sign_offs("epic_002", root=root) == ()
    readiness = compute_epic_plan_readiness("epic_002", root=root)
    assert readiness is not None
    assert readiness.approve_disabled_reason == "dependency_unmet"


def test_feature_approval_fails_closed_after_dependency_regresses(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
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
        title="Owner",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    stale = merged_board(root)
    move_doc("feat_001", "backlog", root=root)

    with merged_board_snapshot(root, stale):
        with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
            approve_feature("feat_002", root=root)

    assert read_doc("feat_002", root=root).meta.approved_at is None


def test_source_refresh_failure_refuses_without_feature_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")

    def fail_refresh(root: Path) -> object:
        raise OSError("source disappeared")

    monkeypatch.setattr(
        "cascade.planning_action_dependencies.refresh_merged_board", fail_refresh
    )
    with pytest.raises(
        DependencyActionRefused, match="dependency_status_unavailable"
    ):
        approve_feature("feat_001", root=root)

    assert read_doc("feat_001", root=root).meta.approved_at is None


def test_epic_approval_checks_only_epic_dependencies_before_bulk_write(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_001",
        title="Prerequisite",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_002",
        title="Epic",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    add_doc(root, id="feat_002_001", title="First", tier="feature", parent="epic_002")
    add_doc(
        root,
        id="feat_002_002",
        title="Second",
        tier="feature",
        parent="epic_002",
        depends_on=["feat_002_001"],
    )
    sign_off_both_planning_roles("epic_002", root=root)

    result = approve_epic_plan("epic_002", root=root)

    assert result["features"] == ["feat_002_001", "feat_002_002"]
    assert read_doc("feat_002_001", root=root).meta.approved_at is not None
    assert read_doc("feat_002_002", root=root).meta.approved_at is not None


def test_epic_dependency_regression_refuses_before_any_bulk_approval(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(
        root,
        id="epic_001",
        title="Prerequisite",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_002",
        title="Epic",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    add_doc(root, id="feat_002_001", title="First", tier="feature", parent="epic_002")
    add_doc(root, id="feat_002_002", title="Second", tier="feature", parent="epic_002")
    sign_off_both_planning_roles("epic_002", root=root)
    move_doc("epic_001", "backlog", root=root)

    with pytest.raises(DependencyActionRefused, match="dependency_unmet"):
        approve_epic_plan("epic_002", root=root)

    assert read_doc("feat_002_001", root=root).meta.approved_at is None
    assert read_doc("feat_002_002", root=root).meta.approved_at is None
    assert read_doc("epic_002", root=root).meta.plan_approved_at is None


def test_mint_allows_incomplete_child_predecessor_when_owner_is_ready(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")

    minted = mint_feature(
        "Second",
        depends_on=["feat_001"],
        epic_id="epic_001",
        root=root,
    )

    assert read_doc(minted, root=root).meta.depends_on == ["feat_001"]
