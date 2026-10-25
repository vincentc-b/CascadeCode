"""Unified cancellation command for epics, features, and tasks."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from cascade.board.context import resolve_root
from cascade.board.errors import BoardError
from cascade.board.gitutil import has_git
from cascade.board.lock import process_lock
from cascade.board.paths import column_dir
from cascade.board.store import list_board, read_doc, save_doc
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
    complete: bool = True
    cleanup_step: str = "complete"
    cleanup_error: str | None = None


CancellationEffect = Callable[[CancellationResult, Path], None]


def cancel_work_item(
    work_id: WorkId,
    reason: str,
    *,
    root: Path | None = None,
    effect: CancellationEffect | None = None,
    discard_uncommitted: bool = False,
) -> CancellationResult:
    """Cancel one work item and tear down only its registered local artifacts.

    Active cleanup is checkpointed as cancelling before Git side effects.
    A refusal or partial failure remains visible and a repeated call resumes the
    exact owned teardown. Terminal cancelled is persisted only after cleanup.
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
        if doc.meta.status not in {
            "backlog", "ready_to_plan", "active", "blocked", "cancelling"
        }:
            raise CancellationTransitionRejected(work_id, doc.meta.status)

        retrying = doc.meta.status == "cancelling"
        if retrying:
            if doc.meta.cancellation_reason is None or doc.meta.cancelled_at is None:
                raise CancellationError(
                    "invalid_cancelling_record",
                    f"cancelling work item {work_id} is missing cancellation metadata",
                )
        else:
            doc.meta.status = "cancelling"
            doc.meta.cancellation_reason = normalized_reason
            doc.meta.cancelled_at = datetime.now(timezone.utc)
        previous_path = doc.meta.path.resolve()
        owner_root = _doc_owner(doc, repo)
        doc.meta.cancellation_step = "owned_artifact_teardown"
        doc.meta.cancellation_error = None
        if doc.meta.path.parent.name == "1_backlog":
            doc.meta.path = (
                owner_root / column_dir(doc.meta.tier, "active") / previous_path.name
            ).resolve()
        save_doc(doc, previous_path=previous_path, root=owner_root)
        _stage_cancellation_record(doc, repo, owner_root)

    teardown = _teardown_owned_artifacts(
        doc, repo, discard_uncommitted=discard_uncommitted
    )
    with process_lock:
        doc = read_doc(work_id, root=repo)
        if not teardown.complete:
            doc.meta.status = "cancelling"
            doc.meta.cancellation_step = teardown.step
            doc.meta.cancellation_error = teardown.detail or "cleanup did not complete"
            save_doc(doc, previous_path=doc.meta.path.resolve(), root=_doc_owner(doc, repo))
            return CancellationResult(
                work_id=doc.meta.id,
                tier=doc.meta.tier,
                reason=doc.meta.cancellation_reason or normalized_reason,
                cancelled_at=doc.meta.cancelled_at or datetime.now(timezone.utc),
                changed=not retrying,
                complete=False,
                cleanup_step=teardown.step,
                cleanup_error=doc.meta.cancellation_error,
            )

        previous_path = doc.meta.path.resolve()
        owner_root = _doc_owner(doc, repo)
        doc.meta.status = "cancelled"
        doc.meta.cancellation_step = "complete"
        doc.meta.cancellation_error = None
        doc.meta.path = (
            owner_root / column_dir(doc.meta.tier, "completed") / previous_path.name
        ).resolve()
        save_doc(doc, previous_path=previous_path, root=owner_root)
        result = CancellationResult(
            work_id=doc.meta.id,
            tier=doc.meta.tier,
            reason=doc.meta.cancellation_reason or normalized_reason,
            cancelled_at=doc.meta.cancelled_at or datetime.now(timezone.utc),
            changed=not retrying,
        )

    if effect is not None:
        effect(result, repo)
    return result


def _doc_owner(doc: WorkDoc, repo: Path) -> Path:
    if not has_git(repo):
        return repo
    from cascade.workspace.integration_worktree import git_root_for_path

    return git_root_for_path(doc.meta.path.resolve())



def _stage_cancellation_record(doc: WorkDoc, repo: Path, owner_root: Path) -> None:
    """Persist lifecycle state outside an integration checkout before deleting it."""

    if not has_git(repo):
        return
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        locate_trunk,
    )

    trunk = locate_trunk(repo)
    owned = get_integration_worktree(trunk, doc.meta.tier, doc.meta.id)
    if owned is None or owned.path.resolve() != owner_root.resolve():
        return
    if doc.meta.tier == "epic" or doc.meta.parent is None:
        target = trunk
    else:
        parent_kind = "epic" if doc.meta.tier == "feature" else "feature"
        parent = get_integration_worktree(trunk, parent_kind, doc.meta.parent)
        target = parent.path if parent is not None else trunk

    staged = deepcopy(doc)
    existing = list_board(target).by_id.get(doc.meta.id)
    previous = existing.path.resolve() if existing is not None else None
    filename = previous.name if previous is not None else doc.meta.path.name
    staged.meta.path = (
        target / column_dir(doc.meta.tier, "active") / filename
    ).resolve()
    staged.sha = None
    save_doc(staged, previous_path=previous, root=target)

def _teardown_owned_artifacts(
    doc: WorkDoc, repo: Path, *, discard_uncommitted: bool = False
):
    if not has_git(repo):
        from cascade.workspace.integration_worktree import CancellationTeardownResult

        return CancellationTeardownResult(True, "complete")
    from cascade.workspace.integration_worktree import cancel_integration_worktree

    return cancel_integration_worktree(
        doc.meta.tier,
        doc.meta.id,
        trunk=repo,
        discard_uncommitted=discard_uncommitted,
    )


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
