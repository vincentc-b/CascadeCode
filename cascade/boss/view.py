"""Read-only BossView over the board: dispatchable work, slots, and failures."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.workspace.integration_worktree import merged_board
from cascade.board.types import BoardIndex, WorkMeta, WorkId
from cascade.watchdog.config import task_parallelism

_OPEN = {"backlog", "ready_to_plan"}


@dataclass(frozen=True)
class BossView:
    dispatchable_features: list[WorkId]
    dispatchable_tasks: list[WorkId]
    slots_free: int
    failed_tasks: list[WorkId]


def compute_boss_view(*, root: Path | None = None) -> BossView:
    """Inspect the board without dispatching. Cap and dependency rules match dispatch law."""

    repo = resolve_root(root)
    board = merged_board(repo)
    active = _active_task_count(board)
    cap = task_parallelism(repo)
    slots_free = max(0, cap - active)
    at_cap = active >= cap

    dispatchable_features: list[WorkId] = []
    dispatchable_tasks: list[WorkId] = []
    failed_tasks: list[WorkId] = []
    from cascade.feature.readiness import compute_feature_readiness, feature_boss_dispatchable

    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.tier == "feature" and _backlog_open(meta) and meta.parent:
            readiness = compute_feature_readiness(work_id, root=repo, board=board)
            if readiness is not None and feature_boss_dispatchable(readiness):
                dispatchable_features.append(work_id)
        elif meta.tier == "task":
            if meta.status == "blocked" and meta.path.parent.name == "2_active":
                failed_tasks.append(work_id)
            elif (
                _backlog_open(meta)
                and meta.parent
                and _deps_met(board, meta, root=repo)
                and not _parent_cancellation_gated(board, meta)
                and not at_cap
            ):
                dispatchable_tasks.append(work_id)

    return BossView(
        dispatchable_features=dispatchable_features,
        dispatchable_tasks=dispatchable_tasks,
        slots_free=slots_free,
        failed_tasks=failed_tasks,
    )


def _backlog_open(meta: WorkMeta) -> bool:
    return meta.status in _OPEN and meta.path.parent.name == "1_backlog"


def _parent_cancellation_gated(board: BoardIndex, meta: WorkMeta) -> bool:
    if not meta.parent:
        return False
    parent = board.by_id.get(meta.parent)
    if parent is None:
        return False
    return any(
        item.disposition is None for item in parent.cancellation_feedback
    )


def _deps_met(board: BoardIndex, meta: WorkMeta, *, root: Path) -> bool:
    if meta.tier == "feature" and meta.parent:
        from cascade.stacked_dispatch import feature_dependency_ready

        return feature_dependency_ready(meta, board, root=root)
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is None or dep.status != "completed" or dep.path.parent.name != "3_completed":
            return False
        if dep.tier == "feature":
            from cascade.review import feature_review_pending

            if feature_review_pending(dep_id, root=root):
                return False
    return True


def _active_task_count(board: BoardIndex) -> int:
    count = 0
    for meta in board.by_id.values():
        if meta.tier == "task" and meta.status == "active" and meta.path.parent.name == "2_active":
            count += 1
    return count
