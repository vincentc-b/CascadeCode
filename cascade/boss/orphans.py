"""Flag inconsistent parent/column relationships on the board (no repair)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.context import resolve_root
from cascade.board.store import list_board
from cascade.board.types import BoardIndex, WorkId, WorkMeta

OrphanKind = Literal[
    "feature_without_parent",
    "task_after_feature_completed",
    "epic_with_active_child",
]

_TOAST_KIND = "orphan"
_ACTIVE_CHILD_FOLDERS = frozenset({"1_backlog", "2_active"})


@dataclass(frozen=True)
class OrphanRecord:
    kind: OrphanKind
    work_id: WorkId
    message: str
    toast_payload: dict[str, str]


def detect_orphans(*, root: Path | None = None) -> list[OrphanRecord]:
    """Return orphan flags for the current board index. Does not move or repair docs."""

    repo = resolve_root(root)
    board = list_board(repo)
    if not board.by_id:
        return []

    out: list[OrphanRecord] = []
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.tier == "feature":
            record = _feature_without_parent(meta, board)
            if record is not None:
                out.append(record)
        elif meta.tier == "task":
            record = _task_after_feature_completed(meta, board)
            if record is not None:
                out.append(record)
        elif meta.tier == "epic":
            record = _epic_with_active_child(meta, board)
            if record is not None:
                out.append(record)
    return out


def _feature_without_parent(meta: WorkMeta, board: BoardIndex) -> OrphanRecord | None:
    if not meta.parent or meta.parent not in board.by_id:
        if meta.parent and meta.parent not in board.by_id:
            detail = f"parent {meta.parent} is not on the board"
        else:
            detail = "parent is missing or empty"
        message = f"{meta.id} feature without valid parent: {detail}"
        return _record("feature_without_parent", meta.id, message)
    return None


def _task_after_feature_completed(meta: WorkMeta, board: BoardIndex) -> OrphanRecord | None:
    if meta.status == "completed":
        return None
    parent_id = meta.parent
    if not parent_id:
        return None
    parent = board.by_id.get(parent_id)
    if parent is None or parent.tier != "feature":
        return None
    if parent.path.parent.name != "3_completed":
        return None
    message = (
        f"{meta.id} is not completed while parent feature {parent_id} "
        "is already in 3_completed"
    )
    return _record("task_after_feature_completed", meta.id, message)


def _child_feature_ids(epic_id: WorkId, board: BoardIndex) -> set[WorkId]:
    epic = board.by_id[epic_id]
    ids = set(epic.children)
    for child in board.by_id.values():
        if child.tier == "feature" and child.parent == epic_id:
            ids.add(child.id)
    return ids


def _epic_with_active_child(meta: WorkMeta, board: BoardIndex) -> OrphanRecord | None:
    if meta.path.parent.name != "3_completed":
        return None
    active_children = sorted(
        child_id
        for child_id in _child_feature_ids(meta.id, board)
        if (child := board.by_id.get(child_id)) is not None
        and child.tier == "feature"
        and child.path.parent.name in _ACTIVE_CHILD_FOLDERS
    )
    if not active_children:
        return None
    joined = ", ".join(active_children)
    message = (
        f"{meta.id} is in 3_completed but child feature(s) still active: {joined}"
    )
    return _record("epic_with_active_child", meta.id, message)


def _record(kind: OrphanKind, work_id: WorkId, message: str) -> OrphanRecord:
    return OrphanRecord(
        kind=kind,
        work_id=work_id,
        message=message,
        toast_payload={
            "kind": _TOAST_KIND,
            "id": work_id,
            "message": message,
        },
    )
