"""Board scan, id allocation, and git-backed read/write/move."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from contextvars import ContextVar
from collections import OrderedDict
from copy import copy, deepcopy
from datetime import date
from pathlib import Path
from threading import RLock

from cascade.board.context import (
    resolve_root,
    resolve_tracking_root,
    route_planning_path,
)
from cascade.board.errors import GitError, GitSynchronizationError, NotFound, SchemaError
from cascade.board.gitutil import (
    commit_paths,
    has_git,
    last_commit_touching,
    path_for_work_id,
    read_blob,
)
from cascade.board.id_reservations import reset_id_reservations as reset_id_reservations
from cascade.board.lock import process_lock
from cascade.board.parse import parse_doc, parse_text, render_doc
from cascade.board.paths import column_dir, status_for_column
from cascade.board.types import BoardIndex, Column, WorkDoc, WorkId, WorkMeta, WorkTier
from cascade.board.validate import validate_doc
from cascade.board.work_ids import allocate_hierarchical_id

_COLUMNS = ("1_backlog", "2_active", "3_completed")
_TIER_DIRS = (("epic", "epics"), ("feature", "features"), ("task", "tasks"))
_SCAN_META_CACHE_LIMIT = 8192
_scan_meta_cache: OrderedDict[Path, tuple[tuple[int, ...], WorkMeta]] = OrderedDict()
_scan_meta_cache_lock = RLock()
_board_scan_snapshot: ContextVar[dict[Path, BoardIndex] | None] = ContextVar(
    "board_scan_snapshot", default=None
)


@contextmanager
def board_scan_snapshot():
    """Reuse board scans within one read-only response, never across requests."""

    token = _board_scan_snapshot.set({})
    try:
        yield
    finally:
        _board_scan_snapshot.reset(token)


def _copy_meta(meta: WorkMeta) -> WorkMeta:
    """Copy mutable frontmatter without recursively copying immutable values."""

    result = copy(meta)
    for name in ("children", "depends_on", "owners", "skills", "cites", "monitoring_blockers"):
        setattr(result, name, list(getattr(meta, name)))
    # Cancellation feedback contains a mutable list of available dispositions.
    result.cancellation_feedback = deepcopy(meta.cancellation_feedback)
    for name in ("models", "reasoning"):
        value = getattr(meta, name)
        if value is not None:
            setattr(result, name, value.copy())
    return result


def _scan_meta(path: Path) -> WorkMeta:
    """Reuse unchanged frontmatter without sharing mutable metadata between scans."""

    stat = path.stat()
    version = (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
    with _scan_meta_cache_lock:
        cached = _scan_meta_cache.get(path)
        if cached is not None and cached[0] == version:
            _scan_meta_cache.move_to_end(path)
            return _copy_meta(cached[1])

    meta = parse_doc(path).meta
    # A concurrent writer can replace the file during parsing. Return this
    # scan's result, but cache it only if its identity is still unchanged.
    after = path.stat()
    if version == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        with _scan_meta_cache_lock:
            _scan_meta_cache[path] = (version, _copy_meta(meta))
            _scan_meta_cache.move_to_end(path)
            if len(_scan_meta_cache) > _SCAN_META_CACHE_LIMIT:
                _scan_meta_cache.popitem(last=False)
    return meta


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a same-directory temp file and ``os.replace``."""

    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def list_board(root: Path) -> BoardIndex:
    """Scan board directories, reusing frontmatter from unchanged files."""

    repo = resolve_tracking_root(root)
    snapshot = _board_scan_snapshot.get()
    if snapshot is not None and repo in snapshot:
        return snapshot[repo]
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
                    meta = _scan_meta(path)
                except (SchemaError, OSError, UnicodeDecodeError):
                    continue
                if meta.id in by_id:
                    other = by_id[meta.id].path
                    raise SchemaError(f"duplicate id {meta.id} at {path} and {other}")
                by_id[meta.id] = meta
    board = BoardIndex(by_id=by_id)
    if snapshot is not None:
        snapshot[repo] = board
    return board


def allocate_id(
    tier: WorkTier,
    board: BoardIndex,
    *,
    parent_id: str | None = None,
) -> WorkId:
    """Next canonical hierarchical id for ``tier``, scoped to ``parent_id`` when required."""

    return allocate_hierarchical_id(tier, board, parent_id=parent_id)


