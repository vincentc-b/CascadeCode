"""Cross-process serialization for canonical Task execution and delivery state."""

from __future__ import annotations

import fcntl
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cascade.board.context import resolve_tracking_root
from cascade.board.lock import process_lock

_LOCK_NAME = "task-lifecycle.lock"
_held = threading.local()


def lifecycle_root(root: Path) -> Path:
    """One tracking-trunk home for lifecycle state, independent of caller checkout."""
    from cascade.workspace.integration_worktree import locate_trunk

    return locate_trunk(resolve_tracking_root(root))


@contextmanager
def task_lifecycle_lock(*, root: Path) -> Iterator[None]:
    """Serialize execution leases, attempts, action history, and recovery generations.

    ``process_lock`` retains the existing in-process ordering.  The flock adds
    the missing boundary between a War Room process and workspace workers.
    Nested calls on the same thread are deliberately re-entrant.
    """

    # Task/Feature MCP callers and the trunk supervisor share one transaction.
    repo = lifecycle_root(root)
    path = repo / ".cascade" / _LOCK_NAME
    key = str(path.resolve())
    with process_lock:
        held = getattr(_held, "paths", set())
        if key in held:
            yield
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            _held.paths = {*held, key}
            try:
                yield
            finally:
                _held.paths = held
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def task_lifecycle_read_lock(*, root: Path) -> Iterator[None]:
    """Synchronize a projection without creating lifecycle state.

    Writers create the durable lock before any lifecycle sidecar.  A missing
    lock therefore means there is no writer to coordinate with; importantly,
    a healthy read must not make an otherwise clean repository dirty.
    """

    repo = lifecycle_root(root)
    path = repo / ".cascade" / _LOCK_NAME
    key = str(path.resolve())
    with process_lock:
        held = getattr(_held, "paths", set())
        if key in held or not path.exists():
            yield
            return
        with path.open("r", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
            _held.paths = {*held, key}
            try:
                yield
            finally:
                _held.paths = held
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
