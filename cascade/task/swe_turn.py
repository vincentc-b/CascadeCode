"""SWE role turn against the active task worktree (feat_009 / task_047)."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from cascade.agent import CursorAgentError, RoleResult, RoleTurn, run_role
from cascade.task.swe_mcp import build_swe_mcp_servers
from cascade.task.git_tools import (
    _assert_commit_paths_allowed,
    _changed_paths,
    swe_commit,
)
from cascade.task.guard import TaskToolDenied
from cascade.task.worktree import TaskRun, get_task_run

RunRoleFn = Callable[[RoleTurn], Awaitable[RoleResult]]


def augment_swe_prompt_with_skill_paths(
    task_id: str,
    prompt: str,
    *,
    root: Path,
) -> str:
    """Prepend ``skill_playbooks`` path list and bodies (same block as planning turns)."""

    from cascade.agent.graph_turn import prepend_role_skills
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    repo = Path(root).resolve()
    graph = ensure_task_graph(task_id, root=repo)
    values = graph.get_state(thread_config(task_id)).values or {}
    playbooks = values.get("skill_playbooks") or []
    if not playbooks:
        return prompt
    return prepend_role_skills(prompt, playbooks)

def default_swe_commit_message(task_id: str) -> str:
    """Deterministic commit message when the agent did not commit during the run."""

    return f"task/{task_id}: swe turn"


@dataclass(frozen=True)
class SweTurnResult:
    """Outcome of one SWE adapter turn (commit optional, failure flags for graph wiring)."""

    role_result: RoleResult | None = None
    commit_sha: str | None = None
    failed_closed: bool = False
    may_retry: bool = False
    failure_reason: str | None = None


def resolve_swe_task_run(task_id: str) -> TaskRun:
    """Return the active task run or raise if no worktree is registered."""

    run = get_task_run(task_id)
    if run is None:
        raise RuntimeError(f"no active task run for {task_id!r}")
    return run


def build_swe_role_turn(
    task_id: str,
    *,
    provider: str,
    model_id: str,
    prompt: str,
    root: Path,
) -> RoleTurn:
    """Assemble a ``RoleTurn`` with cwd set to the task worktree."""

    run = resolve_swe_task_run(task_id)
    return RoleTurn(
        role="swe",
        provider=provider,  # type: ignore[arg-type]
        model_id=model_id,
        prompt=prompt,
        cwd=run.worktree.resolve(),
        tools=build_swe_mcp_servers(task_id, root=root),
    )


def worktree_diff_committable(
    task_id: str,
    task_run: TaskRun,
    *,
    root: Path,
) -> bool:
    """Return whether the current worktree diff may be committed on ``task/{id}``."""

    repo = Path(root).resolve()
    wt = task_run.worktree.resolve()
    if not _changed_paths(wt):
        return True
    try:
        _assert_commit_paths_allowed(task_id, wt, board_root=repo)
    except TaskToolDenied:
        return False
    return True


async def run_swe_turn(
    task_id: str,
    *,
    provider: str,
    model_id: str,
    prompt: str,
    root: Path,
    commit_message: str | None = None,
    run_role_fn: RunRoleFn | None = None,
) -> SweTurnResult:
    """Run one SWE Cursor turn in the task worktree; gate paths and commit when allowed."""

    from cascade.task.wiring import clear_swe_turn_success, route_swe_turn_failure

    repo = Path(root).resolve()
    run = resolve_swe_task_run(task_id)
    full_prompt = augment_swe_prompt_with_skill_paths(task_id, prompt, root=repo)
    turn = build_swe_role_turn(
        task_id,
        provider=provider,
        model_id=model_id,
        prompt=full_prompt,
        root=repo,
    )
    invoke = run_role_fn or run_role

    try:
        role_result = await invoke(turn)
    except CursorAgentError as exc:
        may_retry = route_swe_turn_failure(task_id, exc, root=repo)
        return SweTurnResult(
            failed_closed=not may_retry,
            may_retry=may_retry,
            failure_reason=str(exc.message),
        )

    if role_result.status == "error":
        route_swe_turn_failure(task_id, role_result, root=repo)
        return SweTurnResult(
            role_result=role_result,
            failed_closed=True,
            failure_reason="swe_run_error",
        )

    wt = run.worktree.resolve()
    if _changed_paths(wt) and not worktree_diff_committable(task_id, run, root=repo):
        from cascade.task.failure import fail_task

        fail_task(task_id, "forbidden_commit_paths", root=repo)
        clear_swe_turn_success(task_id)
        return SweTurnResult(
            role_result=role_result,
            failed_closed=True,
            failure_reason="forbidden_commit_paths",
        )

    commit_sha: str | None = None
    if _changed_paths(wt):
        message = (commit_message or default_swe_commit_message(task_id)).strip()
        if message:
            commit_sha = swe_commit(
                message,
                task_id=task_id,
                task_run=run,
                root=repo,
            )

    clear_swe_turn_success(task_id)
    return SweTurnResult(role_result=role_result, commit_sha=commit_sha)


def run_swe_turn_sync(
    task_id: str,
    *,
    provider: str,
    model_id: str,
    prompt: str,
    root: Path,
    commit_message: str | None = None,
    run_role_fn: RunRoleFn | None = None,
) -> SweTurnResult:
    """Synchronous wrapper for graph nodes and tests."""

    import asyncio

    return asyncio.run(
        run_swe_turn(
            task_id,
            provider=provider,
            model_id=model_id,
            prompt=prompt,
            root=root,
            commit_message=commit_message,
            run_role_fn=run_role_fn,
        )
    )
