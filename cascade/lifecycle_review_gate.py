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

    from cascade.scoped_change_holds import (
        ScopedChangeHoldError,
        require_no_scoped_change_hold,
    )
    from cascade.workspace.architecture_review import ArchitectureProposalError

    # Approval is the path that creates the refreshed evidence needed to
    # release changed work. It is intentionally not itself a held boundary.
    if boundary != "approval":
        try:
            require_no_scoped_change_hold(work_id, boundary, root=root)
        except ScopedChangeHoldError as exc:
            raise ArchitectureProposalError(
                exc.code, str(exc).partition(": ")[2]
            ) from exc

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
    return validate_review_gate(
        project,
        work_id=work_id,
        boundary=boundary,
        store=store,
        blocking_work_ids=blocked,
        semantic_blockers=semantic_blockers,
    )


__all__ = ["require_lifecycle_review_gate"]
