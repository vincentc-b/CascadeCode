"""Feature closeout and completion rollup (task_041)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.paths import column_for_status
from cascade.board.store import list_board, move_doc, read_doc, write_doc
from cascade.board.types import WorkId
from cascade.comments.store import read_comments
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event

_CLOSEOUT_HEADING = re.compile(r"^## Closeout\s*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"^## ", re.MULTILINE)


def write_closeout(feature_id: WorkId, paragraph: str, *, root: Path | None = None) -> str | None:
    """Ensure the feature doc has a ## Closeout section with ``paragraph``. Does not move columns."""

    repo = resolve_root(root)
    doc = read_doc(feature_id, root=repo)
    if doc.meta.tier != "feature":
        raise NotFound(feature_id)
    doc.body = _upsert_closeout_section(doc.body, paragraph)
    return write_doc(doc, root=repo)


def try_complete_feature(feature_id: WorkId, *, root: Path | None = None) -> bool:
    """Complete the feature when all rollup gates pass; otherwise return False with no side effects."""

    repo = resolve_root(root)
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    if feature_id not in board.by_id:
        return False
    feature_meta = board.by_id[feature_id]
    if feature_meta.tier != "feature":
        return False
    if (
        feature_meta.status == "completed"
        and feature_meta.path.parent.name == "3_completed"
    ):
        return True

    doc = read_doc(feature_id, root=repo)
    if not _rollup_gates_pass(feature_id, doc.body, board, repo):
        return False

    epic_id = doc.meta.parent
    if not epic_id:
        return False

    from cascade.boss.merge import merge_feature_branch

    from cascade.board.errors import GitError
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        git_root_for_path,
        locate_trunk,
    )

    trunk = locate_trunk(repo)
    feat_entry = get_integration_worktree(trunk, "feature", feature_id)
    if feat_entry is not None and feat_entry.path.is_dir():
        owner_root = feat_entry.path
    else:
        try:
            owner_root = git_root_for_path(doc.meta.path)
        except GitError:
            owner_root = repo
    merge_result = merge_feature_branch(feature_id, root=repo)
    if not merge_result.ok:
        return False
    move_doc(feature_id, "completed", root=owner_root)
    # The feat→epic merge leaves the feature spec on the epic worktree. An
    # active copy there outranks a completed copy on the feature worktree.
    epic_entry = get_integration_worktree(trunk, "epic", epic_id)
    if epic_entry is not None and epic_entry.path.is_dir():
        epic_meta = list_board(epic_entry.path).by_id.get(feature_id)
        if epic_meta is not None and column_for_status(epic_meta.status) != "completed":
            move_doc(feature_id, "completed", root=epic_entry.path)
    if owner_root.resolve() != trunk.resolve():
        trunk_board = list_board(trunk)
        meta = trunk_board.by_id.get(feature_id)
        if meta is not None and column_for_status(meta.status) != "completed":
            move_doc(feature_id, "completed", root=trunk)

    append_event(
        epic_id,
        Event(
            type="FeatureCompleted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id},
            dest=epic_id,
        ),
        root=repo,
    )
    return True


def on_task_merged(task_id: WorkId, *, root: Path | None = None) -> None:
    """After a task merge, attempt to complete its parent feature when gates already hold."""

    repo = resolve_root(root)
    try:
        task = read_doc(task_id, root=repo)
    except NotFound:
        return
    if task.meta.tier != "task":
        return
    parent_id = task.meta.parent
    if not parent_id:
        return
    try_complete_feature(parent_id, root=repo)


def _rollup_gates_pass(
    feature_id: WorkId,
    body: str,
    board,
    repo: Path,
) -> bool:
    if not _all_child_tasks_completed(feature_id, board):
        return False
    if _has_open_human_comments(feature_id, repo):
        return False
    if not _closeout_present(body):
        return False
    return True


def _child_task_ids(feature_id: WorkId, board) -> set[WorkId]:
    feature = board.by_id[feature_id]
    ids = set(feature.children)
    for meta in board.by_id.values():
        if meta.tier == "task" and meta.parent == feature_id:
            ids.add(meta.id)
    return ids


def _all_child_tasks_completed(feature_id: WorkId, board) -> bool:
    for task_id in _child_task_ids(feature_id, board):
        meta = board.by_id.get(task_id)
        if meta is None or meta.tier != "task":
            return False
        if meta.status != "completed":
            return False
        if column_for_status(meta.status) != "completed":
            return False
        if meta.path.parent.name != "3_completed":
            return False
    return True


def _has_open_human_comments(feature_id: WorkId, repo: Path) -> bool:
    for row in read_comments(feature_id, root=repo):
        if row.state == "open" and row.author == "human":
            return True
    return False


def _closeout_present(body: str) -> bool:
    return bool(_read_closeout_paragraph(body))


def _read_closeout_paragraph(body: str) -> str | None:
    match = _CLOSEOUT_HEADING.search(body)
    if match is None:
        return None
    rest = body[match.end() :]
    if rest.startswith("\r\n"):
        rest = rest[2:]
    elif rest.startswith("\n"):
        rest = rest[1:]
    next_match = _NEXT_SECTION.search(rest)
    section = rest[: next_match.start()] if next_match else rest
    text = section.strip()
    return text or None


def _upsert_closeout_section(body: str, paragraph: str) -> str:
    para = paragraph.strip()
    new_section = f"## Closeout\n\n{para}\n"
    match = _CLOSEOUT_HEADING.search(body)
    if match is not None:
        rest = body[match.end() :]
        next_match = _NEXT_SECTION.search(rest)
        if next_match is not None:
            tail_start = match.end() + next_match.start()
            return body[: match.start()] + new_section.rstrip() + "\n" + body[tail_start:]
        return body[: match.start()] + new_section
    trimmed = body.rstrip()
    if trimmed:
        return trimmed + "\n\n" + new_section
    return new_section
