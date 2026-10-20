"""Work doc JSON coercion for MCP tools."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.board.serde import work_doc_from_dict
from cascade.board.store import read_doc
from cascade.epic.wiring import load_epic_tools
from cascade.epic.activation import activate_epic_on_worktree
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    get_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from tests.support import add_doc, make_repo


def test_work_doc_from_dict_merges_canonical_path_from_read_doc(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    canonical = read_doc("epic_001", root=root)

    payload = {
        "meta": {"id": "epic_001", "path": "/wrong/scratch/plan.md"},
        "body": "# Updated\n\nNew body\n",
        "sha": "deadbeef",
    }
    doc = work_doc_from_dict(payload, root=root)
    assert doc.meta.path.resolve() == canonical.meta.path.resolve()
    assert doc.body == "# Updated\n\nNew body\n"


def test_dispatch_write_doc_accepts_plain_dict(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    branch = integration_branch("epic", "epic_001")
    ensure_integration_worktree(
        "epic", "epic_001", branch=branch, base_ref="HEAD", trunk=root
    )
    entry = get_integration_worktree(root, "epic", "epic_001")
    assert entry is not None
    activate_epic_on_worktree("epic_001", trunk=root, epic_wt=entry)
    wt = integration_worktree_path("epic", "epic_001", trunk=root)
    live_path = read_doc("epic_001", root=root).meta.path

    load_epic_tools()
    base = read_doc("epic_001", root=root)
    assert live_path.is_relative_to(wt)
    new_body = base.body + "\n\n## Agent edit\n\nDone.\n"
    collector = ToolEffectCollector()
    dispatch_planning_tool(
        "epic",
        "write_doc",
        {
            "doc": {
                "meta": {"id": "epic_001"},
                "body": new_body,
                "sha": base.sha,
            }
        },
        scope_id="epic_001",
        repo_root=root,
        collector=collector,
    )
    assert "## Agent edit" in live_path.read_text(encoding="utf-8")
    assert collector.effects and collector.effects[0].tool == "write_doc"
