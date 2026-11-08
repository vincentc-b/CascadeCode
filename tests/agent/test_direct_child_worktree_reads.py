"""Parent tools can inspect canonical child plans across owned checkouts."""

import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.epic.guard import tool_guard as epic_guard
from cascade.feature.guard import tool_guard as feature_guard
from cascade.workspace.integration_worktree import ensure_integration_worktree
from tests.support import add_doc, make_repo


@pytest.mark.parametrize("tier,roles,owner,child,foreign", [
    ("epic", ("epic_manager", "epic_architect"), "epic_001", "feat_001", "feat_002"),
    ("feature", ("feature_lead", "feature_architect"), "feat_001", "task_001", "task_002"),
])
def test_direct_child_read_tracks_registered_checkout_and_preserves_denials(
    tmp_path, tier, roles, owner, child, foreign,
):
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Mine", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Foreign", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Mine", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Foreign", tier="feature", parent="epic_002")
    add_doc(root, id="task_001", title="Mine", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Foreign", tier="task", parent="feat_002")
    owner_entry = ensure_integration_worktree(
        tier, owner, branch=f"{'epic' if tier == 'epic' else 'feat'}/{owner}",
        base_ref="main", trunk=root,
    )
    if tier == "feature":
        move_doc(owner, "active", root=owner_entry.path)
    child_tier = "feature" if tier == "epic" else "task"
    child_entry = ensure_integration_worktree(
        child_tier, child, branch=f"{'feat' if tier == 'epic' else 'task'}/{child}",
        base_ref="main", trunk=root,
    )
    move_doc(child, "active", root=child_entry.path)
    doc = read_doc(child, root=child_entry.path)
    doc.body += "\nCanonical child-only acceptance detail.\n"
    write_doc(doc, root=child_entry.path)
    guard = epic_guard if tier == "epic" else feature_guard
    kwargs = {f"{tier}_id": owner, "root": root}
    assert guard(doc.meta.path, "read", **kwargs)
    assert not guard(doc.meta.path, "write", **kwargs)

    for role in roles:
        def call(name, arguments):
            return dispatch_planning_tool(
                tier, name, arguments, scope_id=owner, repo_root=root,
                role=role, collector=ToolEffectCollector(),
            )

        current = call("read_doc", {"work_id": child})
        assert "Canonical child-only acceptance detail." in current.body
        assert current.meta.status == "active"
        with pytest.raises(PermissionError):
            call("read_doc", {"work_id": foreign})
        with pytest.raises(PermissionError):
            call("write_doc", {"doc": {"meta": {"id": child}, "body": "Unauthorized write"}})
        # Grandchildren and unrelated parent bodies remain outside the scope.
        denied = "task_001" if tier == "epic" else "epic_002"
        with pytest.raises(PermissionError):
            call("read_doc", {"work_id": denied})

    alias = doc.meta.path.with_name(f"{child}_alias.md")
    alias.symlink_to(doc.meta.path)
    assert not guard(alias, "read", **kwargs)
    # A noncanonical checkout copy is not granted the new cross-worktree access.
    sibling = ensure_integration_worktree(
        child_tier, foreign,
        branch=f"{'feat' if tier == 'epic' else 'task'}/{foreign}",
        base_ref="main", trunk=root,
    )
    shadow = sibling.path / "docs" / ("features" if tier == "epic" else "tasks") / "1_backlog" / doc.meta.path.name
    assert shadow.is_file()
    assert not guard(shadow, "read", **kwargs)
