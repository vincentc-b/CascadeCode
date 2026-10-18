"""ack_amendment (task_028)."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.feature.amendments as amendments_mod  # noqa: F401
from cascade.amendments import read_amendment
from cascade.epic.amendments import resolve_amendment
from cascade.feature.amendments import ack_amendment, propose_epic_amendment
from cascade.feature.registry import clear_feature_tools
from cascade.feature.wiring import load_feature_tools
from cascade.board.store import pin_parent, read_doc, write_doc
from tests.support import EPIC_BODY, add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    epic = read_doc("epic_001", root=root)
    epic.body = EPIC_BODY
    write_doc(epic, root=root)
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_001", "epic_001", root=root)
    return root


def test_ack_preconditions_and_stays_blocked(board: Path) -> None:
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Proposal.",
        "Because.",
        feature_id="feat_001",
        root=board,
    )
    resolve_amendment(
        amd_id,
        "revise",
        revised_text="Revised.",
        epic_id="epic_001",
        root=board,
    )

    with pytest.raises(amendments_mod.AckAmendmentError, match="feat_001"):
        ack_amendment(amd_id, feature_id="feat_002", root=board)

    ack_amendment(amd_id, feature_id="feat_001", root=board)
    record = read_amendment(amd_id, root=board)
    assert record.state == "pending"
    assert record.proposed_text == "Revised."
    assert read_doc("feat_001", root=board).meta.status == "blocked"


def test_ack_refused_while_pending(board: Path) -> None:
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Proposal.",
        "Because.",
        feature_id="feat_001",
        root=board,
    )
    with pytest.raises(amendments_mod.AckAmendmentError, match="revise_pending"):
        ack_amendment(amd_id, feature_id="feat_001", root=board)


def test_ack_error_class_survives_load_feature_tools(board: Path) -> None:
    clear_feature_tools()
    load_feature_tools()
    amd_id = propose_epic_amendment(
        "epic_001",
        "Cross-module constraints",
        "Proposal.",
        "Because.",
        feature_id="feat_001",
        root=board,
    )
    with pytest.raises(amendments_mod.AckAmendmentError, match="revise_pending"):
        ack_amendment(amd_id, feature_id="feat_001", root=board)
