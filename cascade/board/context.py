"""Injectable repo root so library calls are not pinned to the workspace."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path

from cascade.board.paths import infer_repo_root

_repo_root: ContextVar[Path | None] = ContextVar("cascade_repo_root", default=None)


def set_repo_root(root: Path | None) -> None:
    """Set the process-context default repo. Pass None to clear it."""

    if root is None:
        _repo_root.set(None)
    else:
        _repo_root.set(Path(root).resolve())


def get_repo_root() -> Path | None:
    return _repo_root.get()


def resolve_root(root: Path | None = None, hint: Path | None = None) -> Path:
    """Explicit argument, then context, then a path hint, then the current directory."""

    if root is not None:
        return Path(root).resolve()
    current = _repo_root.get()
    if current is not None:
        return current
    if hint is not None:
        inferred = infer_repo_root(Path(hint))
        if inferred is not None:
            return inferred
    return Path.cwd().resolve()
