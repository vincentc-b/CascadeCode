"""Task-scoped test runner and local commits (no push, no board lifecycle)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.board.errors import GitError
from cascade.task.guard import TaskToolDenied, task_tool_guard
from cascade.task.registry import register_task_tool
from cascade.task.worktree import TaskRun, get_task_run

_DEFAULT_TEST_CMD = ("python3", "-m", "pytest", "-q")
_OUTPUT_SUMMARY_LIMIT = 32_000
_NON_DELIVERABLE_PREFIXES = ("docs/tasks/", "docs/_queue/", "docs/_war_room/")


def is_deliverable_path(path: str) -> bool:
    """Board lifecycle writes do not count as Task implementation."""

    return bool(path.strip()) and not path.startswith(_NON_DELIVERABLE_PREFIXES)


def swe_run_tests(
    *,
    task_id: str,
    task_run: TaskRun,
    root: Path,
    cmd: list[str] | None = None,
) -> dict[str, object]:
    """Run pytest in the task worktree; return exit code and captured output."""

    _ = root
    _assert_task_run(task_id, task_run)
    wt = task_run.worktree.resolve()
    argv = list(cmd) if cmd is not None else list(_DEFAULT_TEST_CMD)
    _validate_pytest_cmd(argv)
    final_validation = _validation_target(task_id, task_run, root=Path(root).resolve())
    result = subprocess.run(
        argv,
        cwd=wt,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    outcome: dict[str, object] = {
        "exit_code": result.returncode,
        "output": _output_summary(result.stdout, result.stderr),
    }
    if final_validation is not None:
        outcome["final_validation"] = final_validation
    return outcome


def _validation_target(task_id: str, task_run: TaskRun, *, root: Path) -> dict[str, str] | None:
    """Capture the immutable branch pair immediately before final pytest runs."""

    if _git(task_run.worktree.resolve(), "status", "--porcelain").stdout.strip():
        return None
    if not _deliverable_commits(task_run):
        return None
    from cascade.board.store import read_doc
    from cascade.workspace.integration_worktree import integration_branch

    task = read_doc(task_id, root=root)
    if not task.meta.parent:
        return None
    source = _git(root, "rev-parse", "--verify", f"{task_run.branch}^{{commit}}", check=False)
    target = _git(
        root, "rev-parse", "--verify", f"{integration_branch('feature', task.meta.parent)}^{{commit}}",
        check=False,
    )
    if source.returncode != 0 or target.returncode != 0:
        return None
    return {
        "task_id": task_id,
        "deliverable_sha": source.stdout.strip(),
        "feature_base_sha": target.stdout.strip(),
    }


def swe_commit(
    message: str,
    *,
    task_id: str,
    task_run: TaskRun,
    root: Path,
) -> str:
    """Create or amend the task's sole deliverable commit; never push."""

    repo = Path(root).resolve()
    _assert_task_run(task_id, task_run)
    wt = task_run.worktree.resolve()
    _assert_task_branch(task_id, wt)
    _assert_commit_paths_allowed(task_id, wt, board_root=repo)
    deliverable_commits = _deliverable_commits(task_run)
    count = len(deliverable_commits)
    if count > 1:
        raise GitError(
            f"task/{task_id} already has {count} deliverable commits; "
            "refusing to add more"
        )
    if count == 1 and deliverable_commits[0] != _git(wt, "rev-parse", "HEAD").stdout.strip():
        raise GitError(
            f"task/{task_id} has a lifecycle commit after its deliverable; "
            "refusing to amend the wrong commit"
        )
    _git(wt, "add", "-A")
    trailer = f"Cascade-Task: {task_id}"
    if count == 1:
        existing = _git(wt, "log", "-1", "--format=%B").stdout.strip()
        commit_message = _with_task_trailer(existing or message, trailer)
        _git(wt, "commit", "--amend", "-m", commit_message)
    else:
        _git(wt, "commit", "-m", _with_task_trailer(message, trailer))
    sha = _git(wt, "rev-parse", "HEAD").stdout.strip()
    if not sha:
        raise GitError("commit succeeded but HEAD sha is empty")
    # Amending a deliverable changes the identity that validation attests to.
    # Do this at commit time so no old ready/queue record survives until a
    # later replay happens to notice it.
    from cascade.task.wiring import invalidate_validated_delivery

    invalidate_validated_delivery(task_id, root=repo)
    return sha


