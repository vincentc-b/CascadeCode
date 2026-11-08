"""Durable feature approval on board docs; epic plan approval marks the epic and its current children."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from cascade.agent.discovery.inventory import ProviderInventoryResult, get_provider_inventory
from cascade.agent.selection_preflight import (
    RuntimeSelection,
    SelectionPreflight,
    evaluate_work_selection,
)
from cascade.board.parse import parse_doc
from cascade.board.context import resolve_root
from cascade.board.lock import process_lock
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkMeta
from cascade.epic.plan_readiness import require_epic_plan_ready_for_approval
from cascade.planning_action_dependencies import require_action_dependencies
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from cascade.watchdog.events import append_event
from cascade.watchdog.types import DispatchResult, Event


class ApprovalSelectionError(ValueError):
    """A complete, safe refusal before an approval mutates board state."""

    def __init__(self, preflights: tuple[SelectionPreflight, ...]) -> None:
        self.preflights = preflights
        self.failures = tuple(item for item in preflights if not item.result.supported)
        first = self.failures[0]
        self.preflight = first.result
        self.selections = first.selections
        super().__init__(
            first.result.message or "selected configuration is not supported"
        )

    def to_dict(self) -> dict[str, object]:
        first = self.failures[0]
        message = str(self)
        return {
            "ok": False,
            "code": (
                "provider_preflight_blocked"
                if first.result.outcome == "blocked"
                else "provider_preflight_unavailable"
            ),
            "error": message,
            "message": message,
            "preflight": first.result.to_dict(),
            "selections": first.selections.to_dict(),
            "preflights": [
                {
                    "preflight": item.result.to_dict(),
                    "selections": item.selections.to_dict(),
                }
                for item in self.preflights
            ],
        }


@dataclass(frozen=True)
class _DispatchWarning:
    message: str
    preflight: object | None = None
    selections: object | None = None
    refusals: tuple[tuple[str, DispatchResult], ...] = ()
    launched: tuple[str, ...] = ()


def feature_approved(feature_id: str, *, root: Path) -> bool:
    repo = resolve_root(root)
    meta = merged_board(repo).by_id.get(feature_id)
    return meta is not None and meta.tier == "feature" and meta.approved_at is not None


def epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    repo = resolve_root(root)
    meta = merged_board(repo).by_id.get(epic_id)
    return meta is not None and meta.tier == "epic" and meta.plan_approved_at is not None


def approve_feature(
    feature_id: str,
    *,
    root: Path,
    inventory: ProviderInventoryResult | None = None,
) -> dict[str, object]:
    repo = resolve_root(root)
    with process_lock:
        board = merged_board(repo)
        meta = board.by_id.get(feature_id)
        if meta is None or meta.tier != "feature":
            raise ValueError("feature approval requires a feature on the board")
        evidence = require_action_dependencies(feature_id, root=repo)
        assert evidence.board is not None
        with merged_board_snapshot(repo, evidence.board):
            current = evidence.board.by_id.get(feature_id)
            if current is None or current.tier != "feature":
                raise ValueError("feature approval requires a feature on the board")
            if current.approved_at is None:
                _require_approval_selections(
                    (current, *_approval_tasks(evidence.board.by_id.values(), feature_id)),
                    root=repo,
                    inventory=inventory,
                    action="feature_approval",
                )
            newly = _set_feature_approved(feature_id, root=repo)
    result: dict[str, object] = {
        "ok": True, "feature_id": feature_id, "newly_approved": newly
    }
    _add_dispatch_warning(result, _maybe_advance_after_approval(repo))
    return result


def approve_epic_plan(
    epic_id: str,
    *,
    root: Path,
    inventory: ProviderInventoryResult | None = None,
) -> dict[str, object]:
    repo = resolve_root(root)
    with process_lock:
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
        evidence = require_action_dependencies(epic_id, root=repo)
        assert evidence.board is not None
        board = evidence.board
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
        with merged_board_snapshot(repo, board):
            if epic is not None and epic.plan_approved_at is None:
                require_epic_plan_ready_for_approval(epic_id, root=repo, board=board)
                approval_children = tuple(board.by_id[item] for item in children)
            else:
                # A repeated approval may authorize a child added after the
                # original plan approval. Existing accepted children remain
                # accepted even if current capability evidence has drifted.
                approval_children = tuple(
                    board.by_id[item]
                    for item in children
                    if board.by_id[item].approved_at is None
                )
            approval_scope = tuple(
                item
                for child in approval_children
                for item in (
                    child,
                    *_approval_tasks(board.by_id.values(), child.id),
                )
            )
            _require_approval_selections(
                approval_scope,
                root=repo,
                inventory=inventory,
                action="epic_plan_approval",
            )
            for feature_id in children:
                _set_feature_approved(feature_id, root=repo)
            # The epic timestamp durably indicates that the whole plan was approved.
            # Write it only after every child to avoid a partially approved plan.
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
    _add_dispatch_warning(result, _maybe_advance_after_approval(repo))
    return result


def _approval_tasks(metas: Iterable[WorkMeta], feature_id: str) -> tuple[WorkMeta, ...]:
    return tuple(
        sorted(
            (
                item
                for item in metas
                if item.tier == "task" and item.parent == feature_id
            ),
            key=lambda item: item.id,
        )
    )


def _require_approval_selections(
    metas: Iterable[WorkMeta],
    *,
    root: Path,
    inventory: ProviderInventoryResult | None,
    action: str,
) -> tuple[SelectionPreflight, ...]:
    """Evaluate an immutable owning-document set before the first write."""

    candidates = tuple(metas)
    if not candidates:
        return ()
    available = inventory or get_provider_inventory()
    preflights = tuple(
        _evaluate_approval_meta(
            meta,
            root=root,
            inventory=available,
            action=action,
        )
        for meta in candidates
    )
    if any(not item.result.supported for item in preflights):
        raise ApprovalSelectionError(preflights)
    return preflights


def _evaluate_approval_meta(
    meta: WorkMeta,
    *,
    root: Path,
    inventory: ProviderInventoryResult,
    action: str,
) -> SelectionPreflight:
    """Read the snapshot-selected owning path and fail safely if it went stale."""

    try:
        doc = parse_doc(meta.path)
        if doc.meta.id != meta.id or doc.meta.tier != meta.tier:
            raise ValueError("owning document identity changed")
        if (
            doc.meta.parent != meta.parent
            or doc.meta.parent_rev != meta.parent_rev
            or doc.meta.provider != meta.provider
            or doc.meta.model != meta.model
            or doc.meta.models != meta.models
            or doc.meta.reasoning != meta.reasoning
            or doc.meta.flex_mode != meta.flex_mode
        ):
            raise ValueError("owning selection changed after board snapshot")
    except Exception:
        base = evaluate_work_selection(
            meta,
            root=root,
            inventory=inventory,
            action=action,
        )
        return evaluate_work_selection(
            meta,
            root=root,
            inventory=inventory,
            action=action,
            runtime_selections=(
                RuntimeSelection(
                    role=item.role,
                    provider="__stale__",
                    model_id="__stale__",
                )
                for item in base.selections.selections
            ),
        )
    return evaluate_work_selection(
        doc,
        root=root,
        inventory=inventory,
        action=action,
    )


def _set_feature_approved(feature_id: str, *, root: Path) -> bool:
    if feature_approved(feature_id, root=root):
        return False
    doc = read_doc(feature_id, root=root)
    if doc.meta.approved_at is not None:
        return False
    doc.meta.approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True


def _maybe_advance_after_approval(root: Path) -> _DispatchWarning | None:
    from cascade.watchdog.config import read_automation_config
    from cascade.automation import reconcile_approval_dispatch

    # Approval is the dispatch trigger. Broad completion maintenance can involve
    # remote review calls or pending merges and must not hold this HTTP request
    # ahead of newly eligible work.
    refusals: list[tuple[str, DispatchResult]] = []
    try:
        if not read_automation_config(root).enabled:
            return None
        dispatched = reconcile_approval_dispatch(
            root,
            on_refusal=lambda work_id, refusal: refusals.append((work_id, refusal)),
        )
    except Exception as exc:
        # Approval is already durable. The watchdog can retry dispatch; report
        # that delay without claiming the approval itself failed.
        preflight = getattr(exc, "preflight", None)
        if isinstance(preflight, SelectionPreflight):
            preflight = preflight.result
        return _DispatchWarning(
            str(exc) or type(exc).__name__,
            preflight=preflight,
            selections=getattr(exc, "selections", None),
            refusals=tuple(refusals),
        )
    if refusals:
        first = refusals[0][1]
        assert first.preflight is not None
        return _DispatchWarning(
            first.preflight.message or first.reason or "dispatch pending",
            preflight=first.preflight,
            refusals=tuple(refusals),
            launched=tuple((*dispatched["features"], *dispatched["tasks"])),
        )
    return None


def _add_dispatch_warning(
    result: dict[str, object], warning: _DispatchWarning | None
) -> None:
    if warning is None:
        return
    result["dispatch_pending"] = True
    result["dispatch_error"] = warning.message
    result["message"] = f"Approval saved; dispatch pending: {warning.message}"
    result["approval_committed"] = True
    refused_ids = [work_id for work_id, _refusal in warning.refusals]
    result["dispatch_outcome"] = {
        "launched": list(warning.launched),
        "not_launched": refused_ids,
        "pending": True,
        "message": warning.message,
    }
    if warning.preflight is not None and hasattr(warning.preflight, "to_dict"):
        result["preflight"] = warning.preflight.to_dict()
    if warning.selections is not None and hasattr(warning.selections, "to_dict"):
        result["selections"] = warning.selections.to_dict()
    if warning.refusals:
        result["dispatch_refusals"] = [
            {
                "work_id": work_id,
                "reason": refusal.reason,
                "code": refusal.reason,
                "error": refusal.preflight.message,
                "message": refusal.preflight.message,
                "preflight": refusal.preflight.to_dict(),
                **(
                    {"selections": refusal.selections.to_dict()}
                    if refusal.selections is not None
                    else {}
                ),
            }
            for work_id, refusal in warning.refusals
            if refusal.preflight is not None
        ]
        first = warning.refusals[0][1]
        if first.selections is not None:
            result["selections"] = first.selections.to_dict()


def _set_epic_plan_approved(epic_id: str, *, root: Path) -> bool:
    doc = read_doc(epic_id, root=root)
    if doc.meta.plan_approved_at is not None:
        return False
    doc.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(doc, root=root)
    return True
