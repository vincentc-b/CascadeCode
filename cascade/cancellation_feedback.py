"""Durable parent feedback and dispatch gate for child cancellation."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import BoardError
from cascade.board.lock import process_lock
from cascade.board.store import read_doc, save_doc
from cascade.board.types import (
    CancellationDisposition,
    CancellationFeedback,
    WorkDoc,
    WorkMeta,
)

CANCELLATION_DISPOSITIONS: tuple[CancellationDisposition, ...] = (
    "continue_reduced_scope",
    "replace_replan",
    "cancel_parent",
)


class CancellationFeedbackError(BoardError):
    """The requested feedback transition does not satisfy the contract."""


def pending_cancellation_feedback(meta: WorkMeta) -> list[CancellationFeedback]:
    """Return unresolved child-cancellation records that gate parent dispatch."""

    return [
        item for item in meta.cancellation_feedback
        if item.disposition is None
    ]


def cancellation_dispatch_gated(meta: WorkMeta) -> bool:
    """Whether this parent must pause before dispatching another child."""

    return any(
        item.disposition is None or item.disposition == "cancel_parent"
        for item in meta.cancellation_feedback
    )


def record_parent_cancellation_feedback(
    child: WorkDoc, *, root: Path
) -> CancellationFeedback | None:
    """Persist one idempotent feedback record on a cancelled child's parent.

    Epics have no parent escalation. Only a feature or task with a direct parent
    can produce this record.
    """

    if child.meta.tier == "epic":
        return None
    if child.meta.status != "cancelled":
        raise CancellationFeedbackError("feedback requires a cancelled child")
    if child.meta.parent is None:
        raise CancellationFeedbackError("cancelled child has no parent")
    if child.meta.cancellation_reason is None or child.meta.cancelled_at is None:
        raise CancellationFeedbackError("cancelled child is missing cancellation context")

    parent = read_doc(child.meta.parent, root=root)
    expected_parent_tier = "epic" if child.meta.tier == "feature" else "feature"
    if parent.meta.tier != expected_parent_tier:
        raise CancellationFeedbackError("cancelled child has an invalid parent tier")

    for existing in parent.meta.cancellation_feedback:
        if existing.child_id == child.meta.id:
            return existing

    feedback = CancellationFeedback(
        child_id=child.meta.id,
        child_tier=child.meta.tier,
        parent_id=parent.meta.id,
        reason=child.meta.cancellation_reason,
        cancelled_at=child.meta.cancelled_at,
        available_dispositions=list(CANCELLATION_DISPOSITIONS),
    )
    parent.meta.cancellation_feedback.append(feedback)
    save_doc(parent, previous_path=parent.meta.path.resolve(), root=_owner(parent, root))
    return feedback


def choose_cancellation_disposition(
    parent_id: str,
    child_id: str,
    disposition: CancellationDisposition,
    *,
    root: Path | None = None,
) -> CancellationFeedback:
    """Record and apply the user's disposition for one cancelled child.

    Reduced-scope continuation and replacement/replanning release the dispatch
    gate. Parent cancellation leaves it closed while the shared cancellation
    service tears down the parent and escalates when applicable.
    """

    if disposition not in CANCELLATION_DISPOSITIONS:
        raise CancellationFeedbackError(f"invalid cancellation disposition: {disposition}")
    repo = resolve_root(root)
    with process_lock:
        parent = read_doc(parent_id, root=repo)
        matches = [
            item for item in parent.meta.cancellation_feedback
            if item.child_id == child_id
        ]
        if not matches:
            raise CancellationFeedbackError(
                f"no cancellation feedback for {child_id} on {parent_id}"
            )
        feedback = matches[0]
        if feedback.disposition is not None:
            if feedback.disposition != disposition:
                raise CancellationFeedbackError(
                    f"cancellation feedback for {child_id} is already resolved"
                )
            selected = feedback
        else:
            feedback.disposition = disposition
            feedback.resolved_at = datetime.now(timezone.utc)
            parent.body = _record_disposition_decision(
                parent,
                child_id=child_id,
                disposition=disposition,
            )
            save_doc(
                parent,
                previous_path=parent.meta.path.resolve(),
                root=_owner(parent, repo),
            )
            selected = feedback

    if disposition == "cancel_parent":
        from cascade.cancellation import cancel_work_item

        cancel_work_item(
            parent_id,
            f"user chose cancel parent after cancellation of {child_id}",
            root=repo,
        )
    return selected


def _record_disposition_decision(
    parent: WorkDoc,
    *,
    child_id: str,
    disposition: CancellationDisposition,
) -> str:
    """Append a replay-safe human decision to the owning plan."""

    from cascade.board.decision_log import (
        append_to_decision_log,
        find_matching_decision_id,
    )

    labels = {
        "continue_reduced_scope": "continue with reduced scope",
        "replace_replan": "replace the cancelled child and replan",
        "cancel_parent": "cancel the parent",
    }
    section = f"Disposition for cancelled child {child_id}"
    choice = labels[disposition]
    if find_matching_decision_id(parent.body, section=section, choice=choice) is not None:
        return parent.body
    _, body = append_to_decision_log(
        parent.body,
        section=section,
        choice=choice,
        rationale=(
            "User disposition recorded after reviewing the child's "
            "cancellation feedback."
        ),
        honors=(
            "Parent dispatch remains gated until a user choice permits "
            "continuation"
        ),
        author="human",
        author_labels={"human": "Human"},
        missing_section_message=f"{parent.meta.tier} body missing ## Decision log section",
    )
    return body


def _owner(doc: WorkDoc, root: Path) -> Path:
    from cascade.board.gitutil import has_git

    if not has_git(root):
        return root
    from cascade.workspace.integration_worktree import git_root_for_path

    return git_root_for_path(doc.meta.path.resolve())


__all__ = [
    "CANCELLATION_DISPOSITIONS",
    "CancellationFeedbackError",
    "cancellation_dispatch_gated",
    "choose_cancellation_disposition",
    "pending_cancellation_feedback",
    "record_parent_cancellation_feedback",
]
