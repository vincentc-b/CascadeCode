"""Pure feature readiness: approval and dispatch blockers (feat_020_001)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping

from cascade.board.types import BoardIndex, WorkMeta
from cascade.dependency_evaluation import evaluate_dependencies
from cascade.workspace.integration_worktree import merged_board

_OPEN = {"backlog", "ready_to_plan"}


@dataclass(frozen=True)
class FeatureReadiness:
    approved: bool
    blockers: list[str]
    review_refusal: str | None = None
    explanation: ReadinessExplanation | None = None


ReasonKind = Literal["human_action", "work_wait", "system_wait", "unknown"]
ReasonActor = Literal["human", "feature_team", "supervisor", "system"]
ReadinessSummary = Literal[
    "needs_action", "waiting", "ready_awaiting_dispatch", "unavailable"
]


@dataclass(frozen=True)
class ReadinessLink:
    label: str
    href: str


@dataclass(frozen=True)
class ReadinessReason:
    code: str
    kind: ReasonKind
    message: str
    actor: ReasonActor | None = None
    next_action: str | None = None
    affected_work_ids: tuple[str, ...] = ()
    links: tuple[ReadinessLink, ...] = ()


@dataclass(frozen=True)
class SatisfiedPrerequisite:
    code: str
    message: str
    affected_work_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReadinessExplanation:
    """Versioned canonical reason core extended by the board serializer."""

    version: int
    summary: ReadinessSummary
    primary_reason_code: str | None
    reasons: tuple[ReadinessReason, ...]
    satisfied: tuple[SatisfiedPrerequisite, ...]


_DISPATCH_BLOCKER_ORDER = (
    "parent_cancellation_pending",
    "unmet_deps",
    "not_approved",
    "approval_status_unavailable",
    "feature_awaiting_merge",
    "sibling_blocked",
    "dispatch_base_unavailable",
    "review_threads_blocking",
)

_REASON_PRECEDENCE = {
    # Fresh human action.
    "not_approved": 10,
    "review_threads_blocking": 10,
    # Unknown required evidence.
    "dependency_status_unavailable": 20,
    "approval_status_unavailable": 20,
    "dispatch_base_unavailable": 20,
    "not_in_backlog": 20,
    # Known work waits.  Keep execution ahead of review, dependencies, parent.
    "sibling_active_execution": 30,
    "feature_awaiting_merge": 31,
    "dependency_unmet": 32,
    "epic_inactive": 33,
    "parent_cancellation_pending": 33,
}


def compute_feature_readiness(
    feature_id: str,
    *,
    root: Path,
    board: BoardIndex | None = None,
    pending_review_ids: frozenset[str] | None = None,
    review_refusals: Mapping[str, str | None] | None = None,
    approval_state: Literal["current", "stale", "unknown"] | None = None,
    bounded_dispatch_base: bool = True,
) -> FeatureReadiness | None:
    """Return approval and stable blocker codes for a backlog/open feature."""

    board = board or merged_board(root)
    meta = board.by_id.get(feature_id)
    if meta is None or meta.tier != "feature":
        return None

    approved = meta.approved_at is not None and approval_state in (None, "current")
    blockers: list[str] = []

    if meta.status not in _OPEN:
        return FeatureReadiness(
            approved=approved,
            blockers=blockers,
            explanation=_explanation([], []),
        )

    if not meta.parent:
        reasons = [_reason("epic_inactive")]
        satisfied: list[SatisfiedPrerequisite] = []
        if approved:
            satisfied.append(_approval_satisfied(meta.id))
        else:
            reasons.append(_reason("not_approved", affected_work_ids=(meta.id,)))
        return FeatureReadiness(
            approved=approved,
            blockers=["epic_inactive"],
            explanation=_explanation(reasons, satisfied),
        )

    reasons: list[ReadinessReason] = []
    satisfied: list[SatisfiedPrerequisite] = []

    if not _backlog_open(meta):
        blockers.append("not_in_backlog")
        reasons.append(_reason("not_in_backlog", affected_work_ids=(feature_id,)))

    dependency_evaluation = evaluate_dependencies(meta, root=root, board=board)
    unmet = dependency_evaluation.unsatisfied_ids
    if unmet:
        blockers.append(_unmet_deps_code(unmet))
        unavailable_ids = tuple(
            row.work_id
            for row in dependency_evaluation.dependencies
            if row.outcome == "dependency_status_unavailable"
        )
        known_unmet_ids = tuple(
            row.work_id
            for row in dependency_evaluation.dependencies
            if row.outcome == "dependency_unmet"
        )
        if unavailable_ids:
            reasons.append(
                _reason(
                    "dependency_status_unavailable",
                    affected_work_ids=unavailable_ids,
                )
            )
        if known_unmet_ids:
            reasons.append(
                _reason("dependency_unmet", affected_work_ids=known_unmet_ids)
            )
    else:
        satisfied.append(
            SatisfiedPrerequisite(
                code="dependencies_satisfied",
                message="All declared dependencies are complete.",
                affected_work_ids=tuple(sorted(meta.depends_on)),
            )
        )

    if approval_state == "unknown" and meta.approved_at is not None:
        blockers.append("approval_status_unavailable")
        reasons.append(
            _reason("approval_status_unavailable", affected_work_ids=(feature_id,))
        )
    elif not approved:
        blockers.append("not_approved")
        reasons.append(_reason("not_approved", affected_work_ids=(feature_id,)))
    else:
        satisfied.append(_approval_satisfied(feature_id))

    from cascade.stacked_dispatch import feature_dispatch_blockers

    dispatch_blockers = feature_dispatch_blockers(
        meta, board, root=root, pending_review_ids=pending_review_ids
    )
    if dispatch_blockers.pending_review_ids:
        blockers.append("feature_awaiting_merge")
        reasons.append(
            _reason(
                "feature_awaiting_merge",
                affected_work_ids=dispatch_blockers.pending_review_ids,
            )
        )
    else:
        satisfied.append(
            SatisfiedPrerequisite(
                code="merge_review_clear",
                message="No required feature merge or review is pending.",
            )
        )

    if dispatch_blockers.blocking_sibling_ids:
        blockers.append("sibling_blocked")
    if dispatch_blockers.active_execution_ids:
        reasons.append(
            _reason(
                "sibling_active_execution",
                affected_work_ids=dispatch_blockers.active_execution_ids,
            )
        )
    else:
        satisfied.append(
            SatisfiedPrerequisite(
                code="sibling_execution_clear",
                message="No sibling feature is actively executing.",
            )
        )

    parent = board.by_id.get(meta.parent)
    if parent is not None:
        from cascade.cancellation_feedback import cancellation_dispatch_gated

        if cancellation_dispatch_gated(parent):
            blockers.append("parent_cancellation_pending")
            reasons.append(
                _reason(
                    "parent_cancellation_pending",
                    affected_work_ids=(parent.id,),
                )
            )
    if parent is None or parent.path.parent.name != "2_active":
        blockers.append("epic_inactive")
        reasons.append(
            _reason(
                "epic_inactive",
                affected_work_ids=(meta.parent,) if meta.parent else (),
            )
        )
    elif "parent_cancellation_pending" not in blockers:
        satisfied.append(
            SatisfiedPrerequisite(
                code="parent_active",
                message="The parent Epic is active.",
                affected_work_ids=(parent.id,),
            )
        )

    if bounded_dispatch_base:
        dispatch_reason = _dispatch_base_unavailable(feature_id, meta, board, root=root)
        if dispatch_reason is not None:
            blockers.append(f"dispatch_base_unavailable:{dispatch_reason}")
            reasons.append(
                _reason(
                    "dispatch_base_unavailable",
                    affected_work_ids=(feature_id,),
                )
            )
        else:
            satisfied.append(
                SatisfiedPrerequisite(
                    code="dispatch_base_available",
                    message="A dispatch base is available.",
                    affected_work_ids=(feature_id,),
                )
            )

    review_refusal: str | None = None
    if review_refusals is None:
        from cascade.comments.gate import refusal_if_blocked

        review_refusal = refusal_if_blocked(feature_id, root=root, board=board)
    else:
        review_refusal = review_refusals.get(feature_id)
    if review_refusal:
        blockers.append("review_threads_blocking")
        reasons.append(
            _reason("review_threads_blocking", affected_work_ids=(feature_id,))
        )
    else:
        satisfied.append(
            SatisfiedPrerequisite(
                code="review_threads_clear",
                message="No blocking review thread is open.",
                affected_work_ids=(feature_id,),
            )
        )

    return FeatureReadiness(
        approved=approved,
        blockers=blockers,
        review_refusal=review_refusal,
        explanation=_explanation(reasons, satisfied),
    )


def feature_boss_dispatchable(readiness: FeatureReadiness) -> bool:
    """True when the feature passes the boss-view dispatch filter (excludes ``epic_inactive``)."""

    return not any(code for code in readiness.blockers if code != "epic_inactive")


def dispatch_refusal_from_readiness(readiness: FeatureReadiness) -> str | None:
    """Map the first dispatch-relevant blocker to ``DispatchResult.reason``."""

    for code in _DISPATCH_BLOCKER_ORDER:
        if not _has_blocker(readiness.blockers, code):
            continue
        if code == "sibling_blocked":
            return "feature_awaiting_merge"
        if code == "dispatch_base_unavailable":
            return _underlying_dispatch_base_reason(readiness.blockers)
        if code == "review_threads_blocking":
            return readiness.review_refusal or "bad_state"
        if code == "unmet_deps":
            return "unmet_deps"
        if code == "approval_status_unavailable":
            return "not_approved"
        return code
    return None


def _backlog_open(meta: WorkMeta) -> bool:
    return meta.status in _OPEN and meta.path.parent.name == "1_backlog"


def _unmet_deps_code(dep_ids: list[str]) -> str:
    return "unmet_deps:" + ",".join(sorted(dep_ids))


def _dispatch_base_unavailable(
    feature_id: str, meta: WorkMeta, board: BoardIndex, *, root: Path
) -> str | None:
    from cascade.stacked_dispatch import (
        direct_feature_predecessors,
        read_feature_dispatch_selection,
    )

    selection = read_feature_dispatch_selection(feature_id, root=root)
    # A plain Epic base is deterministic board evidence. A single predecessor
    # is also bounded by the existing review registry. Multi-head selection is
    # an action-boundary Git ancestry operation and must never run on a poll.
    if any(dep_id not in board.by_id for dep_id in meta.depends_on):
        return "dispatch_base_evidence_required"
    predecessors = direct_feature_predecessors(meta, board)
    if not predecessors:
        expected = f"epic/{meta.parent}" if meta.parent else None
        if selection is None or (
            selection.base_branch == expected and selection.predecessor_id is None
        ):
            return None
        return "stale_dispatch_selection"
    if len(predecessors) > 1:
        return "dispatch_base_evidence_required"
    from cascade.review import review_enabled, review_record_for_feature
    from cascade.workspace.integration_worktree import locate_trunk

    record = review_record_for_feature(predecessors[0], root=root)
    if record is not None and record.get("closed"):
        expected_base = f"epic/{meta.parent}"
        expected_predecessor = None
    elif record is not None and record.get("source_branch"):
        expected_base = str(record["source_branch"])
        expected_predecessor = predecessors[0]
    else:
        expected_base = None
        expected_predecessor = None
    if expected_base is not None:
        if selection is None or (
            selection.base_branch == expected_base
            and selection.predecessor_id == expected_predecessor
        ):
            return None
        return "stale_dispatch_selection"
    if record is None and not review_enabled(locate_trunk(root)):
        expected = f"epic/{meta.parent}"
        if selection is None or (
            selection.base_branch == expected and selection.predecessor_id is None
        ):
            return None
        return "stale_dispatch_selection"
    return "missing_predecessor_pr_identity"


def _has_blocker(blockers: list[str], code: str) -> bool:
    prefix = code + ":"
    return any(item == code or item.startswith(prefix) for item in blockers)


def _underlying_dispatch_base_reason(blockers: list[str]) -> str:
    for item in blockers:
        if item.startswith("dispatch_base_unavailable:"):
            return item.split(":", 1)[1]
    return "bad_state"


def _approval_satisfied(feature_id: str) -> SatisfiedPrerequisite:
    return SatisfiedPrerequisite(
        code="approval_current",
        message="The feature is approved.",
        affected_work_ids=(feature_id,),
    )


def _reason(code: str, *, affected_work_ids: tuple[str, ...] = ()) -> ReadinessReason:
    details: dict[str, tuple[ReasonKind, str, ReasonActor | None, str | None]] = {
        "not_approved": (
            "human_action",
            "This feature needs approval before it can start.",
            "human",
            "Approve the current feature plan.",
        ),
        "review_threads_blocking": (
            "human_action",
            "Blocking review threads must be resolved.",
            "human",
            "Resolve the blocking review threads.",
        ),
        "dependency_status_unavailable": (
            "unknown",
            "Dependency status is unavailable and is being rechecked.",
            "system",
            None,
        ),
        "approval_status_unavailable": (
            "unknown",
            "Approval evidence cannot be matched to the current feature plan.",
            "system",
            None,
        ),
        "dispatch_base_unavailable": (
            "unknown",
            "A safe dispatch base cannot currently be established.",
            "system",
            None,
        ),
        "not_in_backlog": (
            "unknown",
            "The feature is not in the canonical backlog location.",
            "system",
            None,
        ),
        "sibling_active_execution": (
            "work_wait",
            "Another feature in this Epic is actively executing.",
            "feature_team",
            "Wait for the active sibling feature to finish execution.",
        ),
        "feature_awaiting_merge": (
            "work_wait",
            "Feature work is waiting for required merge or review.",
            "feature_team",
            "Complete the pending feature merge or review.",
        ),
        "dependency_unmet": (
            "work_wait",
            "One or more declared dependencies are incomplete.",
            "feature_team",
            "Complete the declared dependencies.",
        ),
        "epic_inactive": (
            "work_wait",
            "The parent Epic is not active.",
            "supervisor",
            "Activate the parent Epic when it is ready.",
        ),
        "parent_cancellation_pending": (
            "work_wait",
            "The parent Epic has unresolved cancellation feedback.",
            "supervisor",
            "Resolve the parent Epic cancellation disposition.",
        ),
    }
    kind, message, actor, next_action = details[code]
    return ReadinessReason(
        code=code,
        kind=kind,
        message=message,
        actor=actor,
        next_action=next_action,
        affected_work_ids=tuple(sorted(set(affected_work_ids))),
    )


def _reason_sort_key(reason: ReadinessReason) -> tuple[int, str, tuple[str, ...]]:
    return (
        _REASON_PRECEDENCE.get(reason.code, 40),
        reason.code,
        reason.affected_work_ids,
    )


def _explanation(
    reasons: list[ReadinessReason],
    satisfied: list[SatisfiedPrerequisite],
) -> ReadinessExplanation:
    ordered_reasons = tuple(sorted(reasons, key=_reason_sort_key))
    ordered_satisfied = tuple(
        sorted(satisfied, key=lambda item: (item.code, item.affected_work_ids))
    )
    if not ordered_reasons:
        summary: ReadinessSummary = "ready_awaiting_dispatch"
        primary = None
    else:
        primary_reason = ordered_reasons[0]
        primary = primary_reason.code
        summary = {
            "human_action": "needs_action",
            "unknown": "unavailable",
            "work_wait": "waiting",
            "system_wait": "waiting",
        }[primary_reason.kind]
    return ReadinessExplanation(
        version=1,
        summary=summary,
        primary_reason_code=primary,
        reasons=ordered_reasons,
        satisfied=ordered_satisfied,
    )
