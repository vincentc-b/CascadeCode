"""Persistence for revision-bound epic planning sign-offs."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.approvals import approve_epic_plan, epic_plan_approved
from cascade.board.store import read_doc, write_doc
from cascade.epic.planning_signoffs import (
    InvalidPlanningRole,
    canonical_plan_revision,
    current_valid_sign_offs,
    hydrate_plan_sign_offs,
    read_plan_sign_offs,
    record_plan_sign_off,
    sidecar_path,
    valid_sign_offs_for_revision,
)
from tests.support import EPIC_BODY, add_doc, commit_board, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    commit_board(root, "initial")
    return root


def test_active_unapproved_epic_starts_without_valid_sign_offs(board: Path) -> None:
    assert read_plan_sign_offs("epic_001", root=board) == ()
    assert current_valid_sign_offs("epic_001", root=board) == {}
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None


def test_hydration_writes_empty_sidecar_for_active_unapproved(board: Path) -> None:
    hydrate_plan_sign_offs("epic_001", root=board)
    path = sidecar_path("epic_001", root=board)
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == 1
    assert payload["sign_offs"] == []
    assert current_valid_sign_offs("epic_001", root=board) == {}


def test_record_and_idempotent_sign_off(board: Path) -> None:
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None
    when = datetime(2026, 10, 23, 12, 0, tzinfo=timezone.utc)

    assert record_plan_sign_off(
        "epic_001", "epic_manager", revision, root=board, signed_at=when
    ) is True
    assert record_plan_sign_off(
        "epic_001", "epic_manager", revision, root=board, signed_at=when
    ) is False

    stored = read_plan_sign_offs("epic_001", root=board)
    assert len(stored) == 1
    assert stored[0].role == "epic_manager"
    assert stored[0].plan_revision == revision
    assert stored[0].signed_at == when

    valid = current_valid_sign_offs("epic_001", root=board)
    assert set(valid) == {"epic_manager"}


def test_both_roles_same_revision(board: Path) -> None:
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None
    assert record_plan_sign_off("epic_001", "epic_manager", revision, root=board) is True
    assert record_plan_sign_off("epic_001", "epic_architect", revision, root=board) is True
    valid = current_valid_sign_offs("epic_001", root=board)
    assert set(valid) == {"epic_manager", "epic_architect"}


def test_stale_revision_retained_but_not_current(board: Path) -> None:
    revision_a = canonical_plan_revision("epic_001", root=board)
    assert revision_a is not None
    record_plan_sign_off("epic_001", "epic_manager", revision_a, root=board)
    record_plan_sign_off("epic_001", "epic_architect", revision_a, root=board)

    epic = read_doc("epic_001", root=board)
    epic.body = EPIC_BODY.replace("None yet.", "Added detail.")
    write_doc(epic, root=board)
    commit_board(board, "plan edit")

    revision_b = canonical_plan_revision("epic_001", root=board)
    assert revision_b is not None
    assert revision_b != revision_a

    stored = read_plan_sign_offs("epic_001", root=board)
    assert len(stored) == 2
    assert valid_sign_offs_for_revision(stored, revision_a)
    assert current_valid_sign_offs("epic_001", root=board) == {}

    record_plan_sign_off("epic_001", "epic_manager", revision_b, root=board)
    record_plan_sign_off("epic_001", "epic_architect", revision_b, root=board)
    assert set(current_valid_sign_offs("epic_001", root=board)) == {
        "epic_manager",
        "epic_architect",
    }


def test_new_revision_adds_role_sign_off_without_dropping_old(board: Path) -> None:
    revision_a = canonical_plan_revision("epic_001", root=board)
    assert revision_a is not None
    record_plan_sign_off("epic_001", "epic_manager", revision_a, root=board)

    epic = read_doc("epic_001", root=board)
    epic.body = EPIC_BODY.replace("None yet.", "Second revision.")
    write_doc(epic, root=board)
    commit_board(board, "touch")
    revision_b = canonical_plan_revision("epic_001", root=board)
    assert revision_b is not None
    assert revision_b != revision_a

    assert record_plan_sign_off("epic_001", "epic_manager", revision_b, root=board) is True
    roles_revisions = {(row.role, row.plan_revision) for row in read_plan_sign_offs("epic_001", root=board)}
    assert ("epic_manager", revision_a) in roles_revisions
    assert ("epic_manager", revision_b) in roles_revisions


def test_approved_epic_unchanged_and_hydration_skips_sidecar(board: Path) -> None:
    approve_epic_plan("epic_001", root=board)
    assert epic_plan_approved("epic_001", root=board) is True
    hydrate_plan_sign_offs("epic_001", root=board)
    assert not sidecar_path("epic_001", root=board).exists()


def test_invalid_role_rejected(board: Path) -> None:
    revision = canonical_plan_revision("epic_001", root=board)
    assert revision is not None
    with pytest.raises(InvalidPlanningRole):
        record_plan_sign_off("epic_001", "boss", revision, root=board)  # type: ignore[arg-type]
