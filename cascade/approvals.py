"""Durable feature approval on board docs; epic plan approval marks the epic and its current children."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.store import read_doc, write_doc
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
    _maybe_advance_after_approval(repo)
    return {"ok": True, "feature_id": feature_id, "newly_approved": newly}


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
    _maybe_advance_after_approval(repo)
    return {"ok": True, "epic_id": epic_id, "features": children}


def _set_feature_approved(feature_id: str, *, root: Path) -> bool:
    doc = read_doc(feature_id, root=root)
    if doc.meta.approved_at is not None:
        return False
    doc.meta.approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True


def _maybe_advance_after_approval(root: Path) -> None:
    from cascade.watchdog.config import read_automation_config

    if not read_automation_config(root).enabled:
        return
    from cascade.automation import advance_work

    advance_work(root)


def _set_epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    doc = read_doc(epic_id, root=root)
    if doc.meta.plan_approved_at is not None:
        return False
    doc.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True
