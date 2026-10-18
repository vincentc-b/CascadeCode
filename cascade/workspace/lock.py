"""One supervisor process per workspace root (file lock under ``.cascade/``)."""

from __future__ import annotations

import fcntl
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.workspace.errors import WorkspaceError

_LOCK_NAME = "supervisor.lock"


class SupervisorLock:
    """Exclusive flock on ``.cascade/supervisor.lock``. Released on ``release()`` or context exit."""

    def __init__(self, root: Path) -> None:
        self._root = resolve_root(root)
        self._path = self._root / ".cascade" / _LOCK_NAME
        self._handle = None

    @property
    def path(self) -> Path:
        return self._path

    def acquire(self, *, blocking: bool = True) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        handle = self._path.open("a+", encoding="utf-8")
        flags = fcntl.LOCK_EX
        if not blocking:
            flags |= fcntl.LOCK_NB
        try:
            fcntl.flock(handle.fileno(), flags)
        except BlockingIOError as exc:
            handle.close()
            raise WorkspaceError(
                f"supervisor already running for workspace {self._root} "
                f"(lock {self._path}); stop the other cascade up process first"
            ) from exc
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={__import__('os').getpid()}\n")
        handle.flush()
        self._handle = handle

    def release(self) -> None:
        if self._handle is None:
            return
        try:
            fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> SupervisorLock:
        self.acquire()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
