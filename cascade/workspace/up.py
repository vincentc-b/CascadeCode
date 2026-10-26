"""Start War Room and watchdog on the product trunk (``cascade up``)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run, has_git
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.init import _BOARD_TIERS
from cascade.workspace.lock import SupervisorLock
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.source_fingerprint import source_fingerprint as _source_fingerprint
from cascade.workspace.types import WorkspaceRoot


_SOURCE_CHECK_INTERVAL_SECONDS = 1.0


def repair_registered_worktrees(root: Path) -> None:
    """Retire terminal registrations and repair missing integration worktrees."""

    from cascade.workspace.integration_worktree import (
        repair_all_registered,
        retire_terminal_registered_worktrees,
    )

    repo = Path(root).resolve()
    retire_terminal_registered_worktrees(repo)
    repair_all_registered(repo)


def resume_interrupted_task_runs(root: Path) -> list[tuple[str, str]]:
    """Reclaim interrupted Task turns through their existing queue action.

    The active-run restore derives eligibility from the durable execution lease
    and returns nothing once the TaskRun is attached again. The resume event is
    therefore emitted once per interrupted execution, never as a new dispatch
    or replacement action.
    """

    from cascade.task.wiring import restore_active_task_runs
    from cascade.watchdog.events import append_event
    from cascade.watchdog.types import Event
    from cascade.workspace.kickoff import deferred_kickoffs, kickoff_graph_queue_event

    repo = Path(root).resolve()
    restored = restore_active_task_runs(repo)
    if not restored:
        return []

    with deferred_kickoffs():
        for task_id, feature_id in restored:
            append_event(
                task_id,
                Event(
                    type="TaskResumeRequested",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "task_id": task_id,
                        "feature_id": feature_id,
                        "instruction": (
                            "Resume the Task by reading its plan and pinned Feature plan, "
                            "then implement, test, and commit the deliverable. Do not report "
                            "completion without a non-lifecycle commit."
                        ),
                    },
                    dest=task_id,
                ),
                root=repo,
            )
            kickoff_graph_queue_event(task_id, root=repo, by="watchdog")
    return restored


def submit_recovered_turns(root: Path) -> None:
    """Queue interrupted graph and Task turns through existing workers."""

    from cascade.workspace.kickoff import deferred_kickoffs, resume_inflight_graphs
    from cascade.workspace.supervisor_readiness import observe_startup_phase

    repo = Path(root).resolve()
    observe_startup_phase("recovery")
    # Model turns can take minutes.  Queue only those turns in the established
    # per-graph background workers so watchdog startup is not held behind one
    # recovered graph; structural worktree repair remains ordered before this call.
    with deferred_kickoffs():
        resume_inflight_graphs(repo)
    resume_interrupted_task_runs(repo)
    observe_startup_phase("watchdog")


def resume_legally_active_graphs(root: Path) -> None:
    """Repair registered worktrees and queue interrupted turns (no new dispatch)."""

    repair_registered_worktrees(root)
    submit_recovered_turns(root)


def _has_board_layout(path: Path) -> bool:
    docs = path / "docs"
    if not docs.is_dir():
        return False
    for tier in _BOARD_TIERS:
        if not (docs / tier).is_dir():
            return False
    return True


def _current_branch(repo: Path) -> str | None:
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"], repo, check=False)
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    if not name or name == "HEAD":
        return None
    return name


def prepare_up(root: Path | None = None) -> WorkspaceRoot:
    """Validate git root, board layout, and trunk checkout; does not start processes."""

    path = resolve_root(root)
    if not has_git(path):
        raise WorkspaceError(f"not a git repository: {path}")
    if not _has_board_layout(path):
        raise WorkspaceError(
            f"board layout missing under {path / 'docs'}; run `cascade init` first"
        )

    trunk = resolve_product_trunk(path)
    checkout = _current_branch(path)
    if checkout != trunk:
        raise WorkspaceError(
            f"workspace checkout must be the product trunk ({trunk!r}), not {checkout!r}; "
            "do not run cascade up from epic/*, feat/*, or task/* branches"
        )

    return WorkspaceRoot(
        path=path,
        trunk=trunk,
        board=path / "docs",
        config=path / "cascade.toml",
        runtime=path / ".cascade",
    )


def up(
    root: Path | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    stop_when: Callable[[], bool] | None = None,
) -> None:
    """Long-lived launcher: lock, listen socket, and replaceable workers.

    Takes ``.cascade/supervisor.lock`` for the root; a second ``up`` refuses while held.
    The launcher binds the War Room listen socket once and respawns
    ``python -m cascade.workspace.worker`` on source updates (exit 75) or crashes.
    Lock and listener stay up across worker restarts until operator stop or ``stop_when``.
    """

    from cascade.war_room.server import assert_loopback_host
    from cascade.workspace.launcher import bind_listen_socket, run_launcher_loop

    assert_loopback_host(host)
    ws = prepare_up(root)

    lock = SupervisorLock(ws.path)
    lock.acquire(blocking=False)
    try:
        listen_sock = bind_listen_socket(host=host, port=port)
        try:
            run_launcher_loop(
                workspace_root=ws.path,
                listen_sock=listen_sock,
                lock_token=str(lock.path.resolve()),
                lock_fd=lock.fileno(),
                stop_when=stop_when,
            )
        finally:
            listen_sock.close()
    finally:
        lock.release()
