"""Human merge_task_branch (task_040)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.paths import column_dir
from cascade.board.store import read_doc
from cascade.boss.merge import merge_task_branch
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _merge_test_isolation() -> None:
    clear_hooks()
    clear_task_runs()
    yield
    clear_hooks()
    clear_task_runs()


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


def _ensure_feature_line(root: Path, feature_id: str = "feat_001") -> Path:
    feat_branch = integration_branch("feature", feature_id)
    ensure_integration_worktree(
        "feature",
        feature_id,
        branch=feat_branch,
        base_ref="HEAD",
        trunk=root,
    )
    return integration_worktree_path("feature", feature_id, trunk=root)


def _board_with_active_task(tmp_path: Path, task_id: str = "task_040") -> tuple[Path, str]:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id=task_id,
        title="Merge me",
        tier="task",
        status="active",
        parent="feat_001",
    )
    _ensure_feature_line(root)
    return root, task_id


def test_happy_merge_moves_task_and_emits_events(tmp_path: Path) -> None:
    root, task_id = _board_with_active_task(tmp_path)
    feat_branch = integration_branch("feature", "feat_001")
    run = create_task_worktree(
        task_id, root=root, parent_rev=None, skills=[], base_ref=feat_branch
    )
    _commit_in_worktree(run.worktree, "feature.txt", "task work\n", "task commit")

    result = merge_task_branch(task_id, root=root)

    assert result.ok is True
    assert result.reason is None
    assert result.branch == f"task/{task_id}"
    assert result.target_branch == "feat/feat_001"
    assert result.merge_sha

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    merged_file = feat_wt / "feature.txt"
    assert merged_file.is_file()
    assert "task work" in merged_file.read_text(encoding="utf-8")

    task = read_doc(task_id, root=root)
    assert task.meta.status == "completed"
    assert task.meta.path.parent.name == "3_completed"

    feature_events, _ = read_events("feat_001", 0, root=root)
    merged = [event for event in feature_events if event.type == "TaskMerged"]
    assert len(merged) == 1
    payload = merged[0].payload
    assert payload == {
        "task_id": task_id,
        "branch": f"task/{task_id}",
        "merge_sha": result.merge_sha,
        "target_branch": "feat/feat_001",
    }

    war_events, _ = read_events("war_room", 0, root=root)
    toasts = [event for event in war_events if event.type == "Toast"]
    assert len(toasts) == 1
    assert toasts[0].payload["kind"] == "task_merged"
    assert toasts[0].payload["id"] == task_id
    mapped = events_to_toasts(toasts)
    assert mapped[0]["kind"] == "task_merged"
    assert mapped[0]["link"] == f"/api/doc/{task_id}"


def test_missing_branch_returns_error(tmp_path: Path) -> None:
    root, task_id = _board_with_active_task(tmp_path)

    result = merge_task_branch(task_id, root=root)

    assert result.ok is False
    assert result.reason == "branch_missing"
    assert result.branch == f"task/{task_id}"
    task = read_doc(task_id, root=root)
    assert task.meta.path.parent.name == "2_active"
    feature_events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskMerged" for event in feature_events)


def test_merge_conflict_leaves_task_active(tmp_path: Path) -> None:
    root, task_id = _board_with_active_task(tmp_path)
    feat_branch = integration_branch("feature", "feat_001")
    feat_wt = _ensure_feature_line(root)
    run = create_task_worktree(
        task_id, root=root, parent_rev=None, skills=[], base_ref=feat_branch
    )
    rel = "conflict.txt"
    _commit_in_worktree(run.worktree, rel, "from task branch\n", "task side")

    path = feat_wt / rel
    path.write_text("from feature line\n", encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=feat_wt, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feature line change"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
    )

    result = merge_task_branch(task_id, root=root)

    assert result.ok is False
    assert result.reason == "merge_conflict"
    task = read_doc(task_id, root=root)
    assert task.meta.status == "active"
    assert task.meta.path == root / column_dir("task", "active") / task.meta.path.name
    feature_events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskMerged" for event in feature_events)

    merge_head = subprocess.run(
        ["git", "rev-parse", "--git-path", "MERGE_HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert not Path(merge_head).exists()
    unmerged = subprocess.run(
        ["git", "diff", "--name-only", "--diff-filter=U"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    )
    assert unmerged.stdout.strip() == ""


def test_wrong_branch_on_root_refuses_merge(tmp_path: Path) -> None:
    root, task_id = _board_with_active_task(tmp_path)
    feat_branch = integration_branch("feature", "feat_001")
    run = create_task_worktree(
        task_id, root=root, parent_rev=None, skills=[], base_ref=feat_branch
    )
    _commit_in_worktree(run.worktree, "feature.txt", "task work\n", "task commit")

    subprocess.run(
        ["git", "checkout", "-b", "experiment"],
        cwd=root,
        check=True,
        capture_output=True,
    )

    pre = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = merge_task_branch(task_id, root=root)

    assert result.ok is False
    assert result.reason == "wrong_branch"
    task = read_doc(task_id, root=root)
    assert task.meta.path.parent.name == "2_active"
    feature_events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskMerged" for event in feature_events)
    post = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert post == pre


def test_move_doc_failure_rolls_back_merge(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, task_id = _board_with_active_task(tmp_path)
    feat_branch = integration_branch("feature", "feat_001")
    feat_wt = _ensure_feature_line(root)
    run = create_task_worktree(
        task_id, root=root, parent_rev=None, skills=[], base_ref=feat_branch
    )
    _commit_in_worktree(run.worktree, "feature.txt", "task work\n", "task commit")

    pre_merge = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    def boom(*args: object, **kwargs: object) -> None:
        raise RuntimeError("move_doc failed")

    monkeypatch.setattr("cascade.boss.merge.move_doc", boom)

    result = merge_task_branch(task_id, root=root)

    assert result.ok is False
    assert result.reason == "post_merge_failed"
    task = read_doc(task_id, root=root)
    assert task.meta.path.parent.name == "2_active"
    post = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert post == pre_merge
    feature_events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskMerged" for event in feature_events)


def test_task_not_found_does_not_move_doc(tmp_path: Path) -> None:
    root, _ = _board_with_active_task(tmp_path)

    result = merge_task_branch("task_999", root=root)

    assert result.ok is False
    assert result.reason == "task_not_found"


def test_wrong_tier_does_not_move_doc(tmp_path: Path) -> None:
    root, task_id = _board_with_active_task(tmp_path)

    result = merge_task_branch("feat_001", root=root)

    assert result.ok is False
    assert result.reason == "wrong_tier"
    feature = read_doc("feat_001", root=root)
    assert feature.meta.path.parent.name == "2_active"


def test_backlog_task_not_mergeable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_041",
        title="Backlog task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )

    result = merge_task_branch("task_041", root=root)

    assert result.ok is False
    assert result.reason == "wrong_column"
    task = read_doc("task_041", root=root)
    assert task.meta.path.parent.name == "1_backlog"


def test_blocked_task_not_mergeable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_042",
        title="Blocked task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )

    result = merge_task_branch("task_042", root=root)

    assert result.ok is False
    assert result.reason == "not_mergeable"
    task = read_doc("task_042", root=root)
    assert task.meta.path.parent.name == "2_active"


def test_not_a_git_repo_does_not_move_doc(tmp_path: Path) -> None:
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
    add_doc(
        root,
        id="task_043",
        title="No git",
        tier="task",
        status="active",
        parent="feat_001",
    )

    result = merge_task_branch("task_043", root=root)

    assert result.ok is False
    assert result.reason == "not_a_git_repo"
    task = read_doc("task_043", root=root)
    assert task.meta.path.parent.name == "2_active"


def test_missing_parent_does_not_move_doc(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    task_path = root / column_dir("task", "active") / "task_044_orphan-task.md"
    task_path.parent.mkdir(parents=True, exist_ok=True)
    task_path.write_text(
        """---
id: task_044
title: Orphan task
tier: task
status: active
parent: null
children: []
depends_on: []
owners: [tester]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# Orphan task

## Parent Feature

None.

## Depends on

None.

## Acceptance criteria

N/A.

## Files likely touched

- cascade/

## Implementation notes

Orphan for merge test.

## Skills

_(none)_

## Test plan

pytest.

## Out of scope

UI.
""",
        encoding="utf-8",
    )

    result = merge_task_branch("task_044", root=root)

    assert result.ok is False
    assert result.reason == "missing_parent"
    task = read_doc("task_044", root=root)
    assert task.meta.path.parent.name == "2_active"
