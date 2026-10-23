"""Start War Room and watchdog on the product trunk (``cascade up``)."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run, has_git
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.init import _BOARD_TIERS
from cascade.workspace.lock import SupervisorLock
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.types import WorkspaceRoot


_CASCADE_SOURCE_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_CHECK_INTERVAL_SECONDS = 1.0


def _source_fingerprint(root: Path = _CASCADE_SOURCE_ROOT) -> str:
    """Return a stable fingerprint of the Python source loaded by the supervisor."""

    digest = hashlib.sha256()
    try:
        paths = sorted(
            root.rglob("*.py"), key=lambda path: path.relative_to(root).as_posix()
        )
        for path in paths:
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            body = path.read_bytes()
            digest.update(len(body).to_bytes(8, "big"))
            digest.update(body)
    except OSError as exc:
        # A checkout can briefly remove or replace files.  Treat that as a
        # source change rather than letting a read race preserve stale code.
        return f"unreadable:{type(exc).__name__}:{exc}"
    return digest.hexdigest()


def resume_legally_active_graphs(root: Path) -> None:
    """Repair registered worktrees and queue interrupted turns (no new dispatch)."""

    from cascade.workspace.integration_worktree import (
        repair_all_registered,
        retire_terminal_registered_worktrees,
    )
    from cascade.workspace.kickoff import deferred_kickoffs, resume_inflight_graphs

    repo = Path(root).resolve()
    retire_terminal_registered_worktrees(repo)
    repair_all_registered(repo)
    # Model turns can take minutes.  Queue only those turns in the established
    # per-graph background workers so watchdog startup is not held behind one
    # recovered graph; the structural worktree repair above remains ordered.
    with deferred_kickoffs():
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
                stop_when=stop_when,
            )
        finally:
            listen_sock.close()
    finally:
        lock.release()
