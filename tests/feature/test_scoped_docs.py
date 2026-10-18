"""Feature Team scoped read_doc, write_doc, list_children."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

import cascade.feature.docs_tool  # noqa: F401 — registers tools
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.registry import feature_tools
from cascade.feature.scoped_docs import (
    comment_work_id,
    feature_read_doc,
    feature_write_doc,
    list_children,
)
from cascade.feature.wiring import load_feature_tools
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
    add_doc(
        root,
        id="task_002",
        title="Active task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
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
    }


def test_tools_register_on_import():
    load_feature_tools()
    names = feature_tools()
    assert "read_doc" in names
    assert "write_doc" in names
    assert "list_children" in names


def test_parent_epic_at_parent_rev(board):
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    pinned_body = epic.body + "\n\n## Decision log\n\n- dec_pinned · pinned text\n"
    pinned = deepcopy(epic)
    pinned.body = pinned_body
    write_doc(pinned, root=root)
    pin_parent("feat_001", "epic_001", root=root)

    live = deepcopy(epic)
    live.body = epic.body + "\n\n## Decision log\n\n- dec_live · newer text\n"
    write_doc(live, root=root)

    doc = feature_read_doc("epic_001", feature_id="feat_001", root=root)
    assert "dec_pinned" in doc.body
    assert "dec_live" not in doc.body
    assert doc.sha == read_doc("feat_001", root=root).meta.parent_rev


def test_parent_epic_denied_without_parent_rev(board):
    root = board["root"]
    with pytest.raises(FeatureToolDenied, match="parent_rev"):
        feature_read_doc("epic_001", feature_id="feat_001", root=root)


def test_read_self_task_and_own_comments(board):
    root = board["root"]
    feature = board["feature"]
    own_task = board["own_task"]

    self_doc = feature_read_doc("feat_001", feature_id="feat_001", root=root)
    assert self_doc.meta.id == "feat_001"

    task_doc = feature_read_doc("task_001", feature_id="feat_001", root=root)
    assert task_doc.meta.parent == "feat_001"

    sidecar = root / "docs/_comments/feat_001.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text('{"id":"cmt_001","body":"hello"}\n', encoding="utf-8")
    comments = feature_read_doc(
        comment_work_id("feat_001"), feature_id="feat_001", root=root
    )
    assert "cmt_001" in comments.body

    sidecar.unlink()
    empty = feature_read_doc(
        comment_work_id("feat_001"), feature_id="feat_001", root=root
    )
    assert empty.body == ""


def test_write_doc_cannot_clear_blocked_status(board):
    root = board["root"]
    doc = read_doc("feat_001", root=root)
    doc.meta.status = "blocked"
    write_doc(doc, root=root)

    active_attempt = deepcopy(read_doc("feat_001", root=root))
    active_attempt.meta.status = "active"
    with pytest.raises(FeatureToolDenied, match="cannot change status away from blocked"):
        feature_write_doc(active_attempt, feature_id="feat_001", root=root)

    still_blocked = deepcopy(read_doc("feat_001", root=root))
    still_blocked.meta.status = "blocked"
    still_blocked.body = still_blocked.body + "\n"
    feature_write_doc(still_blocked, feature_id="feat_001", root=root)
    assert read_doc("feat_001", root=root).meta.status == "blocked"


def test_write_own_feature_only(board):
    root = board["root"]
    doc = read_doc("feat_001", root=root)
    doc.body = doc.body.replace("None yet.", "dec_test · scoped write")
    sha = feature_write_doc(doc, feature_id="feat_001", root=root)
    assert sha is not None
    updated = read_doc("feat_001", root=root)
    assert "dec_test" in updated.body


def test_write_denied_epic_and_task(board):
    root = board["root"]
    epic = read_doc("epic_001", root=root)
    with pytest.raises(FeatureToolDenied):
        feature_write_doc(epic, feature_id="feat_001", root=root)

    task = read_doc("task_001", root=root)
    with pytest.raises(FeatureToolDenied):
        feature_write_doc(task, feature_id="feat_001", root=root)


def test_read_denied_foreign_feature_epic_and_comments(board):
    root = board["root"]
    with pytest.raises(FeatureToolDenied):
        feature_read_doc("feat_002", feature_id="feat_001", root=root)
    with pytest.raises(FeatureToolDenied):
        feature_read_doc("epic_002", feature_id="feat_001", root=root)
    with pytest.raises(FeatureToolDenied):
        feature_read_doc("task_003", feature_id="feat_001", root=root)
    with pytest.raises(FeatureToolDenied):
        feature_read_doc(comment_work_id("feat_002"), feature_id="feat_001", root=root)


def test_no_war_room_transcript_reads(board):
    root = board["root"]
    war_room = root / "docs/_war_room/epic_001.jsonl"
    war_room.parent.mkdir(parents=True, exist_ok=True)
    war_room.write_text('{"role":"human","body":"secret"}\n', encoding="utf-8")
    with pytest.raises(FeatureToolDenied):
        feature_read_doc("_war_room/epic_001", feature_id="feat_001", root=root)


def test_list_children_tasks_only(board):
    root = board["root"]
    children = list_children(feature_id="feat_001", root=root)
    ids = [meta.id for meta in children]
    assert ids == ["task_001", "task_002"]
    assert all(meta.tier == "task" for meta in children)
    assert all(meta.parent == "feat_001" for meta in children)


def test_scoped_docs_module_does_not_import_dispatch_or_move():
    root = Path(__file__).resolve().parents[2]
    text = (root / "cascade" / "feature" / "scoped_docs.py").read_text(encoding="utf-8")
    forbidden = ("move_doc", "dispatch_feature", "dispatch_task", "activate_epic")
    for symbol in forbidden:
        assert symbol not in text, f"scoped_docs.py must not reference {symbol}"
