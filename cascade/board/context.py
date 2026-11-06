"""Injectable repo root so library calls are not pinned to the workspace."""

from __future__ import annotations

from contextvars import ContextVar
from pathlib import Path
from threading import RLock
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cascade.workspace.types import ProjectContext

from cascade.board.paths import infer_repo_root

_repo_root: ContextVar[Path | None] = ContextVar("cascade_repo_root", default=None)
_project_context: ProjectContext | None = None
_project_context_lock = RLock()


def set_repo_root(root: Path | None) -> None:
    """Set the process-context default repo. Pass None to clear it."""

    if root is None:
        _repo_root.set(None)
    else:
        _repo_root.set(Path(root).resolve())


def get_repo_root() -> Path | None:
    return _repo_root.get()


def set_project_context(project: ProjectContext | None) -> None:
    """Install the resolved repository roles used by planning persistence.

    The supervisor serves requests on multiple threads, so repository roles are
    process configuration rather than a context variable.  Passing ``None``
    restores the legacy single-repository behavior.
    """

    global _project_context
    with _project_context_lock:
        _project_context = project


def get_project_context() -> ProjectContext | None:
    with _project_context_lock:
        return _project_context


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


def resolve_tracking_root(root: Path | None = None, hint: Path | None = None) -> Path:
    """Resolve the repository that owns versioned planning artifacts.

    Explicit roots beneath the target's managed worktree directory still name
    planning operations, so they route to the tracking checkout as well.  This
    function is intentionally used only by planning stores; source, build, and
    task-worktree operations continue to call :func:`resolve_root`.
    """

    requested = resolve_root(root, hint)
    project = get_project_context()
    if project is None:
        return requested
    target = project.target.root.resolve()
    tracking = project.tracking.root.resolve()
    if target == tracking or requested == tracking:
        return requested
    if requested == target or requested.is_relative_to(target / ".cascade" / "worktrees"):
        return tracking
    return requested


def route_planning_path(path: Path, *, requested_root: Path, tracking_root: Path) -> Path:
    """Rebase a planning-document path from a target checkout to tracking."""

    candidate = Path(path)
    if not candidate.is_absolute():
        return (tracking_root / candidate).resolve()
    resolved = candidate.resolve()
    requested = requested_root.resolve()
    tracking = tracking_root.resolve()
    if requested == tracking or resolved.is_relative_to(tracking):
        return resolved
    try:
        relative = resolved.relative_to(requested)
    except ValueError:
        relative = Path()
    if not relative.parts or relative.parts[0] != "docs":
        project = get_project_context()
        if project is None:
            return resolved
        try:
            target_relative = resolved.relative_to(project.target.root.resolve())
        except ValueError:
            return resolved
        docs_indexes = [
            index for index, part in enumerate(target_relative.parts) if part == "docs"
        ]
        if not docs_indexes:
            return resolved
        relative = Path(*target_relative.parts[docs_indexes[-1] :])
    return (tracking_root / relative).resolve()
