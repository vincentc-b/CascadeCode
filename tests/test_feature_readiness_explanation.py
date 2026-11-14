"""Canonical feature activation reasons and prerequisite evidence."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.store import write_doc
from cascade.feature.readiness import compute_feature_readiness
from cascade.stacked_dispatch import (
    FeatureDispatchSelection,
    persist_feature_dispatch_selection,
)
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo


def _reason_view(readiness) -> list[tuple[str, tuple[str, ...]]]:
    assert readiness is not None
    assert readiness.explanation is not None
    return [
        (reason.code, reason.affected_work_ids)
        for reason in readiness.explanation.reasons
    ]


def _active_epic(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")


def _approved_target(root: Path) -> None:
    target = add_doc(
        root,
        id="feat_003",
        title="Target",
        tier="feature",
        parent="epic_001",
    )
    target.meta.approved_at = datetime.now(timezone.utc)
    write_doc(target, root=root)
    persist_feature_dispatch_selection(
        FeatureDispatchSelection("feat_003", "epic/epic_001", None), root=root
    )


@pytest.mark.parametrize("stacked", [False, True])
def test_reports_all_active_siblings_and_separates_pending_review(
    tmp_path: Path, stacked: bool
) -> None:
    root = make_repo(tmp_path, git=False)
    _active_epic(root)
    write_stacked_pr_enabled("epic_001", stacked, root=root)
    for feature_id in ("feat_001", "feat_002"):
        add_doc(
            root,
            id=feature_id,
            title=feature_id,
            tier="feature",
            status="active",
            parent="epic_001",
        )
    add_doc(
        root,
        id="feat_004",
        title="Pending review",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    _approved_target(root)

    readiness = compute_feature_readiness(
        "feat_003",
        root=root,
        pending_review_ids=frozenset({"feat_004"}),
        review_refusals={},
    )

    assert readiness is not None
    assert "sibling_blocked" in readiness.blockers
    reasons = _reason_view(readiness)
    assert ("sibling_active_execution", ("feat_001", "feat_002")) in reasons
    if stacked:
        assert "feature_awaiting_merge" not in readiness.blockers
        assert ("feature_awaiting_merge", ("feat_004",)) not in reasons
    else:
        assert "feature_awaiting_merge" in readiness.blockers
        assert ("feature_awaiting_merge", ("feat_004",)) in reasons


def test_reason_priority_is_deterministic_and_unknown_evidence_fails_closed(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Inactive", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_002",
        title="Incomplete dependency",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_999",
        title="Unavailable dependency",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_001",
        title="Waiting",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_002", "feat_999"],
    )
    board = merged_board(root)
    board.by_id.pop("feat_999")

    readiness = compute_feature_readiness(
        "feat_001",
        root=root,
        board=board,
        pending_review_ids=frozenset(),
        review_refusals={"feat_001": "blocking_review_threads:thread_1"},
    )

    assert readiness is not None
    assert readiness.explanation is not None
    assert readiness.explanation.summary == "needs_action"
    assert readiness.explanation.primary_reason_code == "not_approved"
    assert _reason_view(readiness) == [
        ("not_approved", ("feat_001",)),
        ("review_threads_blocking", ("feat_001",)),
        ("dependency_status_unavailable", ("feat_999",)),
        ("dispatch_base_unavailable", ("feat_001",)),
        ("dependency_unmet", ("feat_002",)),
        ("epic_inactive", ("epic_001",)),
    ]


def test_ready_explanation_lists_satisfied_prerequisites(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _active_epic(root)
    _approved_target(root)

    readiness = compute_feature_readiness(
        "feat_003",
        root=root,
        pending_review_ids=frozenset(),
        review_refusals={},
    )

    assert readiness is not None
    assert readiness.approved is True
    assert readiness.blockers == []
    assert readiness.explanation is not None
    assert readiness.explanation.version == 1
    assert readiness.explanation.summary == "ready_awaiting_dispatch"
    assert readiness.explanation.primary_reason_code is None
    assert readiness.explanation.reasons == ()
    assert [item.code for item in readiness.explanation.satisfied] == [
        "approval_current",
        "dependencies_satisfied",
        "dispatch_base_available",
        "merge_review_clear",
        "parent_active",
        "review_threads_clear",
        "sibling_execution_clear",
    ]


def test_approved_sibling_wait_fixture_does_not_imply_reapproval(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _active_epic(root)
    add_doc(
        root,
        id="feat_009",
        title="Executing sibling",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    _approved_target(root)

    readiness = compute_feature_readiness(
        "feat_003",
        root=root,
        pending_review_ids=frozenset(),
        review_refusals={},
    )

    assert readiness is not None
    assert readiness.approved is True
    assert readiness.explanation is not None
    assert readiness.explanation.summary == "waiting"
    assert readiness.explanation.primary_reason_code == "sibling_active_execution"
    assert _reason_view(readiness) == [
        ("sibling_active_execution", ("feat_009",))
    ]
    assert "approval_current" in {
        item.code for item in readiness.explanation.satisfied
    }
    assert "not_approved" not in {code for code, _ids in _reason_view(readiness)}
