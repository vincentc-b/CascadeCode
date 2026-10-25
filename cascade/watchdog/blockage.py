"""Provenance-aware propagation of an unresolved direct-report blockage."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.board.errors import SchemaError
from cascade.board.store import read_doc, write_doc
from cascade.board.types import MonitoringBlocker, WorkDoc
from cascade.workspace.integration_worktree import git_root_for_path

TERMINAL_STATUSES = frozenset({"completed", "cancelled"})
PropagationOutcome = Literal["applied", "already_applied", "terminal", "conflict"]
ReconciliationOutcome = Literal["applied", "already_applied", "terminal", "conflict"]


@dataclass(frozen=True)
class BlockagePropagationResult:
    outcome: PropagationOutcome
    supervisor_id: str
    child_id: str

    @property
    def ok(self) -> bool:
        return self.outcome in {"applied", "already_applied", "terminal"}


@dataclass(frozen=True)
class BlockageReconciliationResult:
    outcome: ReconciliationOutcome
    supervisor_id: str
    child_id: str

    @property
    def ok(self) -> bool:
        return self.outcome in {"applied", "already_applied", "terminal"}


def propagate_direct_report_blockage(
    supervisor: WorkDoc,
    child: WorkDoc,
    reason: str,
    *,
    root: Path,
) -> BlockagePropagationResult:
    """Persist one child's unresolved condition on its immediate supervisor.

    The observed supervisor SHA is the optimistic concurrency token. A stale
    write succeeds only when a re-read contains the exact same cause.
    """

    _validate_pair(supervisor, child)
    concise_reason = _concise_reason(reason)
    if (
        supervisor.meta.status in TERMINAL_STATUSES
        or child.meta.status in TERMINAL_STATUSES
    ):
        return BlockagePropagationResult("terminal", supervisor.meta.id, child.meta.id)
    if _matching_blocker(supervisor, child.meta.id, concise_reason) is not None:
        return BlockagePropagationResult(
            "already_applied", supervisor.meta.id, child.meta.id
        )
    if supervisor.meta.status not in {"active", "blocked"}:
        return BlockagePropagationResult("conflict", supervisor.meta.id, child.meta.id)

    current_child = read_doc(child.meta.id, root=root)
    if (
        current_child.sha != child.sha
        or current_child.meta.parent != supervisor.meta.id
        or current_child.meta.status != child.meta.status
    ):
        return BlockagePropagationResult("conflict", supervisor.meta.id, child.meta.id)

    updated = deepcopy(supervisor)
    owns_transition = supervisor.meta.status == "active"
    updated.meta.status = "blocked"
    existing_index = next(
        (
            index
            for index, item in enumerate(updated.meta.monitoring_blockers)
            if item.child_id == child.meta.id
        ),
        None,
    )
    if existing_index is None:
        updated.meta.monitoring_blockers.append(
            MonitoringBlocker(child.meta.id, concise_reason, owns_transition)
        )
    else:
        previous = updated.meta.monitoring_blockers[existing_index]
        updated.meta.monitoring_blockers[existing_index] = MonitoringBlocker(
            child.meta.id, concise_reason, previous.blocked_supervisor
        )
    owner_root = git_root_for_path(updated.meta.path.resolve())
    try:
        write_doc(updated, root=owner_root)
    except SchemaError as exc:
        if "stale sha" not in str(exc):
            raise
        current = read_doc(supervisor.meta.id, root=root)
        if current.meta.status in TERMINAL_STATUSES:
            return BlockagePropagationResult(
                "terminal", supervisor.meta.id, child.meta.id
            )
        if _matching_blocker(current, child.meta.id, concise_reason) is not None:
            return BlockagePropagationResult(
                "already_applied", supervisor.meta.id, child.meta.id
            )
        return BlockagePropagationResult("conflict", supervisor.meta.id, child.meta.id)
    return BlockagePropagationResult("applied", supervisor.meta.id, child.meta.id)



def reconcile_direct_report_blockage(
    supervisor: WorkDoc,
    child: WorkDoc,
    *,
    root: Path,
) -> BlockageReconciliationResult:
    """Remove this child's derived cause after its condition has cleared.

    Ownership of the blocked transition follows the remaining derived causes.
    That lets sibling incidents clear independently while ensuring a supervisor
    is reactivated only when monitoring performed the original transition.
    """

    _validate_pair(supervisor, child)
    if supervisor.meta.status in TERMINAL_STATUSES:
        return BlockageReconciliationResult(
            "terminal", supervisor.meta.id, child.meta.id
        )
    blocker_index = next(
        (
            index
            for index, item in enumerate(supervisor.meta.monitoring_blockers)
            if item.child_id == child.meta.id
        ),
        None,
    )
    if blocker_index is None:
        return BlockageReconciliationResult(
            "already_applied", supervisor.meta.id, child.meta.id
        )
    if supervisor.meta.status != "blocked":
        return BlockageReconciliationResult(
            "conflict", supervisor.meta.id, child.meta.id
        )

    current_child = read_doc(child.meta.id, root=root)
    if (
        current_child.sha != child.sha
        or current_child.meta.parent != supervisor.meta.id
        or current_child.meta.status != child.meta.status
    ):
        return BlockageReconciliationResult(
            "conflict", supervisor.meta.id, child.meta.id
        )

    updated = deepcopy(supervisor)
    removed = updated.meta.monitoring_blockers.pop(blocker_index)
    if removed.blocked_supervisor:
        if updated.meta.monitoring_blockers:
            successor = updated.meta.monitoring_blockers[0]
            updated.meta.monitoring_blockers[0] = MonitoringBlocker(
                successor.child_id, successor.reason, True
            )
        else:
            updated.meta.status = "active"
    owner_root = git_root_for_path(updated.meta.path.resolve())
    try:
        write_doc(updated, root=owner_root)
    except SchemaError as exc:
        if "stale sha" not in str(exc):
            raise
        current = read_doc(supervisor.meta.id, root=root)
        if current.meta.status in TERMINAL_STATUSES:
            return BlockageReconciliationResult(
                "terminal", supervisor.meta.id, child.meta.id
            )
        if not any(
            item.child_id == child.meta.id
            for item in current.meta.monitoring_blockers
        ):
            return BlockageReconciliationResult(
                "already_applied", supervisor.meta.id, child.meta.id
            )
        return BlockageReconciliationResult(
            "conflict", supervisor.meta.id, child.meta.id
        )
    return BlockageReconciliationResult("applied", supervisor.meta.id, child.meta.id)


def _validate_pair(supervisor: WorkDoc, child: WorkDoc) -> None:
    expected_child_tier = {"epic": "feature", "feature": "task"}.get(
        supervisor.meta.tier
    )
    if expected_child_tier is None or child.meta.tier != expected_child_tier:
        raise ValueError("blockage propagation requires an epic/feature direct-report pair")
    if child.meta.parent != supervisor.meta.id:
        raise ValueError(f"{child.meta.id} is not a direct report of {supervisor.meta.id}")


def _concise_reason(reason: str) -> str:
    concise = " ".join(reason.split())
    if not concise:
        raise ValueError("blockage reason must be non-blank")
    if len(concise) > 240:
        raise ValueError("blockage reason must be at most 240 characters")
    return concise


def _matching_blocker(
    supervisor: WorkDoc, child_id: str, reason: str
) -> MonitoringBlocker | None:
    return next(
        (
            item
            for item in supervisor.meta.monitoring_blockers
            if item.child_id == child_id and item.reason == reason
        ),
        None,
    )
