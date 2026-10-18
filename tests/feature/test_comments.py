"""Feature Team comment tools."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import cascade.feature.comments_tool as comments_tool
from cascade.comments.store import comment
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.registry import clear_feature_tools
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _reload_feature_comment_tools() -> None:
    clear_feature_tools()
    importlib.reload(comments_tool)
    yield
    clear_feature_tools()


@pytest.fixture
def board(tmp_path: Path):
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


def test_feature_reply_and_resolve_own_thread(board: Path) -> None:
    root_id = comment("feat_001", "Scope", "human note", author="human", root=board)
    reply_id = comments_tool.reply_comment(
        root_id,
        "ack",
        feature_id="feat_001",
        root=board,
    )
    assert reply_id == "cmt_002"
    comments_tool.resolve_comment(root_id, feature_id="feat_001", root=board)
    from cascade.comments.store import read_comments

    root_row = next(row for row in read_comments("feat_001", root=board) if row.id == root_id)
    assert root_row.state == "resolved"


def test_feature_cannot_touch_epic_doc(board: Path) -> None:
    epic_cmt = comment("epic_001", "Intent", "epic note", author="human", root=board)
    with pytest.raises(FeatureToolDenied, match="epic-owned"):
        comments_tool.resolve_comment(
            epic_cmt,
            feature_id="feat_001",
            root=board,
            doc_id="epic_001",
        )
