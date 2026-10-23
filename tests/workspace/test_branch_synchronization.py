"""Branch synchronization domain service (task_016_001_001)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cascade.stacked_dispatch import read_feature_dispatch_selection
from cascade.task.worktree import clear_task_runs
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.workspace.branch_synchronization import (
    inspect_branch_synchronization,
    update_integration_branch,
)
from cascade.workspace.integration_worktree import integration_branch, integration_worktree_path
from tests.support import add_doc, approve_board_feature, make_repo


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


def test_feature_update_merges_epic_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_on_branch(epic_wt, "epic/epic_001", "epic.txt", "epic work\n", "on epic")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.ok
    assert inspection.state is not None
    assert inspection.state.behind > 0
    assert inspection.update_blocked_reason is None

    result = update_integration_branch("feat_001", root=root)
    assert result.ok
    assert result.reason is None
    assert result.no_op is False

    follow_up = inspect_branch_synchronization("feat_001", root=root)
    assert follow_up.ok and follow_up.state is not None
    assert follow_up.state.behind == 0


def test_already_current_is_no_op(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    result = update_integration_branch("feat_001", root=root)
    assert result.ok
    assert result.no_op is True


def _seed_predecessor_review(root: Path, feature_id: str) -> None:
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, object] = {}
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
    state[feature_id] = {
        "url": f"https://github.example/o/r/pull/{feature_id}",
        "number": "1",
        "forge": "github",
        "source_branch": integration_branch("feature", feature_id),
        "target_branch": integration_branch("epic", "epic_001"),
        "draft": False,
        "closed": False,
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_persisted_feature_base_survives_room_settings_change(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature A", tier="feature", parent="epic_001")
    assert activate_epic("epic_001", "human", root=root).ok
    write_stacked_pr_enabled("epic_001", True, root=root)
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    from cascade.board.store import move_doc

    move_doc("feat_001", "completed", root=root)
    add_doc(
        root,
        id="feat_002",
        title="Feature B",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_predecessor_review(root, "feat_001")
    approve_board_feature(root, "feat_002")
    assert dispatch_feature("feat_002", "human", root=root).ok

    write_stacked_pr_enabled("epic_001", False, root=root)

    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.base_branch == integration_branch("feature", "feat_001")

    inspection = inspect_branch_synchronization("feat_002", root=root)
    assert inspection.ok and inspection.state is not None
    assert inspection.state.base_branch == integration_branch("feature", "feat_001")


def test_dirty_index_blocks_update(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    (feat_wt / "dirty.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "dirty.txt"], cwd=feat_wt, check=True, capture_output=True)

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason == "dirty_index"
    result = update_integration_branch("feat_001", root=root)
    assert not result.ok and result.reason == "dirty_index"


def test_untracked_reports_local_changes(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    (feat_wt / "scratch.txt").write_text("untracked\n", encoding="utf-8")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason == "local_changes"


def test_conflict_aborts_and_restores_head(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    rel = "conflict.txt"
    _commit_on_branch(epic_wt, "epic/epic_001", rel, "base side\n", "epic change")
    _commit_on_branch(feat_wt, "feat/feat_001", rel, "work side\n", "feature change")

    pre = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = update_integration_branch("feat_001", root=root)
    assert not result.ok
    assert result.reason == "branch_conflict"
    assert result.conflict_paths == (rel,)

    post = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert post == pre
    merge_head = subprocess.run(
        ["git", "rev-parse", "-q", "MERGE_HEAD"],
        cwd=feat_wt,
        capture_output=True,
    )
    assert merge_head.returncode != 0


def test_task_update_uses_parent_feature_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_on_branch(feat_wt, "feat/feat_001", "feature.txt", "feature\n", "feature work")

    inspection = inspect_branch_synchronization("task_001", root=root)
    assert inspection.ok and inspection.state is not None
    assert inspection.state.base_branch == integration_branch("feature", "feat_001")
    assert inspection.state.behind > 0

    assert update_integration_branch("task_001", root=root).ok
