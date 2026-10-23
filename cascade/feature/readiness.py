"""Pure feature readiness: approval and dispatch blockers (feat_020_001)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.approvals import feature_approved
from cascade.board.types import BoardIndex, WorkMeta
from cascade.workspace.integration_worktree import merged_board

_OPEN = {"backlog", "ready_to_plan"}


@dataclass(frozen=True)
class FeatureReadiness:
    approved: bool
    blockers: list[str]
    review_refusal: str | None = None


_DISPATCH_BLOCKER_ORDER = (
    "unmet_deps",
    "not_approved",
    "feature_awaiting_merge",
    "sibling_blocked",
    "dispatch_base_unavailable",
    "review_threads_blocking",
)


def compute_feature_readiness(
    feature_id: str,
    *,
    root: Path,
    board: BoardIndex | None = None,
) -> FeatureReadiness | None:
    """Return approval and stable blocker codes for a backlog/open feature."""

    board = board or merged_board(root)
    meta = board.by_id.get(feature_id)
    if meta is None or meta.tier != "feature":
        return None

    approved = feature_approved(feature_id, root=root)
    blockers: list[str] = []

    if meta.status not in _OPEN:
        return FeatureReadiness(approved=approved, blockers=blockers)

    if not meta.parent:
        return FeatureReadiness(approved=approved, blockers=blockers)

    if not _backlog_open(meta):
        blockers.append("not_in_backlog")

    unmet = _unmet_dependency_ids(meta, board)
    if unmet:
        blockers.append(_unmet_deps_code(unmet))

    if not approved:
        blockers.append("not_approved")

    from cascade.stacked_dispatch import feature_merge_gated

    if feature_merge_gated(meta, board, root=root):
        blockers.append("feature_awaiting_merge")

    from cascade.stacked_dispatch import feature_dispatch_blocked_by_sibling

    if feature_dispatch_blocked_by_sibling(meta, board, root=root):
        blockers.append("sibling_blocked")

    parent = board.by_id.get(meta.parent)
    if parent is None or parent.path.parent.name != "2_active":
        blockers.append("epic_inactive")

    dispatch_reason = _dispatch_base_unavailable(feature_id, meta, board, root=root)
    if dispatch_reason is not None:
        blockers.append(f"dispatch_base_unavailable:{dispatch_reason}")

    from cascade.comments.gate import refusal_if_blocked

    review_refusal: str | None = None
    if blocked := refusal_if_blocked(feature_id, root=root):
        blockers.append("review_threads_blocking")
        review_refusal = blocked

    return FeatureReadiness(
        approved=approved,
        blockers=blockers,
        review_refusal=review_refusal,
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
        return code
    return None


def _backlog_open(meta: WorkMeta) -> bool:
    return meta.status in _OPEN and meta.path.parent.name == "1_backlog"


def _unmet_dependency_ids(meta: WorkMeta, board: BoardIndex) -> list[str]:
    missing: list[str] = []
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is None or dep.status != "completed" or dep.path.parent.name != "3_completed":
            missing.append(dep_id)
    return missing


def _unmet_deps_code(dep_ids: list[str]) -> str:
    return "unmet_deps:" + ",".join(sorted(dep_ids))


def _dispatch_base_unavailable(
    feature_id: str, meta: WorkMeta, board: BoardIndex, *, root: Path
) -> str | None:
    from cascade.stacked_dispatch import (
        plan_feature_dispatch,
        read_feature_dispatch_selection,
    )

    if read_feature_dispatch_selection(feature_id, root=root) is not None:
        return None
    plan = plan_feature_dispatch(feature_id, meta, board, root=root)
    if plan.ok:
        return None
    return plan.reason or "bad_state"


def _has_blocker(blockers: list[str], code: str) -> bool:
    prefix = code + ":"
    return any(item == code or item.startswith(prefix) for item in blockers)


def _underlying_dispatch_base_reason(blockers: list[str]) -> str:
    for item in blockers:
        if item.startswith("dispatch_base_unavailable:"):
            return item.split(":", 1)[1]
    return "bad_state"
