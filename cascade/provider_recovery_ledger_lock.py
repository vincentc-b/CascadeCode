"""Serialize recovery-ledger transactions across threads and processes."""

from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from cascade.watchdog.lock import process_lock


@contextmanager
def recovery_ledger_lock(root: Path) -> Iterator[None]:
    """Lock a stable sidecar while reading and replacing the JSON ledger.

    Locking the ledger inode would be unsafe because writers replace it. Keep
    the process lock outermost to preserve the existing lock order.
    """

    with process_lock:
        path = root / ".cascade" / "provider_recoveries.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
