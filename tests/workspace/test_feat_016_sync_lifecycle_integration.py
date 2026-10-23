"""feat_016_001 integration contracts: sync updates and lifecycle merge failures (task_016_001_003)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.boss.merge import merge_feature_branch, merge_task_branch, promote_epic_to_trunk
from cascade.board.store import read_doc
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace.branch_synchronization import (
    inspect_branch_synchronization,
    update_integration_branch,
)
from cascade.workspace.doc_root import read_doc_resolved
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from tests.support import add_doc, approve_board_feature, commit_board, make_repo


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_task_runs()
    yield
    clear_task_runs()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _stacked_board(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok


def _commit_on_branch(repo: Path, branch: str, rel: str, content: str, message: str) -> None:
    subprocess.run(["git", "checkout", branch], cwd=repo, check=True, capture_output=True)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


def test_epic_clean_update_and_no_op_without_pointer_split(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    commit_board(root)
    epic_branch = integration_branch("epic", "epic_001")
    ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=epic_branch,
        base_ref="HEAD",
        trunk=root,
    )
    commit_board(root, message="integration registry")
    _commit_in_worktree(root, "trunk-only.txt", "trunk advance\n", "on main")

    epic_inspection = inspect_branch_synchronization("epic_001", root=root)
    assert epic_inspection.ok and epic_inspection.state is not None
    assert epic_inspection.state.behind > 0
    epic_update = update_integration_branch("epic_001", root=root)
    assert epic_update.ok and epic_update.no_op is False
    assert update_integration_branch("epic_001", root=root).no_op is True


def test_task_clean_update_and_no_op_retry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_in_worktree(feat_wt, "feature.txt", "feature\n", "feature work")

    task_inspection = inspect_branch_synchronization("task_001", root=root)
    assert task_inspection.ok and task_inspection.state is not None
    assert task_inspection.state.behind > 0
    assert update_integration_branch("task_001", root=root).ok
    assert update_integration_branch("task_001", root=root).no_op is True


def test_tracked_unstaged_reports_local_changes_without_mutation(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    rel = "tracked.txt"
    _commit_in_worktree(feat_wt, rel, "committed\n", "tracked")
    path = feat_wt / rel
    path.write_text("edited but not staged\n", encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason == "local_changes"
    result = update_integration_branch("feat_001", root=root)
    assert not result.ok and result.reason == "local_changes"
    assert path.read_text(encoding="utf-8") == before


def test_dirty_index_leaves_staged_content_untouched(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    dirty = feat_wt / "staged-only.txt"
    dirty.write_text("staged payload\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged-only.txt"], cwd=feat_wt, check=True, capture_output=True)
    cached = subprocess.run(
        ["git", "diff", "--cached", "--", "staged-only.txt"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout

    result = update_integration_branch("feat_001", root=root)
    assert not result.ok and result.reason == "dirty_index"
    after = subprocess.run(
        ["git", "diff", "--cached", "--", "staged-only.txt"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert after == cached


def test_inflight_turn_refuses_sync_and_task_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    run = create_task_worktree("task_001", root=root, parent_rev=None, skills=[])
    _commit_in_worktree(run.worktree, "task.txt", "task work\n", "task commit")

    monkeypatch.setattr(
        "cascade.workspace.branch_synchronization._graph_has_inflight_turn",
        lambda *_a, **_k: True,
    )

    assert update_integration_branch("feat_001", root=root).reason == "busy"
    merge = merge_task_branch("task_001", root=root)
    assert not merge.ok and merge.reason == "busy"
    assert not (feat_wt / "task.txt").exists()


def test_lifecycle_merge_failures_preserve_state_and_return_typed_reasons(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    run = create_task_worktree("task_001", root=root, parent_rev=None, skills=[])
    _commit_in_worktree(run.worktree, "deliver.txt", "task payload\n", "task commit")

    staged = feat_wt / "index-dirty.txt"
    staged.write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "index-dirty.txt"], cwd=feat_wt, check=True, capture_output=True)
    task_merge = merge_task_branch("task_001", root=root)
    assert not task_merge.ok and task_merge.reason == "dirty_index"
    assert not (feat_wt / "deliver.txt").exists()
    task = read_doc("task_001", root=root)
    assert task.meta.status == "active"

    subprocess.run(["git", "reset", "HEAD", "index-dirty.txt"], cwd=feat_wt, check=True, capture_output=True)
    _commit_in_worktree(feat_wt, "feature_unit.txt", "feature\n", "feature work")
    scratch = epic_wt / "local.txt"
    scratch.write_text("untracked\n", encoding="utf-8")
    feature_merge = merge_feature_branch("feat_001", root=root)
    assert not feature_merge.ok and feature_merge.reason == "local_changes"
    assert not (epic_wt / "feature_unit.txt").exists()
    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"

    rel = "collision.txt"
    _commit_on_branch(epic_wt, "epic/epic_001", rel, "epic side\n", "epic edit")
    _commit_in_worktree(root, rel, "trunk side\n", "trunk edit")
    promote = promote_epic_to_trunk("epic_001", root=root)
    assert not promote.ok and promote.reason == "branch_conflict"
    assert (root / rel).read_text(encoding="utf-8") == "trunk side\n"
    assert not (root / ".git" / "MERGE_HEAD").exists()


def test_promote_resolves_activation_pointer_add_add_only(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(
        root,
        id="epic_001",
        title="Live epic",
        tier="epic",
        status="ready_to_plan",
    )
    from cascade.board.parse import render_doc

    epic_doc = read_doc("epic_001", root=root)
    epic_doc.body += "\nLive body must land on trunk.\n"
    epic_doc.meta.path.write_text(render_doc(epic_doc), encoding="utf-8")
    commit_board(root, message="seed epic doc")

    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_in_worktree(epic_wt, "only-on-branch.txt", "branch-only\n", "branch work")

    promote = promote_epic_to_trunk("epic_001", root=root)
    assert promote.ok is True
    assert (root / "only-on-branch.txt").read_text(encoding="utf-8") == "branch-only\n"
    epic_on_trunk = read_doc_resolved("epic_001", root=root)
    assert "Live body must land on trunk." in epic_on_trunk.body
    assert "Live epic spec is on branch" not in epic_on_trunk.body
