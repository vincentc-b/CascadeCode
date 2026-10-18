"""Epic comment tools (feat_005 / feat_006)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import cascade.epic.amendments as epic_amendments_mod
import cascade.epic.stubs as epic_stubs
from cascade.comments.store import comment, read_comments
from cascade.epic.registry import clear_epic_tools, epic_tools
from cascade.epic.wiring import load_epic_tools
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _reload_stub_tools() -> None:
    clear_epic_tools()
    importlib.reload(epic_stubs)
    importlib.reload(epic_amendments_mod)
    yield
    clear_epic_tools()


def test_epic_reply_and_resolve_use_store(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    root_id = comment("epic_001", "Intent", "question", author="human", root=root)
    epic_stubs.reply_comment(root_id, "answer", epic_id="epic_001", root=root)
    rows = read_comments("epic_001", root=root)
    assert len(rows) == 2
    assert rows[1].parent == root_id
    epic_stubs.resolve_comment(root_id, epic_id="epic_001", root=root)
    rows = read_comments("epic_001", root=root)
    assert rows[0].state == "resolved"


def test_stubs_register_on_import() -> None:
    tools = epic_tools()
    assert tools["reply_comment"] is epic_stubs.reply_comment
    assert tools["resolve_comment"] is epic_stubs.resolve_comment
    assert tools["resolve_amendment"] is epic_amendments_mod.resolve_amendment


def test_wiring_loads_real_resolve_amendment() -> None:
    clear_epic_tools()
    load_epic_tools()
    tools = epic_tools()
    assert tools["resolve_amendment"] is epic_amendments_mod.resolve_amendment
