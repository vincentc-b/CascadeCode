"""Path sandbox for Epic Team read/write tools."""

from __future__ import annotations

import re
from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.parse import parse_doc
from cascade.board.paths import filename_work_id
from cascade.board.store import list_board, read_doc

_FEATURE_COLUMNS = ("1_backlog", "2_active", "3_completed")
_SIDECAR_TOP = frozenset({"_queue", "_comments", "_amendments"})
_AMENDMENT_FEAT_RE = re.compile(r"feat_\d+")


class EpicToolDenied(PermissionError):
    """Epic team is not allowed to access this path or work id."""


def tool_guard(path: Path | str, op: str, *, epic_id: str, root: Path) -> bool:
    """Return whether the Epic graph may read or write `path` relative to `root`."""

    if op not in ("read", "write"):
        return False

    repo = Path(root).resolve()
    try:
        epic = read_doc(epic_id, root=repo)
    except NotFound:
        return False
    if epic.meta.tier != "epic":
        return False

    resolved = _resolve_under_root(path, repo)
    if resolved is None:
        return False

    if _walks_symlink(path, repo):
        return False

    rel = resolved.relative_to(repo)
    parts = rel.parts
    if not parts or parts[0] != "docs":
        return False

    if len(parts) >= 2 and parts[1] in _SIDECAR_TOP:
        return False

    if len(parts) >= 2 and parts[1] == "tasks":
        return False

    epic_path = epic.meta.path.resolve()
    if resolved == epic_path:
        return True

    if op == "write":
        return _allow_write(resolved, parts, epic_id=epic_id, repo=repo)
    return _allow_read(resolved, parts, epic_id=epic_id, repo=repo)


def _walks_symlink(path: Path | str, root: Path) -> bool:
    """True if any path component under `root` is a symlink (do not follow)."""

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


def _allow_write(resolved: Path, parts: tuple[str, ...], *, epic_id: str, repo: Path) -> bool:
    if len(parts) >= 2 and parts[1] == "epics":
        return False

    if len(parts) >= 3 and parts[1] == "features" and parts[2] in ("2_active", "3_completed"):
        return False

    if len(parts) >= 3 and parts[1] == "features" and parts[2] == "1_backlog":
        if resolved.suffix.lower() != ".md":
            return False
        return _allow_backlog_feature_write(resolved, epic_id=epic_id, repo=repo)

    return False


def _allow_backlog_feature_write(resolved: Path, *, epic_id: str, repo: Path) -> bool:
    board = list_board(repo)
    work_id = filename_work_id(resolved)
    if work_id is not None and work_id in board.by_id:
        current = board.by_id[work_id]
        if current.path.resolve() != resolved:
            return False
        return current.parent == epic_id

    if resolved.is_file():
        try:
            doc = parse_doc(resolved)
        except Exception:
            return False
        if doc.meta.tier != "feature" or doc.meta.parent != epic_id:
            return False
        return _no_column_move(resolved, board)

    return True


def _allow_read(resolved: Path, parts: tuple[str, ...], *, epic_id: str, repo: Path) -> bool:
    if (
        len(parts) >= 4
        and parts[1] == "epics"
        and parts[2] == "2_active"
        and parts[3] == "_amendments"
        and resolved.suffix.lower() == ".md"
    ):
        return _allow_amendment_read(resolved, epic_id=epic_id, repo=repo)

    if len(parts) >= 2 and parts[1] == "epics":
        return False

    if len(parts) >= 3 and parts[1] == "features" and parts[2] in _FEATURE_COLUMNS:
        if not resolved.is_file() or resolved.suffix.lower() != ".md":
            return False
        try:
            doc = parse_doc(resolved)
        except Exception:
            return False
        return doc.meta.tier == "feature" and doc.meta.parent == epic_id

    return False


def _allow_amendment_read(resolved: Path, *, epic_id: str, repo: Path) -> bool:
    match = _AMENDMENT_FEAT_RE.search(resolved.name)
    if match is None:
        return False
    feature_id = match.group(0)
    try:
        doc = read_doc(feature_id, root=repo)
    except NotFound:
        return False
    return doc.meta.tier == "feature" and doc.meta.parent == epic_id


def _no_column_move(resolved: Path, board) -> bool:
    work_id = filename_work_id(resolved)
    if work_id is None or work_id not in board.by_id:
        return True
    return board.by_id[work_id].path.resolve() == resolved
