"""Durable feature approval on board docs; epic plan approval marks the epic and its current children."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.lock import process_lock
from cascade.board.store import read_doc, write_doc
from cascade.epic.plan_readiness import require_epic_plan_ready_for_approval
from cascade.workspace.integration_worktree import merged_board
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event


def feature_approved(feature_id: str, *, root: Path) -> bool:
    repo = resolve_root(root)
    meta = merged_board(repo).by_id.get(feature_id)
    return meta is not None and meta.tier == "feature" and meta.approved_at is not None


def epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    repo = resolve_root(root)
    meta = merged_board(repo).by_id.get(epic_id)
    return meta is not None and meta.tier == "epic" and meta.plan_approved_at is not None


def approve_feature(feature_id: str, *, root: Path) -> dict[str, object]:
    repo = resolve_root(root)
    board = merged_board(repo)
    meta = board.by_id.get(feature_id)
    if meta is None or meta.tier != "feature":
        raise ValueError("feature approval requires a feature on the board")
    newly = _set_feature_approved(feature_id, root=repo)
    result: dict[str, object] = {
        "ok": True, "feature_id": feature_id, "newly_approved": newly
    }
    if warning := _maybe_advance_after_approval(repo):
        result["dispatch_pending"] = True
        result["dispatch_error"] = warning
    return result


def approve_epic_plan(epic_id: str, *, root: Path) -> dict[str, object]:
    repo = resolve_root(root)
    board = merged_board(repo)
    epic = board.by_id.get(epic_id)
    if epic is None or epic.tier != "epic" or epic.path.parent.name != "2_active":
        raise ValueError("epic plan can only be approved while its team is active")
    children = sorted(
        meta.id
        for meta in board.by_id.values()
        if meta.tier == "feature" and meta.parent == epic_id
    )
    if not children:
        raise ValueError("epic plan has no feature plans to approve yet")

    with process_lock:
        board = merged_board(repo)
        epic = board.by_id.get(epic_id)
        if epic is not None and epic.plan_approved_at is None:
            require_epic_plan_ready_for_approval(epic_id, root=repo, board=board)
        for feature_id in children:
            _set_feature_approved(feature_id, root=repo)
        # The epic timestamp is the durable indication that the entire current plan
        # was approved.  Write it only after every child so a child write failure
        # cannot leave the plan marked approved while work remains blocked.
        epic_newly = _set_epic_plan_approved(epic_id, root=repo)

    if epic_newly:
        for dest in (epic_id, "war_room"):
            append_event(
                dest,
                Event(
                    type="Toast" if dest == "war_room" else "EpicPlanApproved",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "kind": "epic_plan_approved",
                        "id": epic_id,
                        "epic_id": epic_id,
                        "features": children,
                        "message": f"Plan approved for {epic_id}; feature work will start automatically",
                    },
                    dest=dest,
                ),
                root=repo,
            )
    result: dict[str, object] = {"ok": True, "epic_id": epic_id, "features": children}
    if warning := _maybe_advance_after_approval(repo):
        result["dispatch_pending"] = True
        result["dispatch_error"] = warning
    return result


def _set_feature_approved(feature_id: str, *, root: Path) -> bool:
    if feature_approved(feature_id, root=root):
        return False
    doc = read_doc(feature_id, root=root)
    if doc.meta.approved_at is not None:
        return False
    doc.meta.approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True


def _maybe_advance_after_approval(root: Path) -> str | None:
    from cascade.watchdog.config import read_automation_config
    from cascade.automation import reconcile_approval_dispatch

    # Approval is the dispatch trigger. Broad completion maintenance can involve
    # remote review calls or pending merges and must not hold this HTTP request
    # ahead of newly eligible work.
    try:
        if not read_automation_config(root).enabled:
            return None
        reconcile_approval_dispatch(root)
    except Exception as exc:
        # Approval is already durable. The watchdog can retry dispatch; report
        # that delay without claiming the approval itself failed.
        return str(exc) or type(exc).__name__
    return None


def _set_epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    doc = read_doc(epic_id, root=root)
    if doc.meta.plan_approved_at is not None:
        return False
    doc.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True