def _deliverable_commits(task_run: TaskRun) -> list[str]:
    """Find commits that changed implementation, ignoring board lifecycle commits."""

    wt = task_run.worktree.resolve()
    revs = _git(wt, "rev-list", "--reverse", f"{task_run.base_sha}..HEAD")
    commits: list[str] = []
    for sha in revs.stdout.splitlines():
        paths = _git(wt, "diff-tree", "--no-commit-id", "--name-only", "-r", sha)
        if any(is_deliverable_path(path) for path in paths.stdout.splitlines()):
            commits.append(sha)
    return commits


def _with_task_trailer(message: str, trailer: str) -> str:
    # The task id is orchestration-owned metadata.  Strip any model-supplied
    # value before appending the canonical trailer so publication cannot end up
    # with duplicate or spoofed task identities.
    body = "\n".join(
        line for line in message.strip().splitlines() if not line.startswith("Cascade-Task:")
    ).rstrip()
    return f"{body}\n\n{trailer}"


def register_task_git_tools() -> None:
    """Register swe_run_tests and swe_commit on the task tool registry (idempotent)."""

    from cascade.task.registry import task_tools

    expected = ("swe_run_tests", "swe_commit")
    if all(name in task_tools() for name in expected):
        return
    register_task_tool("swe_run_tests", _swe_run_tests_tool)
    register_task_tool("swe_commit", _swe_commit_tool)


def _swe_run_tests_tool(
    *,
    task_id: str,
    root: Path,
    cmd: list[str] | None = None,
) -> dict[str, object]:
    run = get_task_run(task_id)
    if run is None:
        raise TaskToolDenied(f"no active task run for {task_id}")
    return swe_run_tests(task_id=task_id, task_run=run, root=root, cmd=cmd)


def _swe_commit_tool(message: str, *, task_id: str, root: Path) -> str:
    run = get_task_run(task_id)
    if run is None:
        raise TaskToolDenied(f"no active task run for {task_id}")
    return swe_commit(message, task_id=task_id, task_run=run, root=root)


def _validate_pytest_cmd(argv: list[str]) -> None:
    """Allow only pytest invocations; reject shell/git escape hatches."""

    if not argv:
        raise TaskToolDenied("empty test command")
    forbidden = frozenset({"git", "push", "-c"})
    for arg in argv:
        if arg in forbidden:
            raise TaskToolDenied(f"test command rejected: forbidden token {arg!r}")

    first = argv[0]
    if first == "pytest" or first.endswith("/pytest"):
        return
    if first in ("python", "python3") and len(argv) >= 3 and argv[1] == "-m" and argv[2] == "pytest":
        return
    raise TaskToolDenied("test command must invoke pytest only")


def _assert_task_run(task_id: str, task_run: TaskRun) -> None:
    if task_run.task_id != task_id:
        raise TaskToolDenied(
            f"task_run.task_id {task_run.task_id!r} != task_id {task_id!r}"
        )


def _assert_task_branch(task_id: str, worktree: Path) -> None:
    branch = _git(worktree, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    expected = f"task/{task_id}"
    if branch != expected:
        raise TaskToolDenied(
            f"commit refused: worktree on {branch!r}, expected {expected!r}"
        )


def _assert_commit_paths_allowed(
    task_id: str,
    worktree: Path,
    *,
    board_root: Path,
) -> None:
    for rel in _changed_paths(worktree):
        if not task_tool_guard(
            rel,
            "write",
            task_id=task_id,
            worktree_root=worktree,
            board_root=board_root,
        ):
            raise TaskToolDenied(f"commit refused: path not allowed: {rel}")


def _changed_paths(worktree: Path) -> list[str]:
    result = _git(worktree, "status", "--porcelain", check=False)
    paths: list[str] = []
    for line in (result.stdout or "").splitlines():
        if len(line) < 4:
            continue
        entry = line[3:].strip()
        if " -> " in entry:
            entry = entry.split(" -> ", 1)[1].strip()
        if entry.startswith('"') and entry.endswith('"'):
            entry = entry[1:-1]
        if entry:
            paths.append(entry)
    return paths


def _output_summary(stdout: str, stderr: str) -> str:
    parts: list[str] = []
    if stdout:
        parts.append(stdout.rstrip())
    if stderr:
        parts.append(stderr.rstrip())
    combined = "\n".join(parts).strip()
    if len(combined) <= _OUTPUT_SUMMARY_LIMIT:
        return combined
    omitted = len(combined) - _OUTPUT_SUMMARY_LIMIT
    return combined[:_OUTPUT_SUMMARY_LIMIT] + f"\n... [{omitted} chars truncated]"


def _git(worktree: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if args and args[0] == "push":
        raise GitError("git push is not allowed from task git tools")
    result = subprocess.run(
        ["git", *args],
        cwd=worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} failed")
    return result
