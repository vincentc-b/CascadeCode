"""Feature tools must work when the spec lives on an integration worktree."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.store import pin_parent, read_doc
from cascade.epic.activation import activate_epic_on_worktree
from cascade.feature.scoped_docs import feature_read_doc, list_children
from cascade.feature.mint import mint_task
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.workspace.integration_worktree import (
    create_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from tests.support import add_doc, make_repo


def _commit_all(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "docs"],
        cwd=root,
        check=True,
        capture_output=True,
    )


def test_feature_read_and_mint_on_dispatched_worktree(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    _commit_all(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    assert feat_wt.is_dir()
    feature = read_doc("feat_001", root=root)
    assert str(feat_wt) in feature.meta.path.as_posix()

    pin_parent("feat_001", "epic_001", root=feat_wt)
    doc = feature_read_doc("feat_001", feature_id="feat_001", root=root)
    assert "Feature" in doc.meta.title

    task_id = mint_task("Slice one", feature_id="feat_001", root=root)
    assert list_children(feature_id="feat_001", root=root)
    task = read_doc(task_id, root=root)
    assert task.meta.parent == "feat_001"
    assert str(feat_wt) in task.meta.path.as_posix()
