"""Resolve which integration worktree owns War Room doc reads (task_067)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc, read_doc_in_worktree
from cascade.board.types import WorkId
from cascade.workspace.integration_worktree import (
    IntegrationKind,
    get_integration_worktree,
    is_trunk_pointer,
    merged_board,
    repair_missing_worktree,
)

BACKLOG_FEATURE_ATTACH_MESSAGE = "dispatch the feature to open its room"


def resolve_doc_worktree(work_id: WorkId, *, root: Path) -> Path:
    """Return the checkout root for ``work_id`` specs (View plan / Attach reads).

    Does not create worktrees.
    """

    trunk = Path(root).resolve()
    board = merged_board(trunk)
    if work_id not in board.by_id:
        raise NotFound(work_id)
    meta = board.by_id[work_id]
    tier = meta.tier

    if tier == "epic":
        if meta.path.parent.name == "1_backlog" and not is_trunk_pointer(meta):
            return trunk
        epic_root = _registered_worktree_path(trunk, "epic", work_id)
        if epic_root is not None:
            return epic_root
        if "/worktrees/epic_" in meta.path.as_posix():
            from cascade.workspace.integration_worktree import git_root_for_path

            return git_root_for_path(meta.path)
        return trunk

    if tier == "feature":
        feat_root = _registered_worktree_path(trunk, "feature", work_id)
        if feat_root is not None:
            return feat_root
        parent = meta.parent
        if not parent:
            return trunk
        return resolve_doc_worktree(parent, root=trunk)

    if tier == "task":
        parent = meta.parent
        if not parent:
            raise NotFound(work_id)
        return resolve_doc_worktree(parent, root=trunk)

    raise NotFound(work_id)


def read_doc_resolved(work_id: WorkId, *, root: Path):
    """Read ``work_id`` preferring the integration worktree from ``resolve_doc_worktree``.

    Child specs may still live on trunk (or another checkout) until dispatch relocates
    them; fall back to ``doc_filesystem_root`` when the preferred tree has no copy.
    """

    from cascade.workspace.integration_worktree import doc_filesystem_root

    trunk = Path(root).resolve()
    preferred = resolve_doc_worktree(work_id, root=trunk)
    if preferred.resolve() == trunk:
        return read_doc(work_id, root=trunk)
    try:
        return read_doc_in_worktree(work_id, preferred)
    except NotFound:
        pass
    fs_root = doc_filesystem_root(work_id, trunk=trunk)
    if fs_root.resolve() == preferred.resolve():
        raise NotFound(work_id)
    if fs_root.resolve() == trunk.resolve():
        return read_doc(work_id, root=trunk)
    return read_doc_in_worktree(work_id, fs_root)


def is_backlog_feature_attach_refused(work_id: WorkId, *, root: Path) -> bool:
    """True when Attach must refuse a backlog feature with no ``feat/{id}`` worktree."""

    trunk = Path(root).resolve()
    board = merged_board(trunk)
    meta = board.by_id.get(work_id)
    if meta is None or meta.tier != "feature":
        return False
    if meta.path.parent.name != "1_backlog":
        return False
    return _registered_worktree_path(trunk, "feature", work_id) is None


def repair_doc_worktree_for_attach(work_id: WorkId, *, root: Path) -> None:
    """Recreate a missing integration directory for epic/feature attach (no dispatch)."""

    trunk = Path(root).resolve()
    board = merged_board(trunk)
    meta = board.by_id.get(work_id)
    if meta is None:
        return
    if meta.tier == "epic":
        if _registered_worktree_path(trunk, "epic", work_id) is None:
            return
        repair_missing_worktree("epic", work_id, trunk=trunk)
        return
    if meta.tier == "feature":
        if _registered_worktree_path(trunk, "feature", work_id) is None:
            return
        repair_missing_worktree("feature", work_id, trunk=trunk)


def _registered_worktree_path(
    trunk: Path,
    kind: IntegrationKind,
    work_id: str,
) -> Path | None:
    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is not None:
        return entry.path.resolve()
    return None
