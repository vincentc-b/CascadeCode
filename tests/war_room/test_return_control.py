"""Board contract coverage for the Epic return-to-backlog control."""

from __future__ import annotations

from cascade.board.store import list_board, move_doc
from cascade.epic.return_command import return_epic_to_backlog
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
