"""Feature Team comment tools."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import cascade.feature.comments_tool as comments_tool
from cascade.comments.store import comment
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


def test_feature_reply_own_thread(board: Path) -> None:
    root_id = comment("feat_001", "Scope", "human note", author="human", root=board)
    reply_id = comments_tool.reply_comment(
        root_id,
        "ack",
        feature_id="feat_001",
        root=board,
    )
    assert reply_id == "cmt_002"


def test_feature_tools_exclude_resolve_comment() -> None:
    from cascade.feature.registry import feature_tools

    assert "resolve_comment" not in feature_tools()
