"""Authoritative lifecycle evaluation for declared work dependencies."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.context import resolve_tracking_root
from cascade.board.paths import legal_folder
from cascade.board.types import BoardIndex, WorkMeta, WorkStatus, WorkTier
from cascade.workspace.integration_worktree import merged_board

DependencyOutcome = Literal[
    "satisfied",
    "dependency_unmet",
    "dependency_status_unavailable",
]
DependencyReason = Literal[
    "dependency_incomplete",
    "dependency_cancelled",
    "dependency_status_column_mismatch",
    "dependency_not_found",
    "dependency_source_unavailable",
]


@dataclass(frozen=True)
class DependencyStatus:
    """Safe canonical lifecycle facts for one declared dependency."""

    work_id: str
    tier: WorkTier | None
    status: WorkStatus | None
    column: str | None
    outcome: DependencyOutcome
    reason: DependencyReason | None

    @property
    def complete(self) -> bool:
        return self.outcome == "satisfied"


@dataclass(frozen=True)
class DependencyEvaluation:
    """Ordered evaluation of every dependency declared by one work item."""

    dependencies: tuple[DependencyStatus, ...]
    outcome: DependencyOutcome

    @property
    def satisfied(self) -> bool:
        return self.outcome == "satisfied"

    @property
    def unsatisfied_ids(self) -> list[str]:
        return [row.work_id for row in self.dependencies if not row.complete]


def evaluate_dependencies(
    meta: WorkMeta,
    *,
    root: Path,
    board: BoardIndex | None = None,
) -> DependencyEvaluation:
    """Evaluate declared dependencies against the canonical merged board.

    A supplied board pins the caller's already-authoritative snapshot. Without
    one, planning ownership is resolved first so managed target worktrees read
    the tracking repository. Source failures are projected without exception
    text and fail closed for every declared dependency.
    """

    dependency_ids = tuple(meta.depends_on)
    if not dependency_ids:
        return DependencyEvaluation(dependencies=(), outcome="satisfied")

    if board is None:
        try:
            board = merged_board(resolve_tracking_root(root))
        except Exception:
            rows = tuple(
                _unavailable(dep_id, "dependency_source_unavailable")
                for dep_id in dependency_ids
            )
            return DependencyEvaluation(
                dependencies=rows,
                outcome="dependency_status_unavailable",
            )

    rows = tuple(_evaluate_one(dep_id, board) for dep_id in dependency_ids)
    if any(row.outcome == "dependency_status_unavailable" for row in rows):
        outcome: DependencyOutcome = "dependency_status_unavailable"
    elif any(row.outcome == "dependency_unmet" for row in rows):
        outcome = "dependency_unmet"
    else:
        outcome = "satisfied"
    return DependencyEvaluation(dependencies=rows, outcome=outcome)


def _evaluate_one(work_id: str, board: BoardIndex) -> DependencyStatus:
    meta = board.by_id.get(work_id)
    if meta is None:
        return _unavailable(work_id, "dependency_not_found")

    column = meta.path.parent.name
    if column != legal_folder(meta.status):
        reason: DependencyReason = "dependency_status_column_mismatch"
    elif meta.status == "completed" and column == "3_completed":
        return DependencyStatus(
            work_id=work_id,
            tier=meta.tier,
            status=meta.status,
            column=column,
            outcome="satisfied",
            reason=None,
        )
    elif meta.status == "cancelled":
        reason = "dependency_cancelled"
    else:
        reason = "dependency_incomplete"

    return DependencyStatus(
        work_id=work_id,
        tier=meta.tier,
        status=meta.status,
        column=column,
        outcome="dependency_unmet",
        reason=reason,
    )


def _unavailable(work_id: str, reason: DependencyReason) -> DependencyStatus:
    return DependencyStatus(
        work_id=work_id,
        tier=None,
        status=None,
        column=None,
        outcome="dependency_status_unavailable",
        reason=reason,
    )