def _reject_new_doc_id_collision(doc: WorkDoc, board: BoardIndex, repo: Path) -> None:
    """Reject a second create for ``doc.meta.id`` in the same checkout."""

    if doc.meta.path.exists() or doc.meta.id not in board.by_id:
        return
    existing = board.by_id[doc.meta.id]
    if existing.path.resolve() == doc.meta.path.resolve():
        return
    from cascade.workspace.integration_worktree import git_root_for_path

    if has_git(repo):
        existing_root = git_root_for_path(existing.path.resolve())
        new_root = git_root_for_path(doc.meta.path.resolve())
        if existing_root.resolve() != new_root.resolve():
            return
    raise SchemaError(f"id collision: {doc.meta.id}")


def write_doc(doc: WorkDoc, *, root: Path | None = None) -> str | None:
    """Validate, write the file, and commit only that file.

    Returns the commit SHA. Returns None when `root` is not a git repository.
    Does not create the repository. If the repo exists but the commit fails,
    the previous on-disk state is restored and GitError is raised.
    """

    with process_lock:
        return _write_doc(doc, root)


def _write_doc(doc: WorkDoc, root: Path | None) -> str | None:
    requested_repo = resolve_root(root, doc.meta.path)
    repo = resolve_tracking_root(root, doc.meta.path)
    doc.meta.path = route_planning_path(
        doc.meta.path,
        requested_root=requested_repo,
        tracking_root=repo,
    )
    doc.meta.updated = date.today()
    from cascade.workspace.integration_worktree import (
        git_root_for_path,
        invalidate_merged_board,
        locate_trunk,
        merged_board,
    )

    trunk = locate_trunk(repo)
    # Collisions are per-checkout; merged_board also indexes other worktrees and snapshots.
    _reject_new_doc_id_collision(doc, list_board(repo), repo)
    validate_doc(doc, merged_board(trunk))
    if doc.meta.path.exists() and doc.sha is not None and has_git(repo):
        rel = doc.meta.path.resolve().relative_to(repo.resolve())
        current_sha = last_commit_touching(repo, rel)
        if current_sha is not None and current_sha != doc.sha:
            raise SchemaError(
                f"stale sha for {doc.meta.id}: document changed since read (expected {doc.sha})"
            )
    previous_bytes = doc.meta.path.read_bytes() if doc.meta.path.exists() else None
    rendered = render_doc(doc)
    _atomic_write_text(doc.meta.path, rendered)
    invalidate_merged_board(trunk)
    commit_root = git_root_for_path(doc.meta.path) if has_git(repo) else repo
    try:
        sha = commit_paths(
            commit_root,
            [doc.meta.path],
            f"docs: {doc.meta.id} {doc.meta.title}",
        )
    except GitSynchronizationError:
        # The document is already committed locally.  Preserve that exact state
        # so startup or an idempotent retry can synchronize it later.
        invalidate_merged_board(trunk)
        raise
    except GitError:
        if previous_bytes is None:
            doc.meta.path.unlink(missing_ok=True)
        else:
            doc.meta.path.write_bytes(previous_bytes)
        invalidate_merged_board(trunk)
        raise
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

    repo = resolve_tracking_root(root)
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
    if dest_column == "completed" and doc.meta.tier == "feature":
        from cascade.stacked_dispatch import refusal_if_feature_completion_without_pr

        if refusal := refusal_if_feature_completion_without_pr(doc.meta.id, root=repo):
            raise SchemaError(refusal)
    validate_doc(doc, merged_board(locate_trunk(repo)))
    if new_path != old_path and new_path.exists():
        raise SchemaError(f"destination already exists: {new_path}")
    _atomic_write_text(new_path, render_doc(doc))
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
    requested_repo = resolve_root(root, doc.meta.path)
    repo = resolve_tracking_root(root, doc.meta.path)
    new_path = route_planning_path(
        doc.meta.path,
        requested_root=requested_repo,
        tracking_root=repo,
    )
    previous = route_planning_path(
        previous_path,
        requested_root=requested_repo,
        tracking_root=repo,
    )
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
        _atomic_write_text(new_path, render_doc(doc))
        if new_path != previous and previous.exists():
            previous.unlink()
        invalidate_merged_board(locate_trunk(repo))
        paths = [new_path] if new_path == previous else [previous, new_path]
        sha = commit_paths(repo, paths, f"docs: {doc.meta.id} {doc.meta.title}")
    except GitSynchronizationError:
        invalidate_merged_board(locate_trunk(repo))
        raise
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

    repo = resolve_tracking_root(worktree_root)
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

    repo = resolve_tracking_root(root)
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

    repo = resolve_tracking_root(root)
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
