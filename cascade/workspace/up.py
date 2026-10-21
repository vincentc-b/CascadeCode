"""Start War Room and watchdog on the product trunk (``cascade up``)."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run, has_git
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.init import _BOARD_TIERS
from cascade.workspace.lock import SupervisorLock
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.types import WorkspaceRoot

def resume_legally_active_graphs(root: Path) -> None:
    """Recreate missing integration worktrees for registered branches (no dispatch)."""

    from cascade.workspace.integration_worktree import (
        repair_all_registered,
        retire_terminal_registered_worktrees,
    )
    from cascade.workspace.kickoff import resume_inflight_graphs

    repo = Path(root).resolve()
    retire_terminal_registered_worktrees(repo)
    repair_all_registered(repo)
    resume_inflight_graphs(repo)


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
    """Bind War Room and watchdog to ``root``; block until ``stop_when`` or process exit.

    Takes ``.cascade/supervisor.lock`` for the root; a second ``up`` refuses while held.
    Lock is released when this function returns (normal exit, ``stop_when``, or error after acquire).
    ``up`` does not dispatch or check out integration branches in ``--root``.
    """

    from cascade.war_room.server import assert_loopback_host, serve
    from cascade.watchdog.loop import run_watchdog

    assert_loopback_host(host)
    ws = prepare_up(root)
    lock = SupervisorLock(ws.path)
    lock.acquire(blocking=False)
    try:
        server = serve(root=ws.path, host=host, port=port)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        try:
            # Bind the operator UI before potentially long agent resume turns.
            # Recovery can then be observed instead of looking like a dead app.
            resume_legally_active_graphs(ws.path)
            run_watchdog(root=ws.path, stop_when=stop_when)
        finally:
            server.shutdown()
            server.server_close()
            server_thread.join(timeout=10)
    finally:
        lock.release()
