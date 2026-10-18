"""Task boot wiring: worktree, skills, tools, and test-completion orchestration."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.gitutil import head_sha
from cascade.board.store import read_doc
from cascade.task.boot import install_task_boot_hook, last_fail_closed_boot
from cascade.task.checkpoint import checkpoint_path
from cascade.task.failure import classify_error, fail_task, maybe_retry
from cascade.task.git_tools import register_task_git_tools
from cascade.task.io_tools import register_task_io_tools
from cascade.task.report import mark_awaiting_merge
from cascade.task.registry import register_task_tool, task_tools
from cascade.task.skills_context import apply_skill_playbooks
from cascade.watchdog.role_skills import load_role_skills_context
from cascade.watchdog.skills import SkillPathError
from cascade.task.worktree import (
    create_task_worktree,
    get_task_run,
    install_task_worktree_teardown_hook,
)
from cascade.watchdog.hooks import register_boot_hook

_wiring_root: Path | None = None
_infra_attempts: dict[str, int] = {}


def load_task_tools() -> None:
    """Register all task SWE tools idempotently."""

    expected = (
        "swe_read",
        "swe_write",
        "read_doc",
        "swe_run_tests",
        "swe_commit",
        "fail_task",
    )
    if all(name in task_tools() for name in expected):
        return
    register_task_io_tools()
    register_task_git_tools()
    if "fail_task" not in task_tools():
        from cascade.task.failure import fail_task as fail_task_fn

        register_task_tool("fail_task", fail_task_fn)


def boot_task_wired(task_id: str) -> None:
    """Second task boot hook: worktree, skill playbooks, coding state."""

    if _wiring_root is None:
        raise RuntimeError("install_task_wiring(root) must run before boot_task_wired")
    root = _wiring_root

    stale = last_fail_closed_boot()
    if stale is not None and stale[0] == task_id:
        return

    if not checkpoint_path(task_id, root=root).exists():
        return

    try:
        task = read_doc(task_id, root=root)
    except Exception:
        return
    if task.meta.tier != "task":
        return

    if head_sha(root) is None:
        return

    skills = [str(p) for p in task.meta.skills]
    parent_rev = task.meta.parent_rev

    try:
        run = create_task_worktree(
            task_id,
            root=root,
            parent_rev=parent_rev,
            skills=skills,
        )
    except GitError as exc:
        detail = str(exc).strip() or "worktree_creation_failed"
        fail_task(task_id, f"worktree_error: {detail}", root=root)
        return
    try:
        playbooks = load_role_skills_context(
            root,
            "swe",
            task_skills=skills,
        )
    except SkillPathError as exc:
        detail = str(exc).strip() or "illegal_skill_path"
        fail_task(task_id, f"skill_path_error: {detail}", root=root)
        return
    apply_skill_playbooks(task_id, playbooks, root=root)
    run.state = "coding"


def on_tests_finished(task_id: str, result: dict[str, object], *, root: Path) -> None:
    """Handle pytest (or swe_run_tests) outcome: merge-ready or fail/retry."""

    repo = Path(root).resolve()
    exit_code = result.get("exit_code")
    if exit_code == 0:
        run = get_task_run(task_id)
        if run is None:
            return
        mark_awaiting_merge(task_id, run, root=repo)
        _infra_attempts.pop(task_id, None)
        return
    _route_failure(task_id, result, root=repo)


def on_tool_error(task_id: str, exc: BaseException, *, root: Path) -> None:
    """Route tool/infra exceptions through classify / retry / fail_task."""

    _route_failure(task_id, exc, root=Path(root).resolve())


def route_swe_turn_failure(task_id: str, exc_or_result: object, *, root: Path) -> bool:
    """Classify a SWE turn failure; return True when another attempt is allowed."""

    return _route_failure(task_id, exc_or_result, root=Path(root).resolve())


def clear_swe_turn_success(task_id: str) -> None:
    """Clear infra retry counter after a successful SWE turn."""

    _infra_attempts.pop(task_id, None)


def load_task_wiring(root: Path) -> None:
    """Register wired boot hook, tools, and worktree teardown (idempotent)."""

    global _wiring_root
    repo = Path(root).resolve()
    _wiring_root = repo

    install_task_boot_hook(repo)

    from cascade.watchdog.hooks import _boot

    if not any(fn is boot_task_wired for fn in _boot["task"]):
        register_boot_hook("task", boot_task_wired)

    load_task_tools()
    install_task_worktree_teardown_hook(repo)
    _install_task_graph_teardown_hook(repo)


def install_task_wiring(root: Path) -> None:
    """Alias for ``load_task_wiring`` (server / watchdog install entrypoint)."""

    load_task_wiring(root)


def clear_task_wiring_state() -> None:
    """Reset wiring module state (tests only)."""

    global _wiring_root
    _wiring_root = None
    _infra_attempts.clear()


def get_infra_attempt(task_id: str) -> int:
    return _infra_attempts.get(task_id, 0)


def set_infra_attempt(task_id: str, attempt: int | None) -> None:
    if attempt is None:
        _infra_attempts.pop(task_id, None)
    else:
        _infra_attempts[task_id] = attempt


def _route_failure(task_id: str, exc_or_result: object, *, root: Path) -> bool:
    kind = classify_error(exc_or_result)
    attempt = _infra_attempts.get(task_id, 0)
    if maybe_retry(task_id, kind, attempt, root=root):
        _infra_attempts[task_id] = attempt + 1
        return True
    reason = _failure_reason(kind, exc_or_result)
    fail_task(task_id, reason, root=root)
    _infra_attempts.pop(task_id, None)
    return False


def _install_task_graph_teardown_hook(root: Path) -> None:
    from cascade.watchdog.hooks import _teardown, register_teardown_hook

    if not any(fn is _teardown_task_graph for fn in _teardown["task"]):
        register_teardown_hook("task", _teardown_task_graph)


def _teardown_task_graph(work_id: str) -> None:
    if _wiring_root is None:
        return
    from cascade.task.graph import drop_task_graph

    drop_task_graph(work_id, root=_wiring_root)


def _failure_reason(kind: str, exc_or_result: object) -> str:
    if isinstance(exc_or_result, dict) and exc_or_result.get("exit_code") not in (
        None,
        0,
    ):
        return "tests_red"
    if getattr(exc_or_result, "status", None) == "error":
        return "swe_run_error"
    if kind == "infra":
        return "infra_error"
    return "spec_error"
