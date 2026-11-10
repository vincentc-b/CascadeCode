"""Durable scoped holds through shared lifecycle entry points."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.boss.merge import merge_feature_branch
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.mint import mint_task
from cascade.lifecycle_review_gate import require_lifecycle_review_gate
from cascade.scoped_change_holds import (
    ScopedChangeHoldError,
    create_scoped_change_hold,
    holds_affecting,
    read_scoped_change_holds,
    release_scoped_change_hold,
)
from cascade.workspace.architecture_review import ArchitectureProposalError
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001", "feat_002"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Changed feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    pin_parent("feat_001", "epic_001", root=root)
    add_doc(
        root,
        id="task_001",
        title="Running task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Accepted sibling",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_002", "epic_001", root=root)
    return root


def test_hold_survives_restart_and_blocks_only_affected_boundaries(
    board: Path,
) -> None:
    hold = create_scoped_change_hold(
        "crh_material_001",
        ["feat_001"],
        ["minting", "dispatch", "task_integration", "feature_merge", "closure"],
        reason="The feature contract changed after a sibling merged.",
        owner="epic_001",
        root=board,
    )
    assert hold.affected_work_ids == ("feat_001", "task_001")
    assert hold.boundaries == (
        "mint",
        "dispatch",
        "integration",
        "merge",
        "closeout",
    )

    # Re-read from disk as a new process would. Existing running work remains
    # active; only its safe integration boundary is held.
    [restarted] = read_scoped_change_holds(root=board, active_only=True)
    assert restarted.request_id == hold.request_id
    assert read_doc("task_001", root=board).meta.status == "active"
    with pytest.raises(ArchitectureProposalError) as exc_info:
        require_lifecycle_review_gate("task_001", "integration", root=board)
    message = str(exc_info.value)
    assert "scoped_change_hold" in message
    assert "request=crh_material_001" in message
    assert "owner=epic_001" in message
    assert "release by recording" in message

    with pytest.raises(FeatureToolDenied, match="crh_material_001"):
        mint_task("Held task", feature_id="feat_001", root=board)
    merge = merge_feature_branch("feat_001", root=board)
    assert not merge.ok
    assert merge.reason is not None and "request=crh_material_001" in merge.reason

    # The accepted sibling is outside the affected subtree.
    assert holds_affecting("feat_002", "feature_merge", root=board) == ()
    require_lifecycle_review_gate("feat_002", "merge", root=board)


def test_new_descendants_are_held_and_exact_release_resumes_scope(board: Path) -> None:
    create_scoped_change_hold(
        "crh_material_002",
        ["feat_001"],
        ["dispatch", "integration", "merge"],
        reason="Awaiting revised contract review.",
        owner="epic_001",
        root=board,
    )
    add_doc(
        board,
        id="task_002",
        title="Later task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    feature = read_doc("feat_001", root=board)
    feature.meta.children.append("task_002")
    write_doc(feature, root=board)
    replay = create_scoped_change_hold(
        "crh_material_002",
        ["feat_001"],
        ["feature_merge", "dispatch", "task_integration"],
        reason="Awaiting revised contract review.",
        owner="epic_001",
        root=board,
    )
    assert replay.affected_work_ids == ("feat_001", "task_001")
    assert [
        row.request_id for row in holds_affecting("task_002", "dispatch", root=board)
    ] == ["crh_material_002"]

    with pytest.raises(ScopedChangeHoldError, match="revised_approval_required"):
        release_scoped_change_hold(
            "crh_material_002",
            decision_ref="dec_002",
            released_by="epic_manager",
            root=board,
        )

    released = release_scoped_change_hold(
        "crh_material_002",
        decision_ref="dec_002",
        review_unit_id="architecture-review-revised",
        reviewed_tuple_digest="a" * 64,
        approval_ref="feature-approval:feat_001:revision-2",
        released_by="epic_manager",
        root=board,
    )
    assert released.status == "released"
    assert released.release_evidence is not None
    assert released.release_evidence.decision_ref == "dec_002"
    assert holds_affecting("task_002", "dispatch", root=board) == ()
    require_lifecycle_review_gate("task_002", "dispatch", root=board)

    # Replay is idempotent for the same tuple and rejects substituted evidence.
    assert (
        release_scoped_change_hold(
            "crh_material_002",
            decision_ref="dec_002",
            review_unit_id="architecture-review-revised",
            reviewed_tuple_digest="a" * 64,
            approval_ref="feature-approval:feat_001:revision-2",
            released_by="epic_manager",
            root=board,
        )
        == released
    )
    with pytest.raises(ScopedChangeHoldError, match="release_conflict"):
        release_scoped_change_hold(
            "crh_material_002",
            decision_ref="dec_other",
            review_unit_id="architecture-review-revised",
            reviewed_tuple_digest="a" * 64,
            approval_ref="feature-approval:feat_001:revision-2",
            released_by="epic_manager",
            root=board,
        )


def test_approval_boundary_stays_open_to_create_release_evidence(board: Path) -> None:
    create_scoped_change_hold(
        "crh_material_003",
        ["feat_001"],
        ["dispatch", "merge"],
        reason="Fresh approval required.",
        owner="epic_001",
        root=board,
    )
    require_lifecycle_review_gate("feat_001", "approval", root=board)
