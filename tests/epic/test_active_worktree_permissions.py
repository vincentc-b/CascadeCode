"""Epic team tools use the live checkout when trunk retains an old brief."""

from __future__ import annotations

from cascade.agent.planning_sandbox import collect_epic_readable_paths, materialize_scratch, teardown_scratch
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.epic.mint import list_children, mint_feature
from cascade.epic.scoped_docs import epic_read_doc
from cascade.workspace.integration_worktree import ensure_integration_worktree
from tests.support import add_doc, make_repo


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

    feature_id = mint_feature("New child", epic_id="epic_028", root=root)
    child = read_doc(feature_id, root=root)
    assert child.meta.provider == "codex"
    assert feature_id in read_doc("epic_028", root=worktree).meta.children
    assert feature_id not in read_doc("epic_028", root=root).meta.children
    assert [meta.id for meta in list_children(epic_id="epic_028", root=root)] == [feature_id]
