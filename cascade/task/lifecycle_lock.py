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


@contextmanager
def task_lifecycle_lock(*, root: Path) -> Iterator[None]:
    """Serialize execution leases, attempts, action history, and recovery generations.

    ``process_lock`` retains the existing in-process ordering.  The flock adds
    the missing boundary between a War Room process and workspace workers.
    Nested calls on the same thread are deliberately re-entrant.
    """

    repo = resolve_tracking_root(root)
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
