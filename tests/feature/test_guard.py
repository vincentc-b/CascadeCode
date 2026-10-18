"""Feature Team path sandbox (tool_guard)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.feature.guard import FeatureToolDenied, tool_guard
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path):
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
    other_epic = add_doc(root, id="epic_002", title="Other epic", tier="epic", status="backlog")
    feature = add_doc(
        root,
        id="feat_001",
        title="Mine",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    other_feature = add_doc(
        root,
        id="feat_002",
        title="Other feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    own_task = add_doc(
        root,
        id="task_001",
        title="Own task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    active_task = add_doc(
        root,
        id="task_002",
        title="Active task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    foreign_task = add_doc(
        root,
        id="task_003",
        title="Foreign task",
        tier="task",
        status="backlog",
        parent="feat_002",
    )
    return {
        "root": root,
        "epic": epic,
        "other_epic": other_epic,
        "feature": feature,
        "other_feature": other_feature,
        "own_task": own_task,
        "active_task": active_task,
        "foreign_task": foreign_task,
    }


def test_write_own_feature_and_comment_sidecar(board):
    root = board["root"]
    feature = board["feature"]
    own_comments = root / "docs/_comments/feat_001.jsonl"
    other_comments = root / "docs/_comments/feat_002.jsonl"
    assert tool_guard(feature.meta.path, "write", feature_id="feat_001", root=root)
    assert tool_guard(own_comments, "write", feature_id="feat_001", root=root)
    assert not tool_guard(other_comments, "write", feature_id="feat_001", root=root)


def test_write_backlog_task_new_and_owned(board):
    root = board["root"]
    new_task = root / "docs/tasks/1_backlog/task_099_new.md"
    own = board["own_task"].meta.path
    assert tool_guard(new_task, "write", feature_id="feat_001", root=root)
    assert tool_guard(own, "write", feature_id="feat_001", root=root)


def test_write_denied_epic_other_feature_active_task(board):
    root = board["root"]
    assert not tool_guard(board["epic"].meta.path, "write", feature_id="feat_001", root=root)
    assert not tool_guard(board["other_feature"].meta.path, "write", feature_id="feat_001", root=root)
    assert not tool_guard(board["active_task"].meta.path, "write", feature_id="feat_001", root=root)
    assert not tool_guard(board["foreign_task"].meta.path, "write", feature_id="feat_001", root=root)


def test_write_column_move_to_backlog_denied(board):
    root = board["root"]
    active = board["active_task"]
    backlog_shadow = root / "docs/tasks/1_backlog" / active.meta.path.name
    assert not tool_guard(backlog_shadow, "write", feature_id="feat_001", root=root)


def test_write_denied_queue_and_outside_docs(board):
    root = board["root"]
    queue = root / "docs/_queue/feat_001.jsonl"
    outside = root / "cascade.toml"
    assert not tool_guard(queue, "write", feature_id="feat_001", root=root)
    assert not tool_guard(outside, "write", feature_id="feat_001", root=root)


def test_read_parent_epic_own_tasks_and_comments(board):
    root = board["root"]
    feature = board["feature"]
    assert tool_guard(board["epic"].meta.path, "read", feature_id="feat_001", root=root)
    assert tool_guard(feature.meta.path, "read", feature_id="feat_001", root=root)
    assert tool_guard(board["own_task"].meta.path, "read", feature_id="feat_001", root=root)
    assert tool_guard(board["active_task"].meta.path, "read", feature_id="feat_001", root=root)
    own_comments = root / "docs/_comments/feat_001.jsonl"
    assert tool_guard(own_comments, "read", feature_id="feat_001", root=root)


def test_read_denied_foreign_epic_feature_task_sidecars(board):
    root = board["root"]
    war_room = root / "docs/_war_room/epic_001.jsonl"
    queue = root / "docs/_queue/feat_001.jsonl"
    amendment = root / "docs/epics/2_active/_amendments/feat_001_section.md"
    amendment.parent.mkdir(parents=True, exist_ok=True)
    amendment.write_text("# amendment\n", encoding="utf-8")
    other_comments = root / "docs/_comments/epic_001.jsonl"
    assert not tool_guard(board["other_epic"].meta.path, "read", feature_id="feat_001", root=root)
    assert not tool_guard(board["other_feature"].meta.path, "read", feature_id="feat_001", root=root)
    assert not tool_guard(board["foreign_task"].meta.path, "read", feature_id="feat_001", root=root)
    assert not tool_guard(war_room, "read", feature_id="feat_001", root=root)
    assert not tool_guard(queue, "read", feature_id="feat_001", root=root)
    assert not tool_guard(amendment, "read", feature_id="feat_001", root=root)
    assert not tool_guard(other_comments, "read", feature_id="feat_001", root=root)


def test_symlink_escape_denied(board):
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    evil = root / "docs/tasks/1_backlog/evil.md"
    evil.symlink_to(epic.meta.path)
    assert not tool_guard(evil, "write", feature_id="feat_001", root=root)
    assert not tool_guard(evil, "read", feature_id="feat_001", root=root)


def test_unknown_or_non_feature_id_denied(board):
    root = board["root"]
    feature_path = board["feature"].meta.path
    assert not tool_guard(feature_path, "read", feature_id="feat_999", root=root)
    assert not tool_guard(feature_path, "read", feature_id="epic_001", root=root)


def test_invalid_op_denied(board):
    root = board["root"]
    feature_path = board["feature"].meta.path
    assert not tool_guard(feature_path, "delete", feature_id="feat_001", root=root)


def test_guard_module_does_not_import_dispatch_or_move():
    root = Path(__file__).resolve().parents[2]
    text = (root / "cascade" / "feature" / "guard.py").read_text(encoding="utf-8")
    forbidden = ("move_doc", "dispatch_feature", "dispatch_task", "activate_epic")
    for symbol in forbidden:
        assert symbol not in text, f"guard.py must not reference {symbol}"


def test_feature_tool_denied_is_permission_error():
    assert issubclass(FeatureToolDenied, PermissionError)
