"""write_doc, move_doc, list_board, allocate_id, read_doc, and pin_parent."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board import (
    CycleError,
    NotFound,
    SchemaError,
    allocate_id,
    list_board,
    move_doc,
    pin_parent,
    read_doc,
    write_doc,
)
from tests.support import add_doc, make_repo


def _porcelain(root: Path) -> str:
    result = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _subject(root: Path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%s"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_write_without_git_returns_none(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    doc = add_doc(root, id="epic_001", title="No git epic", tier="epic")
    assert doc.sha is None
    assert doc.meta.path.is_file()
    assert doc.meta.status == "backlog"
    listed = list_board(root)
    assert set(listed.by_id) == {"epic_001"}


def test_write_commits_only_that_file(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    staged = root / "notes.txt"
    staged.write_text("leave me staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "notes.txt"], cwd=root, check=True)
    scratch = root / "scratch.txt"
    scratch.write_text("untracked\n", encoding="utf-8")

    doc = add_doc(root, id="epic_001", title="Committed epic", tier="epic")
    assert doc.sha is not None and len(doc.sha) == 40
    assert _subject(root) == "docs: epic_001 Committed epic"

    show = subprocess.run(
        ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    names = [line for line in show.stdout.splitlines() if line.strip()]
    assert names == ["docs/epics/1_backlog/epic_001_committed_epic.md"]

    status = _porcelain(root)
    assert "notes.txt" in status
    assert "scratch.txt" in status
    assert "epic_001" not in status


def test_move_doc_sets_column_default_status(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    doc = add_doc(root, id="epic_001", title="Movable epic", tier="epic", status="ready_to_plan")
    old = doc.meta.path
    sha = move_doc("epic_001", "active", root=root)
    assert sha is not None
    assert not old.exists()
    moved = read_doc("epic_001", root=root)
    assert moved.meta.status == "active"
    assert moved.meta.path.parent.name == "2_active"
    assert "epic_001" not in _porcelain(root)


def test_move_doc_does_not_move_when_validate_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    doc = add_doc(root, id="epic_001", title="Stay put", tier="epic")
    original = doc.meta.path.read_bytes()
    doc.meta.path.write_text(doc.meta.path.read_text(encoding="utf-8").replace("## Intent\n", "", 1), encoding="utf-8")
    broken = doc.meta.path.read_bytes()
    dest = root / "docs" / "epics" / "2_active" / doc.meta.path.name
    with pytest.raises(SchemaError):
        move_doc("epic_001", "active", root=root)
    assert doc.meta.path.read_bytes() == broken
    assert not dest.exists()
    assert original != broken


def test_write_rejects_cycle_without_creating_the_edge(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature A", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Feature B",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    doc = read_doc("feat_001", root=root)
    doc.meta.depends_on = ["feat_002"]
    with pytest.raises(CycleError):
        write_doc(doc, root=root)
    assert read_doc("feat_001", root=root).meta.depends_on == []


def test_allocate_id_fills_gaps_and_does_not_reuse(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="One", tier="epic")
    add_doc(root, id="epic_003", title="Three", tier="epic")
    board = list_board(root)
    assert allocate_id("epic", board) == "epic_002"
    assert allocate_id("epic", board) == "epic_004"
    assert allocate_id("task", board) == "task_001"


def test_read_doc_at_revision(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Original title", tier="epic")
    first = read_doc("epic_001", root=root)
    assert first.sha is not None
    edited = read_doc("epic_001", root=root)
    edited.meta.title = "Changed title"
    write_doc(edited, root=root)
    old = read_doc("epic_001", first.sha, root=root)
    assert old.meta.title == "Original title"
    assert read_doc("epic_001", root=root).meta.title == "Changed title"


def test_pin_parent_records_parent_sha(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic")
    add_doc(root, id="feat_001", title="Child feature", tier="feature", parent="epic_001")
    parent = read_doc("epic_001", root=root)
    returned = pin_parent("feat_001", "epic_001", root=root)
    child = read_doc("feat_001", root=root)
    assert parent.sha is not None
    assert child.meta.parent_rev == parent.sha
    assert returned == child.sha
    assert returned != parent.sha


def test_pin_parent_follows_newer_parent_commit(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic")
    add_doc(root, id="feat_001", title="Child feature", tier="feature", parent="epic_001")
    pin_parent("feat_001", "epic_001", root=root)
    first = read_doc("feat_001", root=root).meta.parent_rev
    parent = read_doc("epic_001", root=root)
    parent.meta.title = "Edited parent"
    write_doc(parent, root=root)
    newer = read_doc("epic_001", root=root).sha
    assert first is not None and newer is not None and newer != first
    pin_parent("feat_001", "epic_001", root=root)
    assert read_doc("feat_001", root=root).meta.parent_rev == newer


def test_read_doc_revision_before_column_move(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    created = add_doc(root, id="epic_001", title="Before move", tier="epic")
    assert created.sha is not None
    move_doc("epic_001", "active", root=root)
    old = read_doc("epic_001", created.sha, root=root)
    assert old.meta.status == "backlog"
    assert old.meta.title == "Before move"
    assert old.meta.path.parent.name == "1_backlog"
    assert read_doc("epic_001", root=root).meta.status == "active"


def test_pin_parent_without_git_history_sets_null(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic")
    add_doc(root, id="feat_001", title="Child feature", tier="feature", parent="epic_001")
    assert pin_parent("feat_001", "epic_001", root=root) is None
    assert read_doc("feat_001", root=root).meta.parent_rev is None


def test_move_unknown_id_raises(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    with pytest.raises(NotFound):
        move_doc("epic_999", "active", root=root)


def test_list_board_sees_new_files(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert list_board(root).by_id == {}
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    assert "epic_001" in list_board(root).by_id
