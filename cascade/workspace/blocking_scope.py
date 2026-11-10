"""Current-board scope projection for open semantic review blockers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.board.context import get_project_context, resolve_root
from cascade.board.types import BoardIndex
from cascade.comments.store import read_comments
from cascade.comments.types import Comment
from cascade.workspace.architecture_review import ArchitectureReviewStore, ReviewGateBoundary
from cascade.workspace.c4_threads import SemanticThreadAnchor
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.integration_worktree import locate_trunk, refresh_merged_board
from cascade.workspace.types import ProjectContext


@dataclass(frozen=True)
class BlockingScope:
    """One unresolved semantic thread and its current lifecycle hold."""

    thread_id: str
    owning_work_id: str
    affected_work_ids: tuple[str, ...]
    reason: str
    boundary: ReviewGateBoundary
    fallback: bool


def affected_blocking_threads(
    work_id: str,
    boundary: ReviewGateBoundary,
    *,
    root: Path,
    board: BoardIndex | None = None,
    store: ArchitectureReviewStore | None = None,
) -> tuple[BlockingScope, ...]:
    """Return semantic blockers that affect ``work_id`` on the current graph.

    Stored anchors remain immutable. Their scope is recomputed from the current
    board so newly-added dependents cannot escape an older open blocker.
    """

    if boundary not in {"approval", "dispatch", "integration", "merge", "closeout"}:
        raise WorkspaceError("invalid architecture review gate boundary")
    repo = resolve_root(root)
    trunk = locate_trunk(repo)
    current_board = board or refresh_merged_board(trunk)
    project = get_project_context() or ProjectContext.colocated(trunk)
    review_store = store or ArchitectureReviewStore(project)
    scopes: list[BlockingScope] = []
    for meta in current_board.by_id.values():
        if meta.tier not in {"epic", "feature"}:
            continue
        for row in read_comments(meta.id, root=trunk, board=current_board, readonly=True):
            if (
                row.parent is not None
                or row.state != "open"
                or not row.blocking
                or row.semantic_anchor is None
            ):
                continue
            scope = _scope_for_comment(row, boundary, current_board, review_store)
            if work_id in scope.affected_work_ids:
                scopes.append(scope)
    return tuple(sorted(scopes, key=lambda item: (item.owning_work_id, item.thread_id)))


def semantic_affected_work_ids(
    row: Comment,
    *,
    board: BoardIndex,
    root: Path,
) -> set[str]:
    """Project one semantic root for legacy comment gates such as mint/merge."""

    project = get_project_context() or ProjectContext.colocated(locate_trunk(root))
    scope = _scope_for_comment(
        row, "dispatch", board, ArchitectureReviewStore(project)
    )
    return set(scope.affected_work_ids)


def _scope_for_comment(
    row: Comment,
    boundary: ReviewGateBoundary,
    board: BoardIndex,
    store: ArchitectureReviewStore,
) -> BlockingScope:
    try:
        anchor = SemanticThreadAnchor.from_dict(row.semantic_anchor)
    except (TypeError, WorkspaceError):
        anchor = None

    owner = row.doc_id
    direct: set[str] = {item for item in row.blocks if item in board.by_id}
    reasons: list[str] = []
    if direct:
        reasons.append("comment_affected_ids")

    unit = store.get(anchor.review_unit_id) if anchor is not None else None
    if (
        unit is not None
        and anchor is not None
        and unit.reviewed_tuple_digest == anchor.reviewed_tuple_digest
    ):
        owner = unit.owner_work_id if unit.owner_work_id in board.by_id else owner
        unit_ids = {item for item in unit.affected_work_ids if item in board.by_id}
        if unit_ids:
            direct.update(unit_ids)
            reasons.append("review_unit_affected_ids")
        cited = _cited_work_ids(unit, board)
        if cited:
            direct.update(cited)
            reasons.append("citations")

    fallback = not direct
    if fallback:
        affected = _subtree(owner, board)
        reasons = ["owner_subtree_fallback"]
    else:
        affected = _dependent_closure(direct, board)

    return BlockingScope(
        thread_id=row.id,
        owning_work_id=owner,
        affected_work_ids=tuple(sorted(affected)),
        reason="+".join(reasons),
        boundary=boundary,
        fallback=fallback,
    )


def _cited_work_ids(unit, board: BoardIndex) -> set[str]:
    citations = {
        *unit.requirement_citations,
        *unit.decision_citations,
        *unit.view_citations,
    }
    result: set[str] = set()
    for citation in citations:
        work_id = citation.partition("#")[0]
        if work_id in board.by_id:
            result.add(work_id)
    for meta in board.by_id.values():
        if citations.intersection(meta.cites):
            result.add(meta.id)
    return result


def _dependent_closure(seed: set[str], board: BoardIndex) -> set[str]:
    affected: set[str] = set()
    pending = list(seed)
    while pending:
        work_id = pending.pop()
        if work_id in affected or work_id not in board.by_id:
            continue
        new_ids = _subtree(work_id, board) - affected
        affected.update(new_ids)
        for meta in board.by_id.values():
            if meta.id not in affected and any(
                dependency in new_ids for dependency in meta.depends_on
            ):
                pending.append(meta.id)
    return affected


def _subtree(work_id: str, board: BoardIndex) -> set[str]:
    result: set[str] = set()
    pending = [work_id]
    while pending:
        current = pending.pop()
        if current in result or current not in board.by_id:
            continue
        result.add(current)
        pending.extend(board.by_id[current].children)
    return result


__all__ = ["BlockingScope", "affected_blocking_threads"]
