"""Epic team tools use the live checkout when trunk retains an old brief."""

from __future__ import annotations

import asyncio

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.agent.planning_sandbox import collect_epic_readable_paths, materialize_scratch, teardown_scratch
from cascade.agent.planning_turn import run_epic_planning_turn
from cascade.agent.types import RoleResult, RoleTurn
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.epic.mint import list_children, mint_feature
from cascade.epic.scoped_docs import epic_read_doc
from cascade.workspace.integration_worktree import ensure_integration_worktree
from tests.support import add_doc, make_repo


def test_epic_team_turn_uses_live_integration_worktree(tmp_path, monkeypatch):
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_028", title="Epic", tier="epic", status="backlog")
    worktree = ensure_integration_worktree(
        "epic", "epic_028", branch="epic/epic_028", base_ref="main", trunk=root
    ).path
    move_doc("epic_028", "active", root=worktree)
    seen: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        seen.append(turn)
        (turn.cwd / "owned-team-edit.txt").write_text("editable\n", encoding="utf-8")
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "composer-2.5",
            "inspect",
            provider="cursor",
            epic_id="epic_028",
            root=root,
        )
    )

    assert seen[0].cwd == worktree.resolve()
    assert (worktree / "owned-team-edit.txt").is_file()
    assert not (root / "owned-team-edit.txt").exists()


def test_epic_team_reads_and_mints_from_live_worktree_with_stale_trunk_copy(tmp_path):
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_028", title="Epic", tier="epic", status="backlog")
    worktree = ensure_integration_worktree(
        "epic", "epic_028", branch="epic/epic_028", base_ref="main", trunk=root
    ).path
    move_doc("epic_028", "active", root=worktree)
    live = read_doc("epic_028", root=worktree)
    live.meta.provider = "codex"
    live.meta.models = {"epic_manager": "gpt-6.1-sol", "epic_architect": "gpt-6.1-sol"}
    live.body += "\nLive planning revision.\n"
    write_doc(live, root=worktree)

    assert read_doc("epic_028", root=root).meta.status == "backlog"
    active = epic_read_doc("epic_028", epic_id="epic_028", root=root)
    assert active.meta.status == "active"
    assert "Live planning revision." in active.body
    assert list_children(epic_id="epic_028", root=root) == []

    paths = collect_epic_readable_paths("epic_028", root=root)
    assert paths[0] == active.meta.path
    scratch = materialize_scratch(root, paths, tier="epic")
    try:
        assert "Live planning revision." in (scratch / "plan.md").read_text()
    finally:
        teardown_scratch(scratch)

    dispatch_planning_tool(
        "epic", "write_doc",
        {"doc": {"meta": {"id": "epic_028"}, "body": active.body + "\nTool edit.\n", "sha": active.sha}},
        scope_id="epic_028", repo_root=root, collector=ToolEffectCollector(),
    )
    assert "Tool edit." in read_doc("epic_028", root=worktree).body
    assert "Tool edit." not in read_doc("epic_028", root=root).body

    feature_id = mint_feature("New child", epic_id="epic_028", root=root)
    child = read_doc(feature_id, root=root)
    assert child.meta.provider == "codex"
    assert feature_id in read_doc("epic_028", root=worktree).meta.children
    assert feature_id not in read_doc("epic_028", root=root).meta.children
    assert [meta.id for meta in list_children(epic_id="epic_028", root=root)] == [feature_id]
