"""Fresh dependency evidence for planning authorization boundaries."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.board.context import resolve_tracking_root
from cascade.board.errors import BoardError
from cascade.board.types import BoardIndex, WorkMeta
from cascade.dependency_evaluation import (
    DependencyEvaluation,
    DependencyOutcome,
    evaluate_dependencies,
)
from cascade.dependency_explanations import dependency_outcome_explanation
from cascade.workspace.integration_worktree import refresh_merged_board


class DependencyActionRefused(BoardError):
    """A planning mutation was refused by current dependency evidence."""

    def __init__(
        self,
        outcome: DependencyOutcome,
        *,
        reasons: tuple[str, ...] = (),
    ) -> None:
        self.outcome = outcome
        self.reasons = reasons
        self.explanation = dependency_outcome_explanation(outcome)
        # Keep exception text as the stable code for existing machine-facing
        # boundaries. Human guidance is deliberately a separate attribute.
        super().__init__(outcome)


@dataclass(frozen=True)
class ActionDependencyEvidence:
    """Current owner declaration and lifecycle evaluation from one fresh board."""

    evaluation: DependencyEvaluation
    board: BoardIndex | None = None
    owner: WorkMeta | None = None

    @property
    def outcome(self) -> DependencyOutcome:
        return self.evaluation.outcome


def evaluate_action_dependencies(work_id: str, *, root: Path) -> ActionDependencyEvidence:
    """Re-read an owner's declaration and lifecycle evidence, bypassing snapshots."""

    try:
        tracking_root = resolve_tracking_root(root)
        board = refresh_merged_board(tracking_root)
    except Exception:
        # Source and owner refresh failures are intentionally safe and stable.
        return ActionDependencyEvidence(
            evaluation=DependencyEvaluation(
                dependencies=(), outcome="dependency_status_unavailable"
            )
        )
    owner = board.by_id.get(work_id)
    if owner is None:
        return ActionDependencyEvidence(
            evaluation=DependencyEvaluation(
                dependencies=(), outcome="dependency_status_unavailable"
            ),
            board=board,
        )
    evaluation = evaluate_dependencies(owner, root=tracking_root, board=board)
    return ActionDependencyEvidence(evaluation=evaluation, board=board, owner=owner)


def require_action_dependencies(work_id: str, *, root: Path) -> ActionDependencyEvidence:
    """Return fresh evidence or refuse with its stable dependency outcome."""

    evidence = evaluate_action_dependencies(work_id, root=root)
    if evidence.outcome != "satisfied":
        reasons = tuple(
            dict.fromkeys(
                row.reason
                for row in evidence.evaluation.dependencies
                if row.reason is not None
            )
        )
        if not reasons and evidence.outcome == "dependency_status_unavailable":
            reasons = (
                "dependency_source_unavailable"
                if evidence.board is None
                else "dependency_not_found",
            )
        raise DependencyActionRefused(evidence.outcome, reasons=reasons)
    return evidence
