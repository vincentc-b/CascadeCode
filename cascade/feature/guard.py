"""Path sandbox for Feature Team read/write tools."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.parse import parse_doc
from cascade.board.paths import filename_work_id
from cascade.board.store import list_board, read_doc

_TASK_COLUMNS = ("1_backlog", "2_active", "3_completed")
_FEATURE_COLUMNS = ("1_backlog", "2_active", "3_completed")


class FeatureToolDenied(PermissionError):
    """Feature team is not allowed to access this path or work id."""


def tool_guard(path: Path | str, op: str, *, feature_id: str, root: Path) -> bool:
    """Return whether the Feature graph may read or write `path` relative to `root`."""

    if op not in ("read", "write"):
        return False

    repo = Path(root).resolve()
    try:
        feature = read_doc(feature_id, root=repo)
    except NotFound:
        return False
    if feature.meta.tier != "feature":
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

    feature_path = feature.meta.path.resolve()
    if resolved == feature_path:
        return True

    if op == "write":
        return _allow_write(resolved, parts, feature_id=feature_id, repo=repo)
    return _allow_read(resolved, parts, feature=feature, feature_id=feature_id, repo=repo)


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


def _own_comment_sidecar(feature_id: str, repo: Path) -> Path:
    return (repo / "docs" / "_comments" / f"{feature_id}.jsonl").resolve()


def _allow_write(
    resolved: Path, parts: tuple[str, ...], *, feature_id: str, repo: Path
) -> bool:
    if len(parts) >= 2 and parts[1] == "epics":
        return False

    if len(parts) >= 2 and parts[1] in ("_queue", "_war_room", "_amendments"):
        return False

    if len(parts) >= 2 and parts[1] == "_comments":
        return resolved == _own_comment_sidecar(feature_id, repo)

    if len(parts) >= 3 and parts[1] == "features":
        return False

    if len(parts) >= 3 and parts[1] == "tasks":
        if parts[2] != "1_backlog":
            return False
        return _allow_backlog_task_write(resolved, feature_id=feature_id, repo=repo)

    return False


def _allow_backlog_task_write(resolved: Path, *, feature_id: str, repo: Path) -> bool:
    if resolved.suffix.lower() != ".md":
        return False

    board = list_board(repo)
    work_id = filename_work_id(resolved)
    if work_id is not None and work_id in board.by_id:
        current = board.by_id[work_id]
        if current.path.resolve() != resolved:
            return False
        return current.parent == feature_id

    if resolved.is_file():
        try:
            doc = parse_doc(resolved)
        except Exception:
            return False
        if doc.meta.tier != "task" or doc.meta.parent != feature_id:
            return False
        return _no_column_move(resolved, board)

    return True


def _allow_read(
    resolved: Path,
    parts: tuple[str, ...],
    *,
    feature,
    feature_id: str,
    repo: Path,
) -> bool:
    if len(parts) >= 2 and parts[1] in ("_war_room", "_queue", "_amendments"):
        return False

    if len(parts) >= 2 and parts[1] == "_comments":
        return resolved == _own_comment_sidecar(feature_id, repo)

    if len(parts) >= 2 and parts[1] == "epics":
        return _allow_parent_epic_read(resolved, feature=feature, repo=repo)

    if len(parts) >= 3 and parts[1] == "features" and parts[2] in _FEATURE_COLUMNS:
        return False

    if len(parts) >= 3 and parts[1] == "tasks" and parts[2] in _TASK_COLUMNS:
        if not resolved.is_file() or resolved.suffix.lower() != ".md":
            return False
        try:
            doc = parse_doc(resolved)
        except Exception:
            return False
        return doc.meta.tier == "task" and doc.meta.parent == feature_id

    return False


def _allow_parent_epic_read(resolved: Path, *, feature, repo: Path) -> bool:
    parent_id = feature.meta.parent
    if parent_id is None:
        return False
    try:
        parent = read_doc(parent_id, root=repo)
    except NotFound:
        return False
    if parent.meta.tier != "epic":
        return False
    return resolved == parent.meta.path.resolve()


def _no_column_move(resolved: Path, board) -> bool:
    work_id = filename_work_id(resolved)
    if work_id is None or work_id not in board.by_id:
        return True
    return board.by_id[work_id].path.resolve() == resolved
