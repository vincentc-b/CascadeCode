"""Board contract coverage for the Epic return-to-backlog control."""

from __future__ import annotations

from unittest.mock import patch

from cascade.board.store import list_board, move_doc
from cascade.epic.return_command import return_epic_to_backlog
from cascade.epic.return_eligibility import ReturnEligibilityInput, ReturnGraphMember
from cascade.war_room.serialize import board_view_from_index
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
    assert row["return_to_backlog"]["eligible"] is False
    assert row["return_to_backlog"]["reason_codes"] == [
        "epic_transition_in_progress",
        "conflicting_lifecycle_operation",
        "source_brief_missing",
        "graph_unavailable",
    ]


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
    # Feature 030_002 owns the transition, so the eligible command still makes
    # no mutation while that capability is intentionally unavailable.
    assert result.error_code == "transition_unavailable"
    assert list_board(root).by_id["epic_030"].status == "active"
