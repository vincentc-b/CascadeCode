"""Service coverage for durable per-Epic backlog feature priority."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.board.store import move_doc
from cascade.war_room.backlog_priority import (
    BacklogPriorityError,
    read_backlog_priority,
    reorder_backlog_features,
)
from cascade.workspace.integration_worktree import invalidate_merged_board
from tests.support import add_doc, make_repo


@pytest.fixture
def priority_board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Other epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="First",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_099",
        title="Other epic feature",
        tier="feature",
        parent="epic_002",
    )
    add_doc(
        root,
        id="feat_003",
        title="Already dispatched",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    return root


def test_priority_persists_and_reloads_from_every_client_root(priority_board: Path) -> None:
    initial = read_backlog_priority("epic_001", root=priority_board)
    reordered = reorder_backlog_features(
        "epic_001",
        ["feat_002", "feat_001"],
        version=initial.version,
        root=priority_board,
    )

    # An integration client resolves the same trunk-owned durable file.
    client_root = priority_board / ".cascade" / "worktrees" / "feat_feat_001"
    reloaded = read_backlog_priority("epic_001", root=client_root)

    assert reordered.feature_ids == ("feat_002", "feat_001")
    assert reloaded == reordered
    payload = json.loads(
        (priority_board / ".cascade" / "backlog_feature_priority.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["epics"]["epic_001"] == {
        "feature_ids": ["feat_002", "feat_001"],
        "version": 2,
    }


def test_read_appends_new_peers_and_compacts_departed_or_removed_features(
    priority_board: Path,
) -> None:
    initial = read_backlog_priority("epic_001", root=priority_board)
    ranked = reorder_backlog_features(
        "epic_001",
        ["feat_002", "feat_001"],
        version=initial.version,
        root=priority_board,
    )
    add_doc(
        priority_board,
        id="feat_004",
        title="New peer",
        tier="feature",
        parent="epic_001",
    )

    appended = read_backlog_priority("epic_001", root=priority_board)
    assert appended.feature_ids == ("feat_002", "feat_001", "feat_004")
    assert appended.version == ranked.version + 1

    move_doc("feat_001", "active", root=priority_board)
    compacted = read_backlog_priority("epic_001", root=priority_board)
    assert compacted.feature_ids == ("feat_002", "feat_004")
    assert compacted.version == appended.version + 1

    feature_path = next(
        (priority_board / "docs" / "features" / "1_backlog").glob("feat_002_*.md")
    )
    feature_path.unlink()
    invalidate_merged_board(priority_board)
    removed = read_backlog_priority("epic_001", root=priority_board)
    assert removed.feature_ids == ("feat_004",)
    assert removed.version == compacted.version + 1


def test_reorder_accepts_exact_current_membership(priority_board: Path) -> None:
    current = read_backlog_priority("epic_001", root=priority_board)

    result = reorder_backlog_features(
        "epic_001",
        list(reversed(current.feature_ids)),
        version=current.version,
        root=priority_board,
    )

    assert result.feature_ids == tuple(reversed(current.feature_ids))
    assert result.version == current.version + 1
    assert read_backlog_priority("epic_001", root=priority_board) == result


@pytest.mark.parametrize(
    ("submitted", "code"),
    [
        (["feat_001", "feat_001"], "duplicate_id"),
        (["feat_001", "feat_missing"], "unknown_id"),
        (["feat_001", "feat_099"], "cross_epic_id"),
        (["feat_001", "feat_003"], "non_backlog_id"),
        (["feat_001"], "membership_mismatch"),
    ],
)
def test_invalid_reorders_leave_durable_state_unchanged(
    priority_board: Path,
    submitted: list[str],
    code: str,
) -> None:
    current = read_backlog_priority("epic_001", root=priority_board)
    state_path = priority_board / ".cascade" / "backlog_feature_priority.json"
    before = state_path.read_bytes()

    with pytest.raises(BacklogPriorityError) as exc_info:
        reorder_backlog_features(
            "epic_001",
            submitted,
            version=current.version,
            root=priority_board,
        )

    assert exc_info.value.code == code
    assert state_path.read_bytes() == before
    assert read_backlog_priority("epic_001", root=priority_board) == current


def test_stale_reorder_is_refused_without_changing_state(priority_board: Path) -> None:
    initial = read_backlog_priority("epic_001", root=priority_board)
    accepted = reorder_backlog_features(
        "epic_001",
        ["feat_002", "feat_001"],
        version=initial.version,
        root=priority_board,
    )
    state_path = priority_board / ".cascade" / "backlog_feature_priority.json"
    before = state_path.read_bytes()

    with pytest.raises(BacklogPriorityError) as exc_info:
        reorder_backlog_features(
            "epic_001",
            ["feat_001", "feat_002"],
            version=initial.version,
            root=priority_board,
        )

    assert exc_info.value.code == "stale_version"
    assert state_path.read_bytes() == before
    assert read_backlog_priority("epic_001", root=priority_board) == accepted


def test_rejected_stale_write_does_not_persist_pending_reconciliation(
    priority_board: Path,
) -> None:
    initial = read_backlog_priority("epic_001", root=priority_board)
    state_path = priority_board / ".cascade" / "backlog_feature_priority.json"
    before = state_path.read_bytes()
    add_doc(
        priority_board,
        id="feat_004",
        title="New peer",
        tier="feature",
        parent="epic_001",
    )

    with pytest.raises(BacklogPriorityError) as exc_info:
        reorder_backlog_features(
            "epic_001",
            ["feat_001", "feat_002"],
            version=initial.version,
            root=priority_board,
        )

    assert exc_info.value.code == "stale_version"
    assert state_path.read_bytes() == before
    reconciled = read_backlog_priority("epic_001", root=priority_board)
    assert reconciled.feature_ids == ("feat_001", "feat_002", "feat_004")
    assert reconciled.version == initial.version + 1
