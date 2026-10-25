"""Cancellation cleanup service integration coverage."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.cancellation import cancel_work_item
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace import integration_worktree as worktrees
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from tests.support import add_doc, approve_board_feature, make_repo


def _branch_exists(root: Path, branch: str) -> bool:
    return (
        subprocess.run(
            ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
            cwd=root,
            capture_output=True,
        ).returncode
        == 0
    )


def _active_task(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok


def test_service_removes_only_owned_task_artifacts(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _active_task(root)
    task_path = integration_worktree_path("task", "task_001", trunk=root)
    feature_path = integration_worktree_path("feature", "feat_001", trunk=root)
    unrelated_branch = "task/task_999"
    subprocess.run(["git", "branch", unrelated_branch], cwd=root, check=True)

    result = cancel_work_item("task_001", "superseded", root=root)

    assert result.complete
    assert not task_path.exists()
    assert not _branch_exists(root, integration_branch("task", "task_001"))
    assert get_integration_worktree(root, "task", "task_001") is None
    assert root.is_dir()
    assert feature_path.is_dir()
    assert _branch_exists(root, "main")
    assert _branch_exists(root, integration_branch("feature", "feat_001"))
    assert _branch_exists(root, unrelated_branch)
    assert read_doc("task_001", root=root).meta.status == "cancelled"


def test_dirty_owned_work_is_refused_until_discard_is_confirmed(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _active_task(root)
    task_path = integration_worktree_path("task", "task_001", trunk=root)
    user_file = task_path / "user-work.txt"
    user_file.write_text("do not lose this\n", encoding="utf-8")

    refused = cancel_work_item("task_001", "superseded", root=root)

    assert not refused.complete
    assert refused.cleanup_step == "remove_worktree"
    assert refused.cleanup_error is not None
    assert str(task_path) in refused.cleanup_error
    assert "discard_uncommitted=True" in refused.cleanup_error
    assert user_file.read_text(encoding="utf-8") == "do not lose this\n"
    stored = read_doc("task_001", root=root)
    assert stored.meta.status == "cancelling"
    assert stored.meta.cancellation_step == "remove_worktree"
    assert stored.meta.cancellation_error == refused.cleanup_error

    confirmed = cancel_work_item(
        "task_001",
        "ignored on retry",
        root=root,
        discard_uncommitted=True,
    )

    assert confirmed.complete
    assert confirmed.changed is False
    assert confirmed.reason == "superseded"
    assert not task_path.exists()
    assert not _branch_exists(root, integration_branch("task", "task_001"))


def test_partial_branch_failure_is_actionable_and_retry_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _active_task(root)
    task_path = integration_worktree_path("task", "task_001", trunk=root)
    task_branch = integration_branch("task", "task_001")
    real_git = worktrees._git
    remove_calls = 0
    fail_branch_once = True

    def flaky_git(cwd: Path, *args: str, **kwargs: object):
        nonlocal remove_calls, fail_branch_once
        if args[:2] == ("worktree", "remove"):
            remove_calls += 1
        if args[:2] == ("branch", "-D") and args[2:] == (task_branch,) and fail_branch_once:
            fail_branch_once = False
            return subprocess.CompletedProcess(
                ["git", *args],
                1,
                "",
                f"cannot delete exact owned branch {task_branch}; retry cancellation",
            )
        return real_git(cwd, *args, **kwargs)

    monkeypatch.setattr(worktrees, "_git", flaky_git)

    partial = cancel_work_item("task_001", "superseded", root=root)

    assert not partial.complete
    assert partial.cleanup_step == "delete_branch"
    assert partial.cleanup_error is not None and task_branch in partial.cleanup_error
    assert not task_path.exists()
    assert _branch_exists(root, task_branch)
    stored = read_doc("task_001", root=root)
    assert stored.meta.status == "cancelling"
    assert stored.meta.cancellation_step == "delete_branch"
    assert stored.meta.cancellation_error == partial.cleanup_error

    retried = cancel_work_item("task_001", "ignored on retry", root=root)
    repeated = cancel_work_item("task_001", "ignored after completion", root=root)

    assert retried.complete and retried.changed is False
    assert repeated.complete and repeated.changed is False
    assert remove_calls == 1
    assert not task_path.exists()
    assert not _branch_exists(root, task_branch)
    assert get_integration_worktree(root, "task", "task_001") is None
