"""Board scan, id allocation, and git-backed read/write/move."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import date
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import GitError, NotFound, SchemaError
from cascade.board.gitutil import (
    commit_paths,
    has_git,
    last_commit_touching,
    path_for_work_id,
    read_blob,
)
from cascade.board.lock import process_lock
from cascade.board.parse import parse_doc, parse_text, render_doc
from cascade.board.paths import column_dir, format_work_id, parse_work_id, status_for_column
from cascade.board.types import BoardIndex, Column, WorkDoc, WorkId, WorkTier
from cascade.board.validate import validate_doc

_COLUMNS = ("1_backlog", "2_active", "3_completed")
_TIER_DIRS = (("epic", "epics"), ("feature", "features"), ("task", "tasks"))
_reserved_ids: ContextVar[frozenset[str]] = ContextVar(
    "cascade_reserved_ids",
    default=frozenset(),
)


def reset_id_reservations() -> None:
    """Drop in-memory ids reserved by allocate_id. Tests isolate calls with this."""

    _reserved_ids.set(frozenset())


def list_board(root: Path) -> BoardIndex:
    """Scan `docs/{epics,features,tasks}/{column}` and index by id. No cache."""

    repo = Path(root).resolve()
    by_id = {}
    for _tier, dirname in _TIER_DIRS:
        for folder in _COLUMNS:
            directory = repo / "docs" / dirname / folder
            if not directory.is_dir():
                continue
            for path in sorted(directory.glob("*.md")):
                if path.is_symlink() or not path.is_file():
                    continue
                try:
                    doc = parse_doc(path)
                except (SchemaError, OSError, UnicodeDecodeError):
                    continue
                if doc.meta.id in by_id:
                    other = by_id[doc.meta.id].path
                    raise SchemaError(f"duplicate id {doc.meta.id} at {path} and {other}")
                by_id[doc.meta.id] = doc.meta
    return BoardIndex(by_id=by_id)


def allocate_id(tier: WorkTier, board: BoardIndex) -> WorkId:
    """Next free NNN for `tier`. Numbers present on the board or reserved are not reused."""

    reserved = set(_reserved_ids.get())
    used: set[int] = set()
    for work_id in list(board.by_id) + list(reserved):
        try:
            found_tier, number = parse_work_id(work_id)
        except SchemaError:
            continue
        if found_tier == tier:
            used.add(number)
    number = 1
    while number in used:
        number += 1
    work_id = format_work_id(tier, number)
    reserved.add(work_id)
    _reserved_ids.set(frozenset(reserved))
    return work_id


def write_doc(doc: WorkDoc, *, root: Path | None = None) -> str | None:
    """Validate, write the file, and commit only that file.

    Returns the commit SHA. Returns None when `root` is not a git repository.
    Does not create the repository. If the repo exists but the commit fails,
    the file is already on disk and GitError is raised.
    """

    with process_lock:
        return _write_doc(doc, root)


def _write_doc(doc: WorkDoc, root: Path | None) -> str | None:
    repo = resolve_root(root, doc.meta.path)
    path = doc.meta.path
    if not path.is_absolute():
        path = repo / path
    doc.meta.path = path.resolve()
    doc.meta.updated = date.today()
    from cascade.workspace.integration_worktree import (
        invalidate_merged_board,
        locate_trunk,
        merged_board,
    )

    board = merged_board(locate_trunk(repo))
    validate_doc(doc, board)
    doc.meta.path.parent.mkdir(parents=True, exist_ok=True)
    doc.meta.path.write_text(render_doc(doc), encoding="utf-8")
    invalidate_merged_board(locate_trunk(repo))
    sha = commit_paths(repo, [doc.meta.path], f"docs: {doc.meta.id} {doc.meta.title}")
    doc.sha = sha
    return sha


def move_doc(work_id: WorkId, dest_column: Column, *, root: Path | None = None) -> str | None:
    """Rename into the destination column and set that column's default status.

    Does not check dispatch authority. Validation runs before the file moves.
    Commit message matches write_doc. Returns the SHA, or None when there is no git repo.
    """

    if dest_column not in ("backlog", "active", "completed"):
        raise SchemaError(f"unknown column: {dest_column!r}")
    with process_lock:
        return _move_doc(work_id, dest_column, root)


def _move_doc(work_id: WorkId, dest_column: Column, root: Path | None) -> str | None:
    from cascade.workspace.integration_worktree import doc_filesystem_root, is_trunk_pointer

    repo = resolve_root(root)
    trunk_board = list_board(repo)
    if work_id in trunk_board.by_id and is_trunk_pointer(trunk_board.by_id[work_id]):
        repo = doc_filesystem_root(work_id, trunk=repo)
    elif work_id not in trunk_board.by_id:
        try:
            repo = doc_filesystem_root(work_id, trunk=repo)
        except NotFound:
            pass
    from cascade.workspace.integration_worktree import (
        invalidate_merged_board,
        locate_trunk,
        merged_board,
    )

    board = list_board(repo)
    if work_id not in board.by_id:
        raise NotFound(work_id)
    current = board.by_id[work_id]
    doc = parse_doc(current.path)
    new_path = (repo / column_dir(doc.meta.tier, dest_column) / current.path.name).resolve()
    old_path = current.path.resolve()
    doc.meta.status = status_for_column(dest_column)
    doc.meta.path = new_path
    doc.meta.updated = date.today()
    validate_doc(doc, merged_board(locate_trunk(repo)))
    if new_path != old_path and new_path.exists():
        raise SchemaError(f"destination already exists: {new_path}")
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(render_doc(doc), encoding="utf-8")
    if new_path != old_path and old_path.exists():
        old_path.unlink()
    invalidate_merged_board(locate_trunk(repo))
    paths = [new_path] if new_path == old_path else [old_path, new_path]
    sha = commit_paths(repo, paths, f"docs: {doc.meta.id} {doc.meta.title}")
    doc.sha = sha
    return sha


def save_doc(doc: WorkDoc, *, previous_path: Path, root: Path | None = None) -> str | None:
    """Write `doc` at `doc.meta.path` and drop `previous_path` when it differs.

    One commit. A GitError restores the previous bytes so a failed transition
    does not leave a new skills list on disk. Holds `process_lock`.
    """

    with process_lock:
        return _save_doc(doc, previous_path, root)


def _save_doc(doc: WorkDoc, previous_path: Path, root: Path | None) -> str | None:
    repo = resolve_root(root, doc.meta.path)
    new_path = doc.meta.path if doc.meta.path.is_absolute() else repo / doc.meta.path
    new_path = new_path.resolve()
    previous = previous_path.resolve()
    doc.meta.path = new_path
    doc.meta.updated = date.today()
    from cascade.workspace.integration_worktree import (
        invalidate_merged_board,
        locate_trunk,
        merged_board,
    )

    board = merged_board(locate_trunk(repo))
    validate_doc(doc, board)
    if new_path != previous and new_path.exists():
        raise SchemaError(f"destination already exists: {new_path}")
    previous_bytes = previous.read_bytes() if previous.exists() else None
    new_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        new_path.write_text(render_doc(doc), encoding="utf-8")
        if new_path != previous and previous.exists():
            previous.unlink()
        invalidate_merged_board(locate_trunk(repo))
        paths = [new_path] if new_path == previous else [previous, new_path]
        sha = commit_paths(repo, paths, f"docs: {doc.meta.id} {doc.meta.title}")
    except Exception:
        if new_path != previous and new_path.exists():
            new_path.unlink()
        if previous_bytes is not None:
            previous.parent.mkdir(parents=True, exist_ok=True)
            previous.write_bytes(previous_bytes)
        invalidate_merged_board(locate_trunk(repo))
        raise
    doc.sha = sha
    return sha


def read_doc_in_worktree(
    work_id: WorkId,
    worktree_root: Path,
    rev: str | None = None,
) -> WorkDoc:
    """Read ``work_id`` from a single checkout root (no supervisor merge lookup)."""

    repo = resolve_root(worktree_root)
    if rev is not None:
        if not has_git(repo):
            raise GitError("cannot read a revision without a git repository")
        rel = path_for_work_id(repo, rev, work_id)
        if rel is None:
            raise NotFound(work_id)
        text = read_blob(repo, rev, rel)
        doc = parse_text(text, repo / rel)
        doc.sha = rev
        return doc
    board = list_board(repo)
    if work_id not in board.by_id:
        raise NotFound(work_id)
    path = board.by_id[work_id].path
    rel = path.resolve().relative_to(repo.resolve()).as_posix()
    doc = parse_doc(path)
    doc.sha = last_commit_touching(repo, Path(rel)) if has_git(repo) else None
    return doc


def read_doc(work_id: WorkId, rev: str | None = None, *, root: Path | None = None) -> WorkDoc:
    """Read the working tree, or the blob of `{id}_*.md` inside `rev`."""

    repo = resolve_root(root)
    if rev is not None:
        if not has_git(repo):
            raise GitError("cannot read a revision without a git repository")
        rel = path_for_work_id(repo, rev, work_id)
        if rel is None:
            raise NotFound(work_id)
        text = read_blob(repo, rev, rel)
        doc = parse_text(text, repo / rel)
        doc.sha = rev
        return doc
    from cascade.workspace.integration_worktree import doc_filesystem_root, is_trunk_pointer

    board = list_board(repo)
    if work_id in board.by_id and is_trunk_pointer(board.by_id[work_id]):
        doc_root = doc_filesystem_root(work_id, trunk=repo)
    elif work_id in board.by_id:
        doc_root = repo
    else:
        try:
            doc_root = doc_filesystem_root(work_id, trunk=repo)
        except NotFound:
            raise NotFound(work_id) from None
    board = list_board(doc_root)
    if work_id not in board.by_id:
        raise NotFound(work_id)
    path = board.by_id[work_id].path
    rel = path.resolve().relative_to(doc_root.resolve()).as_posix()
    doc = parse_doc(path)
    doc.sha = last_commit_touching(doc_root, Path(rel)) if has_git(doc_root) else None
    return doc


def pin_parent(
    child_id: WorkId,
    parent_id: WorkId,
    *,
    root: Path | None = None,
) -> str | None:
    """Set child.parent_rev to the parent's last commit SHA, or null if it has none."""

    repo = resolve_root(root)
    board = list_board(repo)
    if child_id not in board.by_id:
        raise NotFound(child_id)
    if parent_id not in board.by_id:
        raise NotFound(parent_id)
    parent_path = board.by_id[parent_id].path.resolve()
    rel = parent_path.relative_to(repo.resolve())
    sha = last_commit_touching(repo, rel) if has_git(repo) else None
    child = read_doc(child_id, root=repo)
    child.meta.parent_rev = sha
    return write_doc(child, root=repo)
