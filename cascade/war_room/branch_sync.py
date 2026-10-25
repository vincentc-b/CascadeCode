"""War Room branch synchronization read model and actionable failure payloads (feat_016_002)."""

from __future__ import annotations

from http import HTTPStatus
from pathlib import Path
from typing import Any

from cascade.board.paths import column_for_status
from cascade.board.types import WorkMeta, WorkTier
from cascade.workspace.branch_synchronization import (
    BranchSyncInspection,
    BranchSyncUpdateResult,
    inspect_branch_synchronization,
    update_integration_branch,
)

_SYNC_TIERS: frozenset[WorkTier] = frozenset({"epic", "feature", "task"})

_GUIDANCE: dict[str, str] = {
    "busy": "Wait for the in-flight agent turn to finish, then retry.",
    "dirty_index": "Unstage or commit staged changes in the integration worktree, then retry.",
    "local_changes": (
        "Commit, stash, or remove local changes (including untracked files) "
        "in the integration worktree, then retry."
    ),
    "branch_conflict": (
        "Resolve the listed file conflicts in the integration worktree, then retry."
    ),
    "merge_conflict": (
        "Resolve the listed file conflicts in the integration worktree, then retry."
    ),
    "invariant": "Verify the integration worktree is on the expected branch and retry.",
    "checkout_missing": "Repair or recreate the integration worktree, then retry.",
    "merge_target_missing": "Repair or recreate the integration worktree, then retry.",
    "wrong_branch": "Check out the product trunk on the operator repo, then retry.",
    "current": "The integration branch already includes its base; no update is needed.",
}


def sync_failure_http_status(reason: str | None) -> HTTPStatus:
    """Map typed synchronization / merge failure reasons to HTTP status codes."""

    if reason in ("not_found", "task_not_found", "feature_not_found"):
        return HTTPStatus.NOT_FOUND
    if reason in ("branch_conflict", "merge_conflict"):
        return HTTPStatus.CONFLICT
    return HTTPStatus.BAD_REQUEST


def actionable_sync_failure_payload(
    *,
    reason: str | None,
    conflict_paths: tuple[str, ...] = (),
    product_trunk: bool = False,
) -> dict[str, Any]:
    """Concise JSON fields for dirty, busy, conflict, and invariant failures."""

    payload: dict[str, Any] = {"reason": reason}
    if reason and reason in _GUIDANCE:
        payload["guidance"] = _GUIDANCE[reason]
    if product_trunk and reason == "dirty_index":
        payload["guidance"] = (
            "Unstage or commit staged changes in the product trunk checkout, then retry."
        )
    elif product_trunk and reason == "local_changes":
        payload["guidance"] = (
            "Commit, stash, or remove local changes (including untracked files) "
            "in the product trunk checkout, then retry."
        )
    elif product_trunk and reason in ("branch_conflict", "merge_conflict"):
        payload["guidance"] = (
            "Resolve the listed conflicts between the epic branch and product trunk, "
            "then retry."
        )
    if reason in ("branch_conflict", "merge_conflict"):
        payload["conflict_paths"] = list(conflict_paths)
        payload["merge_aborted"] = True
    return payload


def branch_sync_view_from_inspection(inspection: BranchSyncInspection) -> dict[str, Any]:
    if not inspection.ok:
        reason = inspection.reason
        return {
            "ok": False,
            "reason": reason,
            "update_eligible": False,
            "update_disabled_reason": reason,
        }

    state = inspection.state
    assert state is not None
    blocked = inspection.update_blocked_reason
    if state.behind == 0:
        disabled: str | None = blocked or "current"
        eligible = False
    else:
        disabled = blocked
        eligible = blocked is None

    view: dict[str, Any] = {
        "ok": True,
        "work_branch": state.work_branch,
        "base_branch": state.base_branch,
        "ahead": state.ahead,
        "behind": state.behind,
        "update_eligible": eligible,
        "update_disabled_reason": disabled,
    }
    if disabled and disabled in _GUIDANCE:
        view["guidance"] = _GUIDANCE[disabled]
    return view


def branch_sync_view(work_id: str, *, root: Path) -> dict[str, Any] | None:
    """Per-item branch drift view; None when the tier/column is out of scope."""

    inspection = inspect_branch_synchronization(work_id, root=root)
    if inspection.reason == "wrong_tier":
        return None
    return branch_sync_view_from_inspection(inspection)


def branch_sync_views(
    metas: list[WorkMeta] | tuple[WorkMeta, ...],
    *,
    root: Path,
) -> dict[str, dict[str, Any] | None]:
    """Batch branch sync views for board serialization."""

    views: dict[str, dict[str, Any] | None] = {}
    for meta in metas:
        if meta.tier not in _SYNC_TIERS:
            views[meta.id] = None
            continue
        if column_for_status(meta.status) != "active" or meta.status != "active":
            views[meta.id] = None
            continue
        views[meta.id] = branch_sync_view(meta.id, root=root)
    return views


def branch_sync_update_to_dict(
    result: BranchSyncUpdateResult, *, work_id: str
) -> dict[str, Any]:
    if result.ok:
        payload: dict[str, Any] = {
            "ok": True,
            "work_id": work_id,
            "no_op": result.no_op,
        }
        if result.merge_sha is not None:
            payload["merge_sha"] = result.merge_sha
        return payload
    payload = actionable_sync_failure_payload(
        reason=result.reason,
        conflict_paths=result.conflict_paths,
    )
    payload["ok"] = False
    payload["work_id"] = work_id
    return payload


def run_branch_sync_update(work_id: str, *, root: Path) -> BranchSyncUpdateResult:
    return update_integration_branch(work_id, root=root)


def lifecycle_merge_failure_payload(
    *,
    reason: str | None,
    conflict_paths: tuple[str, ...] = (),
    **fields: Any,
) -> dict[str, Any]:
    """Shared failure envelope for task merge and epic close routes."""

    payload = actionable_sync_failure_payload(
        reason=reason,
        conflict_paths=conflict_paths,
    )
    payload["ok"] = False
    for key, value in fields.items():
        if value is not None:
            payload[key] = value
    return payload
