"""SWE role turn against the active task worktree (feat_009 / task_047)."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from cascade.agent import CursorAgentError, RoleResult, RoleTurn, run_role
from cascade.agent.errors import TurnCancelledForDrain
from cascade.task.swe_mcp import build_swe_custom_tools, build_swe_mcp_servers
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


def augment_swe_prompt_with_work_context(task_id: str, prompt: str, *, root: Path) -> str:
    """Put the scoped Task and pinned Feature plans directly in the SWE prompt."""

    from cascade.task.io_tools import task_read_doc

    task = task_read_doc(task_id, task_id=task_id, root=root)
    sections = [
        "Execute the Task below now. Implement the change in the worktree, run "
        "relevant tests, and leave a deliverable commit. You MUST call Cascade's "
        "swe_run_tests tool with the scoped test command before finishing; tests run "
        "only through a native shell do not satisfy the supervised merge gate. Do not "
        "merely summarize the plan or report completion.",
        f"--- Task plan: {task.meta.id} ({task.meta.title}) ---\n{task.body}",
    ]
    if task.meta.parent:
        parent = task_read_doc(task.meta.parent, task_id=task_id, root=root)
        sections.append(
            f"--- Pinned Feature plan: {parent.meta.id} ({parent.meta.title}) ---\n{parent.body}"
        )
    sections.append(f"--- Lifecycle input ---\n{prompt}")
    return "\n\n".join(sections)

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
    reasoning_level: str | None = None,
) -> RoleTurn:
    """Assemble a ``RoleTurn`` with cwd set to the task worktree."""

    run = resolve_swe_task_run(task_id)
    is_cursor = provider == "cursor"
    return RoleTurn(
        role="swe",
        provider=provider,  # type: ignore[arg-type]
        model_id=model_id,
        prompt=prompt,
        cwd=run.worktree.resolve(),
        tools=[] if is_cursor else build_swe_mcp_servers(task_id, root=root),
        custom_tools=(build_swe_custom_tools(task_id, root=root) if is_cursor else None),
        reasoning_level=reasoning_level,
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
    reasoning_level: str | None = None,
    commit_message: str | None = None,
    run_role_fn: RunRoleFn | None = None,
) -> SweTurnResult:
    """Run one SWE Cursor turn in the task worktree; gate paths and commit when allowed."""

    from cascade.task.wiring import clear_swe_turn_success, route_swe_turn_failure

    repo = Path(root).resolve()
    run = resolve_swe_task_run(task_id)
    full_prompt = augment_swe_prompt_with_work_context(task_id, prompt, root=repo)
    full_prompt = augment_swe_prompt_with_skill_paths(task_id, full_prompt, root=repo)
    turn = build_swe_role_turn(
        task_id,
        provider=provider,
        model_id=model_id,
        prompt=full_prompt,
        root=repo,
        reasoning_level=reasoning_level,
    )
    invoke = run_role_fn or run_role

    from cascade.task.execution import heartbeat

    async def keep_lease_alive() -> None:
        while True:
            await asyncio.sleep(15)
            heartbeat(task_id, root=repo)

    lease_heartbeat = asyncio.create_task(keep_lease_alive())
    from cascade.workspace.in_flight_turn_watchdog import swe_task_turn_context

    try:
        with swe_task_turn_context(
            task_id,
            provider=provider,
            model_id=model_id,
            root=repo,
        ):
            role_result = await invoke(turn)
    except TurnCancelledForDrain:
        raise
    except CursorAgentError as exc:
        may_retry = route_swe_turn_failure(task_id, exc, root=repo)
        return SweTurnResult(
            failed_closed=not may_retry,
            may_retry=may_retry,
            failure_reason=str(exc.message),
        )
    finally:
        lease_heartbeat.cancel()
        with suppress(asyncio.CancelledError):
            await lease_heartbeat
        heartbeat(task_id, root=repo)

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


def has_deliverable_commit(run: TaskRun) -> bool:
    """Require a Task to change something beyond board lifecycle artifacts."""

    import subprocess

    result = subprocess.run(
        ["git", "diff", "--name-only", f"{run.base_sha}..HEAD"],
        cwd=run.worktree,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if result.returncode != 0:
        return False
    ignored = ("docs/tasks/", "docs/_queue/", "docs/_war_room/")
    return any(
        path.strip() and not path.strip().startswith(ignored)
        for path in result.stdout.splitlines()
    )


def run_swe_turn_sync(
    task_id: str,
    *,
    provider: str,
    model_id: str,
    prompt: str,
    root: Path,
    reasoning_level: str | None = None,
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
            reasoning_level=reasoning_level,
            commit_message=commit_message,
            run_role_fn=run_role_fn,
        )
    )
