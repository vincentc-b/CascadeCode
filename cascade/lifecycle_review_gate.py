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
    if store.gate_rollout_version() is None and store.gate_policy_version(work_id) is None:
        return validate_review_gate(
            project, work_id=work_id, boundary=boundary, store=store
        )

    affected = {work_id}
    for unit in store.units_affecting(work_id):
        affected.update(unit.affected_work_ids)
    from cascade.comments.gate import blocking_threads_for_many

    gates = blocking_threads_for_many(affected, root=root)
    blocked = tuple(item for item, result in gates.items() if result.blocked)
    return validate_review_gate(
        project,
        work_id=work_id,
        boundary=boundary,
        store=store,
        blocking_work_ids=blocked,
    )


__all__ = ["require_lifecycle_review_gate"]
