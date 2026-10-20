"""Epic Team path sandbox (tool_guard and scoped docs)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.epic.guard import EpicToolDenied, tool_guard
from cascade.epic.scoped_docs import epic_read_doc, epic_write_doc
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path):
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Mine", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Other", tier="epic", status="backlog")
    child = add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    active_child = add_doc(
        root,
        id="feat_002",
        title="Active child",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    other_feat = add_doc(
        root,
        id="feat_003",
        title="Other epic child",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    task = add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    return {
        "root": root,
        "epic": epic,
        "child": child,
        "active_child": active_child,
        "other_feat": other_feat,
        "task": task,
    }


def test_tool_guard_allows_epic_spec_under_cascade_worktree(board, monkeypatch):
    root = board["root"]
    epic = board["epic"]
    wt_epic = (
        root
        / ".cascade"
        / "worktrees"
        / "epic_epic_001"
        / "docs"
        / "epics"
        / "2_active"
        / epic.meta.path.name
    )
    wt_epic.parent.mkdir(parents=True, exist_ok=True)
    wt_epic.write_text(epic.meta.path.read_text(encoding="utf-8"), encoding="utf-8")
    live = read_doc("epic_001", root=root)
    live.meta.path = wt_epic.resolve()

    def _read_doc(work_id: str, *, root: Path):
        if work_id == "epic_001":
            return live
        return read_doc(work_id, root=root)

    monkeypatch.setattr("cascade.epic.guard.read_doc", _read_doc)
    monkeypatch.setattr("cascade.epic.scoped_docs.read_doc", _read_doc)
    assert tool_guard(wt_epic, "read", epic_id="epic_001", root=root)
    assert epic_read_doc("epic_001", epic_id="epic_001", root=root).meta.id == "epic_001"


def test_write_epic_file_allowed_other_epic_denied(board):
    root = board["root"]
    epic = board["epic"]
    other = read_doc("epic_002", root=root)
    assert tool_guard(epic.meta.path, "write", epic_id="epic_001", root=root)
    assert not tool_guard(other.meta.path, "write", epic_id="epic_001", root=root)


def test_write_backlog_new_and_denied_columns(board):
    root = board["root"]
    new_path = root / "docs/features/1_backlog/feat_099_new.md"
    active_path = board["active_child"].meta.path
    task_path = board["task"].meta.path
    assert tool_guard(new_path, "write", epic_id="epic_001", root=root)
    assert not tool_guard(active_path, "write", epic_id="epic_001", root=root)
    assert not tool_guard(task_path, "write", epic_id="epic_001", root=root)


def test_write_existing_feature_parent_rules(board):
    root = board["root"]
    own = board["child"].meta.path
    foreign = board["other_feat"].meta.path
    assert tool_guard(own, "write", epic_id="epic_001", root=root)
    assert not tool_guard(foreign, "write", epic_id="epic_001", root=root)


def test_write_column_move_denied(board):
    root = board["root"]
    active = board["active_child"]
    backlog_shadow = root / "docs/features/1_backlog" / active.meta.path.name
    assert not tool_guard(backlog_shadow, "write", epic_id="epic_001", root=root)


def test_read_child_and_denials(board):
    root = board["root"]
    assert tool_guard(board["child"].meta.path, "read", epic_id="epic_001", root=root)
    assert tool_guard(board["active_child"].meta.path, "read", epic_id="epic_001", root=root)
    assert not tool_guard(board["task"].meta.path, "read", epic_id="epic_001", root=root)
    assert not tool_guard(board["other_feat"].meta.path, "read", epic_id="epic_001", root=root)


def test_read_amendment_shape_allowed(board):
    root = board["root"]
    amendment = root / "docs/epics/2_active/_amendments/feat_001_section.md"
    amendment.parent.mkdir(parents=True, exist_ok=True)
    amendment.write_text("# amendment\n", encoding="utf-8")
    assert tool_guard(amendment, "read", epic_id="epic_001", root=root)


def test_read_amendment_denied_foreign_feature(board):
    root = board["root"]
    amendment = root / "docs/epics/2_active/_amendments/feat_003_section.md"
    amendment.parent.mkdir(parents=True, exist_ok=True)
    amendment.write_text("# amendment\n", encoding="utf-8")
    assert not tool_guard(amendment, "read", epic_id="epic_001", root=root)


def test_symlink_to_epic_denied(board):
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    evil = root / "docs/features/1_backlog/evil.md"
    evil.symlink_to(epic.meta.path)
    assert not tool_guard(evil, "write", epic_id="epic_001", root=root)
    evil_doc = read_doc("epic_001", root=root)
    evil_doc.meta.path = evil
    with pytest.raises(EpicToolDenied):
        epic_write_doc(evil_doc, epic_id="epic_001", root=root)


def test_epic_write_doc_feature_wrong_parent(board):
    root = board["root"]
    foreign = board["other_feat"]
    doc = read_doc(foreign.meta.id, root=root)
    doc.meta.parent = "epic_001"
    with pytest.raises(EpicToolDenied):
        epic_write_doc(doc, epic_id="epic_001", root=root)


def test_epic_write_doc_column_move_denied(board):
    root = board["root"]
    active = board["active_child"]
    doc = read_doc(active.meta.id, root=root)
    backlog_path = root / "docs/features/1_backlog" / active.meta.path.name
    doc.meta.path = backlog_path
    with pytest.raises(EpicToolDenied):
        epic_write_doc(doc, epic_id="epic_001", root=root)


def test_read_denied_sidecars_and_queue(board):
    root = board["root"]
    queue = root / "docs/_queue/epic_001.jsonl"
    comments = root / "docs/_comments/epic_001.jsonl"
    assert not tool_guard(queue, "read", epic_id="epic_001", root=root)
    assert not tool_guard(comments, "read", epic_id="epic_001", root=root)


def test_epic_write_doc_commits_and_task_denied(board):
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    epic.body = epic.body + "\n"
    sha = epic_write_doc(epic, epic_id="epic_001", root=root)
    assert sha is not None
    assert epic.meta.path.is_file()

    task = read_doc("task_001", root=root)
    with pytest.raises(EpicToolDenied):
        epic_write_doc(task, epic_id="epic_001", root=root)


def test_epic_read_doc_task_and_foreign_feature(board):
    root = board["root"]
    epic_read_doc("feat_001", epic_id="epic_001", root=root)
    with pytest.raises(EpicToolDenied):
        epic_read_doc("task_001", epic_id="epic_001", root=root)
    with pytest.raises(EpicToolDenied):
        epic_read_doc("feat_003", epic_id="epic_001", root=root)


def test_scoped_modules_do_not_import_dispatch_or_move():
    root = Path(__file__).resolve().parents[2]
    forbidden = ("move_doc", "dispatch_feature", "dispatch_task", "activate_epic")
    for name in ("guard.py", "scoped_docs.py"):
        text = (root / "cascade" / "epic" / name).read_text(encoding="utf-8")
        for symbol in forbidden:
            assert symbol not in text, f"{name} must not reference {symbol}"
