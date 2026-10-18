"""Path sandbox for Task Team swe_read / swe_write."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc

# Case-insensitive path segments under docs/ that task tools must not touch.
_READ_DENIED = (("docs", "epics"), ("docs", "features"))
_WRITE_DENIED = _READ_DENIED + (("docs", "tasks"),)


class TaskToolDenied(PermissionError):
    """Task team is not allowed to access this path or work id."""


def task_tool_guard(
    path: Path | str,
    op: str,
    *,
    task_id: str,
    worktree_root: Path,
    board_root: Path,
) -> bool:
    """Return whether the Task graph may read or write `path` under `worktree_root`."""

    if op not in ("read", "write"):
        return False

    board = Path(board_root).resolve()
    worktree = Path(worktree_root).resolve()
    try:
        task = read_doc(task_id, root=board)
    except NotFound:
        return False
    if task.meta.tier != "task" or task.meta.id != task_id:
        return False

    resolved = _resolve_under_root(path, worktree)
    if resolved is None:
        return False

    if _walks_symlink(path, worktree):
        return False

    rel = resolved.relative_to(worktree)
    parts = rel.parts
    deny = _WRITE_DENIED if op == "write" else _READ_DENIED
    if _under_denied_prefix(parts, deny):
        return False

    if op == "write" and _hardlink_bypass_denied(resolved, parts, worktree):
        return False

    return True


def _under_denied_prefix(parts: tuple[str, ...], prefixes: tuple[tuple[str, ...], ...]) -> bool:
    folded = tuple(p.casefold() for p in parts)
    for prefix in prefixes:
        plen = len(prefix)
        if len(folded) >= plen and folded[:plen] == prefix:
            return True
    return False


def _hardlink_bypass_denied(
    resolved: Path,
    logical_parts: tuple[str, ...],
    worktree: Path,
) -> bool:
    """Deny writes when a hardlink aliases content under a denied docs/ prefix."""

    logical_resolved = (worktree.joinpath(*logical_parts)).resolve()
    if logical_resolved != resolved:
        logical_rel = (
            logical_resolved.relative_to(worktree)
            if logical_resolved.is_relative_to(worktree)
            else None
        )
        if logical_rel is not None and _under_denied_prefix(
            logical_rel.parts, _WRITE_DENIED
        ):
            return True
        if _under_denied_prefix(
            resolved.relative_to(worktree).parts, _WRITE_DENIED
        ) and not _under_denied_prefix(logical_parts, _WRITE_DENIED):
            return True

    try:
        st = resolved.stat()
    except OSError:
        return False

    if st.st_nlink <= 1:
        return False

    for prefix in _WRITE_DENIED:
        tree = worktree.joinpath(*prefix)
        if not tree.exists():
            continue
        for candidate in tree.rglob("*"):
            try:
                other = candidate.stat()
            except OSError:
                continue
            if other.st_dev == st.st_dev and other.st_ino == st.st_ino:
                if candidate.resolve() != resolved:
                    return True
    return False


def _walks_symlink(path: Path | str, root: Path) -> bool:
    repo = Path(root).resolve()
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = repo / candidate
    try:
        rel = candidate.absolute().relative_to(repo)
    except ValueError:
        return True
    current = repo
    for part in rel.parts:
        current = current / part
        if current.is_symlink():
            return True
    return False


def _resolve_under_root(path: Path | str, root: Path) -> Path | None:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root)
    except (OSError, ValueError):
        return None
    return resolved
