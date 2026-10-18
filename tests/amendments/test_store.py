"""Amendment sidecar store (task_026)."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.amendments import (
    Amendment,
    AmendmentNotFound,
    allocate_amd_id,
    find_open_for_section,
    list_pending_for_epic,
    load_by_path,
    read_amendment,
    section_slug,
    sidecar_paths,
    unified_section_diff,
    update_amendment,
    write_sidecar,
)
from cascade.board import list_board
from tests.support import add_doc, make_repo

EPIC_BODY = """\
# Epic

## Memory Layout

Old constraint text.
More lines.

## Cross-module constraints

Untouched.
"""


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    return root


def _draft(**overrides: object) -> Amendment:
    base = Amendment(
        id="",
        feature_id="feat_001",
        epic_id="epic_001",
        section="Memory Layout",
        diff_path=Path("."),
        proposed_text="New layout rules.",
        rationale="Need more RAM.",
        state="pending",
        created=datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc),
    )
    return Amendment(**{**base.__dict__, **overrides})


def test_allocate_amd_id_monotonic(board: Path) -> None:
    assert allocate_amd_id(root=board) == "amd_001"
    first = write_sidecar(_draft(), EPIC_BODY, root=board)
    assert first.id == "amd_001"
    assert allocate_amd_id(root=board) == "amd_002"


def test_section_slug_paths(board: Path) -> None:
    assert section_slug("Memory Layout") == "memory_layout"
    diff_path, meta_path = sidecar_paths("feat_001", "Memory Layout", root=board)
    assert diff_path.name == "feat_001_memory_layout.diff.md"
    assert meta_path.name == "feat_001_memory_layout.meta.json"
    assert "_amendments" in diff_path.parts


def test_write_read_round_trip(board: Path) -> None:
    written = write_sidecar(_draft(), EPIC_BODY, root=board)
    diff_path, meta_path = sidecar_paths("feat_001", "Memory Layout", root=board)
    assert diff_path.is_file()
    assert meta_path.is_file()

    diff_text = diff_path.read_text(encoding="utf-8")
    assert diff_text.startswith("<!-- Amendment: Memory Layout -->")
    assert "---" in diff_text
    assert "Old constraint text" in diff_text
    assert "New layout rules" in diff_text

    loaded = read_amendment("amd_001", root=board)
    assert loaded == written
    assert loaded.diff_path.as_posix().endswith("feat_001_memory_layout.diff.md")

    by_path = load_by_path(written.diff_path, root=board)
    assert by_path.id == "amd_001"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["created"].endswith("Z") or "+" in meta["created"]


def test_extract_section_body_fails_on_duplicate_heading() -> None:
    from cascade.amendments.diff import extract_section_body

    body = EPIC_BODY + "\n## Memory Layout\n\nDuplicate section.\n"
    with pytest.raises(ValueError, match="duplicate section"):
        extract_section_body(body, "Memory Layout")


def test_unified_diff_uses_section_body_only() -> None:
    diff = unified_section_diff(
        EPIC_BODY,
        "Memory Layout",
        "Replacement only.",
        epic_label="epic_001",
    )
    assert "Untouched" not in diff
    assert "Old constraint text" in diff
    assert "Replacement only" in diff


def test_list_and_find_helpers(board: Path) -> None:
    write_sidecar(_draft(), EPIC_BODY, root=board)
    pending = list_pending_for_epic("epic_001", root=board)
    assert len(pending) == 1
    assert pending[0].state == "pending"

    open_row = find_open_for_section("epic_001", "Memory Layout", root=board)
    assert open_row is not None
    assert open_row.id == "amd_001"

    assert find_open_for_section("epic_001", "Other", root=board) is None

    updated = update_amendment(replace(open_row, state="accepted"), root=board)
    assert updated.state == "accepted"
    assert list_pending_for_epic("epic_001", root=board) == []

    revise = write_sidecar(
        _draft(id="", state="revise_pending", section="Scope"),
        EPIC_BODY.replace("Memory Layout", "Scope").replace(
            "Old constraint text.", "Scope body."
        ),
        root=board,
    )
    assert revise.id == "amd_002"
    open_scope = find_open_for_section("epic_001", "Scope", root=board)
    assert open_scope is not None
    assert open_scope.state == "revise_pending"
    assert len(list_pending_for_epic("epic_001", root=board)) == 1


def test_missing_and_invalid_id(board: Path) -> None:
    with pytest.raises(AmendmentNotFound):
        read_amendment("amd_999", root=board)
    with pytest.raises(AmendmentNotFound):
        read_amendment("not_an_id", root=board)

    diff_path, _ = sidecar_paths("feat_001", "Memory Layout", root=board)
    with pytest.raises(AmendmentNotFound):
        load_by_path(diff_path, root=board)


def test_list_board_ignores_sidecars(board: Path) -> None:
    write_sidecar(_draft(), EPIC_BODY, root=board)
    index = list_board(board)
    assert set(index.by_id) == {"epic_001", "feat_001"}
