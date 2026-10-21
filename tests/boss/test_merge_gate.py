"""merge_feature_branch refuses when open blocking review threads apply (feat_019)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.boss.merge import merge_feature_branch
from cascade.comments.store import comment
from cascade.task.worktree import clear_task_runs
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.workspace.integration_worktree import integration_worktree_path
from tests.support import add_doc, make_repo, approve_board_feature


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


def test_merge_feature_branch_refused_open_blocking_comment(tmp_path: Path) -> None:
    clear_task_runs()
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok

    feature_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_in_worktree(feature_wt, "feature_code.txt", "feature unit\n", "feature work")

    cmt_id = comment(
        "feat_001",
        "Scope",
        "Block feature merge",
        blocking=True,
        author="human",
        root=root,
    )

    result = merge_feature_branch("feat_001", root=root)
    assert result.ok is False
    assert result.reason is not None
    assert cmt_id in result.reason
    assert "/plan/feat_001#plan-comments" in result.reason
