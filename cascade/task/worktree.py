"""Local task branch and isolated git worktree (no push, no board commits)."""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.errors import GitError
from cascade.board.gitutil import head_sha
from cascade.board.paths import parse_work_id
from cascade.watchdog.hooks import register_teardown_hook

TaskRunState = Literal[
    "booting",
    "coding",
    "testing",
    "awaiting_merge",
    "failed",
    "merged",
]

_root: Path | None = None
_runs: dict[str, TaskRun] = {}


@dataclass
class TaskRun:
    task_id: str
    branch: str
    worktree: Path
    base_sha: str
    parent_rev: str | None
    skills: list[str]
    state: TaskRunState = "booting"


def get_task_run(task_id: str) -> TaskRun | None:
    """Return the active run for `task_id`, if any."""

    return _runs.get(task_id)


def clear_task_runs() -> None:
    """Reset active-run registry (tests only)."""

    global _root
    _runs.clear()
    _root = None


def create_task_worktree(
    task_id: str,
    *,
    root: Path,
    parent_rev: str | None,
    skills: list[str],
    base_ref: str | None = None,
) -> TaskRun:
    """Create branch ``task/{task_id}`` from ``base_ref`` (or trunk HEAD) and a worktree."""

    from cascade.workspace.integration_worktree import (
        create_integration_worktree,
        get_integration_worktree,
        integration_branch,
    )

    _validate_task_id(task_id)
    root = root.resolve()
    if head_sha(root) is None:
        raise GitError("cannot create worktree: repo has no commits")

    branch = integration_branch("task", task_id)
    cut_from = base_ref if base_ref is not None else "HEAD"
    existing = get_integration_worktree(root, "task", task_id)
    if existing is not None and existing.path.is_dir():
        worktree = existing.path
        _fast_forward_retry_branch(worktree, branch, cut_from)
    else:
        _fast_forward_detached_retry_branch(root, branch, cut_from)
        record = create_integration_worktree(
            "task",
            task_id,
            branch=branch,
            base_ref=cut_from,
            trunk=root,
        )
        worktree = record.path

    # A failed run keeps its Task branch and worktree so the Feature Team can
    # inspect or retry it.  That branch may already contain a valid deliverable
    # commit.  Keep the comparison base at the common Feature/Task ancestor;
    # using the retry branch's current HEAD would make the existing commit
    # disappear from ``has_deliverable_commit`` and cause an endless
    # ``no_task_changes`` loop.
    current_sha = _git(worktree, "rev-parse", "HEAD").stdout.strip()
    merge_base = _git(
        worktree,
        "merge-base",
        "HEAD",
        cut_from,
        check=False,
    )
    base_sha = merge_base.stdout.strip() if merge_base.returncode == 0 else current_sha

    run = TaskRun(
        task_id=task_id,
        branch=branch,
        worktree=worktree.resolve(),
        base_sha=base_sha,
        parent_rev=parent_rev,
        skills=list(skills),
        state="booting",
    )
    _runs[task_id] = run
    return run


def _fast_forward_retry_branch(worktree: Path, branch: str, base_ref: str) -> None:
    """Advance a clean, unstarted retry branch to its current Feature tip."""

    if _git(worktree, "status", "--porcelain").stdout.strip():
        return
    ancestor = _git(worktree, "merge-base", "--is-ancestor", branch, base_ref, check=False)
    if ancestor.returncode == 0:
        _git(worktree, "merge", "--ff-only", base_ref)


def _fast_forward_detached_retry_branch(root: Path, branch: str, base_ref: str) -> None:
    """Advance a retry branch whose worktree was removed after failed boot."""

    if not _branch_exists(root, branch):
        return
    ancestor = _git(root, "merge-base", "--is-ancestor", branch, base_ref, check=False)
    if ancestor.returncode == 0:
        _git(root, "branch", "-f", branch, base_ref)


def remove_task_worktree(task_run: TaskRun, *, root: Path) -> None:
    """Remove the worktree checkout; keep the local branch for human merge."""

    root = root.resolve()
    wt = task_run.worktree.resolve()
    _git(root, "worktree", "remove", "--force", str(wt))
    _runs.pop(task_run.task_id, None)


def worktree_path(task_id: str, *, root: Path) -> Path:
    _validate_task_id(task_id)
    return root / ".cascade" / "worktrees" / f"task_{task_id}"


def install_task_worktree_teardown_hook(root: Path) -> None:
    """Register task-tier teardown to drop the active run's worktree."""

    global _root
    _root = Path(root).resolve()
    from cascade.watchdog.hooks import _teardown

    if not any(fn is _teardown_task_worktree for fn in _teardown["task"]):
        register_teardown_hook("task", _teardown_task_worktree)


def _teardown_task_worktree(work_id: str) -> None:
    if _root is None:
        return
    run = _runs.get(work_id)
    if run is None:
        return
    # Keep failed work available to the supervisor for diagnosis or retry.
    # Successful merge teardown still removes the checkout.
    if run.state == "failed":
        return
    remove_task_worktree(run, root=_root)


def _remove_stale_worktree(task_id: str, *, root: Path, worktree: Path) -> None:
    """Drop stale disk paths and git worktree registrations before re-adding."""

    wt = worktree.resolve()
    listed = _git(root, "worktree", "list", "--porcelain", check=False)
    blocks = (listed.stdout or "").split("\n\n")
    for block in blocks:
        if not block.strip():
            continue
        path_line = next(
            (line[7:] for line in block.splitlines() if line.startswith("worktree ")),
            None,
        )
        if path_line is None:
            continue
        registered = Path(path_line).resolve()
        if registered != wt:
            continue
        _git(root, "worktree", "remove", "--force", str(registered), check=False)
        break

    if wt.exists():
        shutil.rmtree(wt, ignore_errors=True)
    _git(root, "worktree", "prune", check=False)


def _branch_exists(root: Path, branch: str) -> bool:
    result = _git(root, "show-ref", "--verify", f"refs/heads/{branch}", check=False)
    return result.returncode == 0


def _validate_task_id(task_id: str) -> None:
    if "/" in task_id or ".." in task_id:
        raise ValueError(f"invalid task id for worktree: {task_id!r}")
    tier, _ = parse_work_id(task_id)
    if tier != "task":
        raise ValueError(f"worktree id must be a task work id: {task_id!r}")


def _env(root: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    env["GIT_DIR"] = str((root / ".git").resolve())
    env["GIT_WORK_TREE"] = str(root.resolve())
    return env


def _git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if args and args[0] == "push":
        raise GitError("git push is not allowed from task worktree module")
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=_env(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} failed")
    return result
