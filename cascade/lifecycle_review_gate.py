"""Thin lifecycle adapter for the revision-bound architecture review gate."""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import get_project_context
from cascade.workspace.architecture_review import (
    ArchitectureReviewStore,
    ReviewGateBoundary,
    ReviewGateResult,
    validate_review_gate,
)
from cascade.workspace.types import ProjectContext


def require_lifecycle_review_gate(
    work_id: str,
    boundary: ReviewGateBoundary,
    *,
    root: Path,
) -> ReviewGateResult:
    """Resolve repository roles and apply scoped comment/affected-work holds."""

    project = get_project_context() or ProjectContext.colocated(root)
    store = ArchitectureReviewStore(project)
    affected = {work_id}
    for unit in store.units_affecting(work_id):
        affected.update(unit.affected_work_ids)
    from cascade.comments.gate import blocking_threads_for_many
    from cascade.workspace.blocking_scope import affected_blocking_threads

    gates = blocking_threads_for_many(affected, root=root)
    blocked = tuple(item for item, result in gates.items() if result.blocked)
    semantic_blockers = affected_blocking_threads(
        work_id, boundary, root=root, store=store
    )
    result = validate_review_gate(
        project,
        work_id=work_id,
        boundary=boundary,
        store=store,
        blocking_work_ids=blocked,
        semantic_blockers=semantic_blockers,
    )
    if boundary == "closeout" and result.rollout_version > 0:
        from cascade.workspace.reconciliation import validate_reconciliation_closeout

        tier = _work_tier(work_id, project)
        validate_reconciliation_closeout(project, work_id, tier, review_store=store)
    return result


def require_task_reconciliation_closeout(work_id: str, *, root: Path) -> None:
    """Apply the closeout receipt at Task's terminal merge boundary."""

    project = get_project_context() or ProjectContext.colocated(root)
    store = ArchitectureReviewStore(project)
    if (store.gate_policy_version(work_id) or 0) <= 0:
        return
    from cascade.workspace.reconciliation import validate_reconciliation_closeout

    validate_reconciliation_closeout(project, work_id, "task", review_store=store)


def _work_tier(work_id: str, project: ProjectContext):
    from cascade.workspace.doc_root import read_doc_resolved

    tier = read_doc_resolved(work_id, root=project.tracking.root).meta.tier
    if tier not in {"task", "feature", "epic"}:
        raise ValueError(f"unsupported closeout tier: {tier}")
    return tier


__all__ = ["require_lifecycle_review_gate", "require_task_reconciliation_closeout"]
