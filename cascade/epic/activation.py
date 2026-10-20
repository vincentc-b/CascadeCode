"""Epic activation: trunk pointer and live spec on the epic integration worktree."""

from __future__ import annotations

from pathlib import Path

from cascade.board.gitutil import commit_paths, has_git
from cascade.board.paths import column_dir
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc
from cascade.workspace.integration_worktree import IntegrationWorktree

_POINTER_BODY = """\
# {title}

## Intent

Live epic spec is on branch `{branch}` (worktree `{worktree}`). Edit there, not on the product trunk.

## Macro-architecture

_(see integration worktree)_

## Cross-module constraints

_(see integration worktree)_

## Core dependencies

_(see integration worktree)_

## Feature breakdown

_(see integration worktree)_

## Open questions

_(see integration worktree)_

## Decision log

_(see integration worktree)_

## Amendment log

_(see integration worktree)_
"""


def activate_epic_on_worktree(
    work_id: str,
    *,
    trunk: Path,
    epic_wt: IntegrationWorktree,
) -> None:
    """Move the live epic doc into the epic worktree; leave a trunk pointer."""

    live_root = epic_wt.path
    doc = read_doc(work_id, root=trunk)
    old_path = doc.meta.path.resolve()

    live = WorkDoc(meta=doc.meta, body=doc.body, sha=None)
    live.meta.status = "active"
    live.meta.path = (live_root / column_dir("epic", "active") / old_path.name).resolve()
    # Drop the branch's backlog copy first: feature parent_rev pins the commit that
    # last touched the live path, and that commit must hold exactly one epic copy.
    _drop_stale_copies(work_id, tier="epic", keep=live.meta.path, board_root=live_root)
    write_doc(live, root=live_root)
    _scrub_child_specs(live_root)

    if old_path.exists():
        old_path.unlink()

    rel_wt = epic_wt.path.relative_to(trunk.resolve()).as_posix()
    pointer = WorkDoc(
        meta=doc.meta,
        body=_POINTER_BODY.format(
            title=doc.meta.title,
            branch=epic_wt.branch,
            worktree=rel_wt,
        ),
        sha=None,
    )
    pointer.meta.status = "active"
    pointer.meta.integration_branch = epic_wt.branch
    pointer.meta.integration_worktree = rel_wt
    pointer.meta.path = (
        trunk / "docs" / "epics" / "2_active" / doc.meta.path.name
    ).resolve()
    write_doc(pointer, root=trunk)
    if has_git(trunk) and old_path != pointer.meta.path.resolve():
        commit_paths(trunk, [old_path], f"docs: {work_id} trunk pointer")


def _drop_stale_copies(
    work_id: str,
    *,
    tier: str,
    keep: Path,
    board_root: Path,
) -> None:
    """Remove duplicate tier docs outside the kept path (branch checkout copies)."""

    keep_resolved = keep.resolve()
    removed: list[Path] = []
    from cascade.board.types import WorkTier

    tier_name: WorkTier = tier  # type: ignore[assignment]
    for column in ("backlog", "active", "completed"):
        folder = board_root / column_dir(tier_name, column)
        if not folder.is_dir():
            continue
        for path in folder.glob(f"{work_id}_*.md"):
            if path.resolve() == keep_resolved:
                continue
            path.unlink()
            removed.append(path)
    if removed and has_git(board_root):
        commit_paths(board_root, removed, f"docs: drop stale copies of {work_id}")


def _scrub_child_specs(epic_root: Path) -> None:
    """Drop feature/task markdown copied onto the epic branch checkout."""

    removed: list[Path] = []
    for dirname in ("features", "tasks"):
        for column in ("1_backlog", "2_active", "3_completed"):
            folder = epic_root / "docs" / dirname / column
            if not folder.is_dir():
                continue
            for path in folder.glob("*.md"):
                path.unlink()
                removed.append(path)
    if removed and has_git(epic_root):
        commit_paths(epic_root, removed, "docs: scrub child specs from epic worktree")
