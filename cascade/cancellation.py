"""Unified cancellation command for epics, features, and tasks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cascade.board.context import resolve_root
from cascade.board.errors import BoardError
from cascade.board.gitutil import has_git
from cascade.board.lock import process_lock
from cascade.board.paths import column_dir
from cascade.board.store import read_doc, save_doc
from cascade.board.types import WorkDoc, WorkId


class CancellationError(BoardError):
    """A stable, user-facing cancellation validation or transition error."""

    code: str

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class CancellationReasonRequired(CancellationError):
    def __init__(self) -> None:
        super().__init__("reason_required", "cancellation reason must not be blank")


class CancellationTransitionRejected(CancellationError):
    def __init__(self, work_id: WorkId, status: str) -> None:
        super().__init__("transition_rejected", f"cannot cancel {work_id} from status {status}")


@dataclass(frozen=True)
class CancellationResult:
    work_id: WorkId
    tier: str
    reason: str
    cancelled_at: datetime
    changed: bool


CancellationEffect = Callable[[CancellationResult, Path], None]


def cancel_work_item(
    work_id: WorkId,
    reason: str,
    *,
    root: Path | None = None,
    effect: CancellationEffect | None = None,
) -> CancellationResult:
    """Cancel any work tier through one transition contract.

    The board transition is committed before the effect is invoked. Repeated
    cancellation returns the original result and deliberately skips the effect.
    """

    normalized_reason = reason.strip() if isinstance(reason, str) else ""
    if not normalized_reason:
        raise CancellationReasonRequired()

    repo = resolve_root(root)
    with process_lock:
        doc = read_doc(work_id, root=repo)
        if doc.meta.status == "cancelled":
            return _existing_result(doc)
        if doc.meta.status == "completed":
            raise CancellationTransitionRejected(work_id, doc.meta.status)
        if doc.meta.status not in {"backlog", "ready_to_plan", "active", "blocked"}:
            raise CancellationTransitionRejected(work_id, doc.meta.status)

        previous_path = doc.meta.path.resolve()
        if has_git(repo):
            from cascade.workspace.integration_worktree import git_root_for_path

            owner_root = git_root_for_path(previous_path)
        else:
            owner_root = repo
        doc.meta.status = "cancelled"
        doc.meta.cancellation_reason = normalized_reason
        doc.meta.cancelled_at = datetime.now(timezone.utc)
        doc.meta.path = (
            owner_root / column_dir(doc.meta.tier, "completed") / previous_path.name
        ).resolve()
        save_doc(doc, previous_path=previous_path, root=owner_root)
        result = CancellationResult(
            work_id=doc.meta.id,
            tier=doc.meta.tier,
            reason=normalized_reason,
            cancelled_at=doc.meta.cancelled_at,
            changed=True,
        )

    if effect is not None:
        effect(result, repo)
    return result


def _existing_result(doc: WorkDoc) -> CancellationResult:
    if doc.meta.cancellation_reason is None or doc.meta.cancelled_at is None:
        raise CancellationError(
            "invalid_cancelled_record",
            f"cancelled work item {doc.meta.id} is missing cancellation metadata",
        )
    return CancellationResult(
        work_id=doc.meta.id,
        tier=doc.meta.tier,
        reason=doc.meta.cancellation_reason,
        cancelled_at=doc.meta.cancelled_at,
        changed=False,
    )


__all__ = [
    "CancellationError",
    "CancellationReasonRequired",
    "CancellationResult",
    "CancellationTransitionRejected",
    "cancel_work_item",
]
