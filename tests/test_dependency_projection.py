"""Safe dependency-status projection from authoritative evaluation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.dependency_projection import project_dependency_status
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo


def _dependent_board(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Complete private plan",
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
    return root, board


def test_projection_represents_safe_lifecycle_outcomes_in_declared_order(
    tmp_path: Path,
) -> None:
    root, board = _dependent_board(tmp_path)
    observed_at = datetime(2026, 11, 6, 12, tzinfo=timezone.utc)

    projection = project_dependency_status(
        board.by_id["feat_005"],
        root=root,
        board=board,
        observed_at=observed_at,
    )

    assert projection.outcome == "dependency_status_unavailable"
    assert projection.observed_at == observed_at
    assert projection.snapshot_fingerprint is not None
    assert projection.snapshot_fingerprint.startswith("sha256:")
    assert [row.work_id for row in projection.dependencies] == [
        "feat_001",
        "feat_002",
        "feat_003",
        "feat_004",
        "feat_999",
    ]
    assert [row.outcome for row in projection.dependencies] == [
        "satisfied",
        "dependency_unmet",
        "dependency_unmet",
        "dependency_unmet",
        "dependency_status_unavailable",
    ]
    assert [row.unavailable_reason for row in projection.dependencies] == [
        None,
        None,
        None,
        None,
        "dependency_not_found",
    ]
    assert [
        (row.status, row.column) for row in projection.dependencies[1:4]
    ] == [
        ("active", "2_active"),
        ("cancelled", "3_completed"),
        ("completed", "2_active"),
    ]
    completed = projection.dependencies[0]
    assert (completed.tier, completed.status, completed.column) == (
        "feature",
        "completed",
        "3_completed",
    )
    assert completed.completion_evidence == "canonical_completed_in_3_completed"
    assert all(row.completion_evidence is None for row in projection.dependencies[1:])

    payload = projection.to_dict()
    serialized = repr(payload)
    assert "Complete private plan" not in serialized
    assert str(root) not in serialized
    assert set(payload) == {
        "owner_work_id",
        "observed_at",
        "snapshot_fingerprint",
        "outcome",
        "dependencies",
    }


def test_projection_source_failure_is_stable_safe_and_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Dependency", tier="epic")
    add_doc(root, id="epic_003", title="Private dependency", tier="epic")
    dependent = add_doc(
        root,
        id="epic_002",
        title="Dependent",
        tier="epic",
        depends_on=["epic_001", "epic_003"],
    ).meta

    def fail_board(_root: Path):
        raise OSError(f"secret exception at {root}")

    monkeypatch.setattr("cascade.dependency_evaluation.merged_board", fail_board)

    projection = project_dependency_status(dependent, root=root)

    assert projection.outcome == "dependency_status_unavailable"
    assert projection.snapshot_fingerprint is None
    assert [row.work_id for row in projection.dependencies] == [
        "epic_001",
        "epic_003",
    ]
    assert all(
        row.unavailable_reason == "dependency_source_unavailable"
        for row in projection.dependencies
    )
    assert "secret exception" not in repr(projection.to_dict())
    assert str(root) not in repr(projection.to_dict())


def test_projection_empty_dependencies_are_satisfied_and_fingerprinted(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    owner = add_doc(root, id="epic_001", title="No dependencies", tier="epic").meta

    projection = project_dependency_status(owner, root=root)

    assert projection.outcome == "satisfied"
    assert projection.dependencies == ()
    assert projection.snapshot_fingerprint is not None
