"""Board contract coverage for the Epic return-to-backlog control."""

from __future__ import annotations

from unittest.mock import patch

from cascade.board.store import list_board, move_doc
from cascade.epic.return_command import return_epic_to_backlog
from cascade.epic.return_eligibility import ReturnEligibilityInput, ReturnGraphMember
from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    merged_board,
)
from tests.support import add_doc, make_repo


def test_active_epic_row_and_command_share_return_eligibility(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_030", title="Returnable", tier="epic")
    move_doc("epic_030", "active", root=root)

    view = board_view_from_index(list_board(root), root=root)
    row = view["epics"]["2_active"][0]
    result = return_epic_to_backlog("epic_030", "request-1", actor="human", root=root)

    assert result.eligibility is not None
    assert row["return_to_backlog"] == result.eligibility.to_dict()
    assert row["return_to_backlog"]["eligible"] is True
    assert row["return_to_backlog"]["reason_codes"] == []
    assert result.ok
    assert merged_board(root).by_id["epic_030"].status == "backlog"


def test_return_eligibility_reads_active_integration_copy_over_stale_trunk_backlog(
    tmp_path,
):
    root = make_repo(tmp_path)
    add_doc(root, id="epic_028", title="Returnable", tier="epic")
    worktree = ensure_integration_worktree(
        "epic", "epic_028", branch="epic/epic_028", base_ref="main", trunk=root
    ).path
    move_doc("epic_028", "active", root=worktree)

    row = board_view_from_index(merged_board(root), root=root)["epics"]["2_active"][0]
    result = return_epic_to_backlog("epic_028", "request-1", actor="human", root=root)

    assert row["return_to_backlog"] == result.eligibility.to_dict()
    assert "epic_not_active" not in result.eligibility.reason_codes


def test_failed_provider_startup_without_mutation_remains_eligible_in_row_and_command(
    tmp_path,
):
    """Startup failure is not a refusal when authoritative preservation facts are safe."""

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_030", title="Returnable", tier="epic")
    move_doc("epic_030", "active", root=root)
    # This snapshot is the state after a provider failed before its first
    # substantive action: the failure itself is not a safety predicate.
    snapshot = ReturnEligibilityInput(
        epic_id="epic_030",
        epic_tier="epic",
        epic_status="active",
        epic_transition_in_progress=False,
        graph=(
            ReturnGraphMember(
                "epic_030",
                "epic",
                None,
                "brief-revision",
                "activation",
                True,
                False,
                True,
                True,
            ),
        ),
        graph_complete=True,
        source_brief_revision="brief-revision",
        lock_order=("epic_030",),
        conflicting_lifecycle_operation=False,
    )

    with patch(
        "cascade.epic.return_command.load_return_eligibility_snapshot",
        return_value=snapshot,
    ):
        row = board_view_from_index(list_board(root), root=root)["epics"]["2_active"][0]
        result = return_epic_to_backlog(
            "epic_030", "request-1", actor="human", root=root
        )

    assert row["return_to_backlog"] == result.eligibility.to_dict()
    assert row["return_to_backlog"] == {
        "eligible": True,
        "reason_codes": [],
        "refusals": [],
    }
    assert result.ok
    assert merged_board(root).by_id["epic_030"].status == "backlog"
