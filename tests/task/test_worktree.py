"""Local task branch and git worktree (task_031)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.task.worktree import (
    clear_task_runs,
    create_task_worktree,
    get_task_run,
    install_task_worktree_teardown_hook,
    remove_task_worktree,
    worktree_path,
)
from cascade.watchdog.hooks import clear_hooks
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _worktree_test_isolation() -> None:
    clear_hooks()
    clear_task_runs()
    yield
    clear_hooks()
    clear_task_runs()


def _initial_commit(root: Path) -> str:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "README.md"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sha.stdout.strip()


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def test_create_task_worktree_branch_and_path(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    parent_rev = _initial_commit(root)

    run = create_task_worktree(
        "task_031",
        root=root,
        parent_rev=parent_rev,
        skills=["skills/a.md"],
    )

    assert run.task_id == "task_031"
    assert run.branch == "task/task_031"
    assert run.worktree == worktree_path("task_031", root=root).resolve()
    assert run.parent_rev == parent_rev
    assert run.skills == ["skills/a.md"]
    assert run.state == "booting"
    assert _branch_exists(root, "task/task_031")
    assert get_task_run("task_031") is run


def test_worktree_is_separate_from_main_checkout(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    run = create_task_worktree(
        "task_031",
        root=root,
        parent_rev=None,
        skills=[],
    )

    assert run.worktree.resolve() != root.resolve()
    assert run.worktree.is_dir()
    head_ref = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=run.worktree,
        check=True,
        capture_output=True,
        text=True,
    )
    assert head_ref.stdout.strip() == "task/task_031"


def test_remove_task_worktree_keeps_branch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    run = create_task_worktree(
        "task_031",
        root=root,
        parent_rev="abc123",
        skills=[],
    )
    wt = run.worktree
    remove_task_worktree(run, root=root)

    assert not wt.exists()
    assert _branch_exists(root, "task/task_031")
    assert get_task_run("task_031") is None


def test_teardown_hook_removes_worktree_not_branch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    run = create_task_worktree(
        "task_031",
        root=root,
        parent_rev=None,
        skills=[],
    )
    wt = run.worktree
    install_task_worktree_teardown_hook(root)

    from cascade.watchdog.hooks import _teardown

    hooks = [fn for fn in _teardown["task"] if fn.__name__ == "_teardown_task_worktree"]
    assert len(hooks) == 1
    hooks[0]("task_031")

    assert not wt.exists()
    assert _branch_exists(root, "task/task_031")
    assert get_task_run("task_031") is None


def test_teardown_hook_preserves_failed_worktree_for_retry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    run = create_task_worktree(
        "task_031", root=root, parent_rev=None, skills=[]
    )
    run.state = "failed"
    install_task_worktree_teardown_hook(root)

    from cascade.watchdog.hooks import _teardown

    hooks = [fn for fn in _teardown["task"] if fn.__name__ == "_teardown_task_worktree"]
    hooks[0]("task_031")

    assert run.worktree.is_dir()
    assert get_task_run("task_031") is run


def test_no_git_push(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import cascade.task.worktree as worktree_mod

    root = make_repo(tmp_path)
    _initial_commit(root)

    pushes: list[list[str]] = []
    real_run = subprocess.run

    def guarded_run(args: list[str], *a: object, **kw: object) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "git" and "push" in args:
            pushes.append(list(args))
        return real_run(args, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(worktree_mod.subprocess, "run", guarded_run)

    run = create_task_worktree(
        "task_031",
        root=root,
        parent_rev=None,
        skills=[],
    )
    remove_task_worktree(run, root=root)

    assert pushes == []


def test_install_teardown_hook_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    install_task_worktree_teardown_hook(root)
    install_task_worktree_teardown_hook(root)

    from cascade.watchdog.hooks import _teardown

    named = [fn for fn in _teardown["task"] if fn.__name__ == "_teardown_task_worktree"]
    assert len(named) == 1
