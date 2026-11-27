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
        affected_work_ids: tuple[str, ...] = (),
    ) -> None:
        self.outcome = outcome
        self.reasons = reasons
        self.affected_work_ids = affected_work_ids
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
        raise DependencyActionRefused(
            evidence.outcome,
            reasons=reasons,
            affected_work_ids=_affected_work_ids(evidence, work_id),
        )
    return evidence


def require_feature_approval_dependencies(
    work_id: str,
    *,
    root: Path,
    prior: ActionDependencyEvidence | None = None,
) -> ActionDependencyEvidence:
    """Allow only known legal predecessor waits for individual approval.

    A second call with ``prior`` also fences the canonical owner and declared
    dependency IDs across the other approval checks. Mutable predecessor
    lifecycle state is deliberately not part of that fence.
    """

    evidence = evaluate_action_dependencies(work_id, root=root)
    if evidence.board is None:
        raise DependencyActionRefused(
            evidence.outcome,
            reasons=("dependency_source_unavailable",),
            affected_work_ids=(work_id,),
        )
    if prior is not None and not _same_dependency_owner(prior.owner, evidence.owner):
        old_ids = tuple(prior.owner.depends_on) if prior.owner is not None else ()
        new_ids = tuple(evidence.owner.depends_on) if evidence.owner is not None else ()
        reason = (
            "dependency_declaration_changed"
            if set(old_ids) != set(new_ids)
            else "dependency_owner_changed"
        )
        raise DependencyActionRefused(
            "dependency_status_unavailable",
            reasons=(reason,),
            affected_work_ids=tuple(sorted({work_id, *old_ids, *new_ids})),
        )
    if feature_approval_dependencies_permitted(evidence.evaluation):
        return evidence
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
    raise DependencyActionRefused(
        evidence.outcome,
        reasons=reasons,
        affected_work_ids=_affected_work_ids(evidence, work_id),
    )


def feature_approval_dependencies_permitted(
    evaluation: DependencyEvaluation,
) -> bool:
    """Apply the individual-approval predecessor policy to supplied evidence.

    This pure form lets read-only projections use exactly the mutation boundary's
    allowlist without refreshing the board or writing approval state.
    """

    return evaluation.outcome == "satisfied" or (
        bool(evaluation.dependencies)
        and all(
            row.outcome in {"satisfied", "dependency_unmet"}
            and (row.complete or row.reason == "dependency_incomplete")
            for row in evaluation.dependencies
        )
    )


def _same_dependency_owner(left: WorkMeta | None, right: WorkMeta | None) -> bool:
    if left is None or right is None:
        return left is right
    return (
        left.id == right.id
        and left.tier == right.tier
        and left.parent == right.parent
        and sorted(left.owners) == sorted(right.owners)
        and left.path == right.path
        and sorted(left.depends_on) == sorted(right.depends_on)
    )


def _affected_work_ids(
    evidence: ActionDependencyEvidence, work_id: str
) -> tuple[str, ...]:
    affected = [
        row.work_id for row in evidence.evaluation.dependencies if not row.complete
    ]
    return tuple(dict.fromkeys(affected or [work_id]))
