"""Parent cancellation feedback persistence and dispatch-gate contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc, write_doc
from cascade.board.parse import parse_text, render_doc
from cascade.cancellation import cancel_work_item
from cascade.cancellation_feedback import (
    CANCELLATION_DISPOSITIONS,
    CancellationFeedbackError,
    cancellation_dispatch_gated,
    choose_cancellation_disposition,
)
from cascade.feature.readiness import compute_feature_readiness
from cascade.watchdog.dispatch import dispatch_task
from tests.support import add_doc, make_repo


def _task_board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root, id="feat_001", title="Feature", tier="feature", parent="epic_001"
    )
    add_doc(
        root, id="task_001", title="Cancelled", tier="task", parent="feat_001"
    )
    add_doc(
        root, id="task_002", title="Waiting", tier="task", parent="feat_001"
    )
    return root


def test_task_cancellation_persists_structured_feedback_and_gates_parent(
    tmp_path: Path,
) -> None:
    root = _task_board(tmp_path)

    cancelled = cancel_work_item("task_001", "scope is no longer required", root=root)

    parent = read_doc("feat_001", root=root)
    assert cancellation_dispatch_gated(parent.meta)
    assert len(parent.meta.cancellation_feedback) == 1
    feedback = parent.meta.cancellation_feedback[0]
    assert feedback.child_id == "task_001"
    assert feedback.child_tier == "task"
    assert feedback.parent_id == "feat_001"
    assert feedback.reason == cancelled.reason
    assert feedback.cancelled_at == cancelled.cancelled_at
    assert feedback.available_dispositions == list(CANCELLATION_DISPOSITIONS)
    assert feedback.disposition is None
    assert feedback.resolved_at is None

    reparsed = parse_text(render_doc(parent), parent.meta.path)
    assert reparsed.meta.cancellation_feedback == parent.meta.cancellation_feedback

    refused = dispatch_task("task_002", "human", root=root)
    assert not refused.ok
    assert refused.reason == "parent_cancellation_pending"


@pytest.mark.parametrize("disposition", CANCELLATION_DISPOSITIONS)
def test_disposition_is_durable_idempotent_and_releases_gate(
    tmp_path: Path, disposition: str
) -> None:
    root = _task_board(tmp_path)
    cancel_work_item("task_001", "superseded", root=root)

    chosen = choose_cancellation_disposition(
        "feat_001", "task_001", disposition, root=root  # type: ignore[arg-type]
    )
    again = choose_cancellation_disposition(
        "feat_001", "task_001", disposition, root=root  # type: ignore[arg-type]
    )

    parent = read_doc("feat_001", root=root)
    assert not cancellation_dispatch_gated(parent.meta)
    assert chosen.disposition == disposition
    assert chosen.resolved_at is not None
    assert again.resolved_at == chosen.resolved_at
    assert dispatch_task("task_002", "human", root=root).ok


def test_feedback_is_emitted_once_and_cannot_be_redecided(tmp_path: Path) -> None:
    root = _task_board(tmp_path)
    cancel_work_item("task_001", "superseded", root=root)
    cancel_work_item("task_001", "different reason", root=root)
    assert len(read_doc("feat_001", root=root).meta.cancellation_feedback) == 1

    choose_cancellation_disposition(
        "feat_001", "task_001", "replace_replan", root=root
    )
    with pytest.raises(CancellationFeedbackError, match="already resolved"):
        choose_cancellation_disposition(
            "feat_001", "task_001", "cancel_parent", root=root
        )


def test_epic_cancellation_does_not_escalate(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")

    result = cancel_work_item("epic_001", "initiative withdrawn", root=root)

    assert result.complete
    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "cancelled"
    assert epic.meta.cancellation_feedback == []


def test_feature_cancellation_gates_epic_feature_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    move_doc("epic_001", "active", root=root)
    add_doc(
        root, id="feat_001", title="Cancelled", tier="feature", parent="epic_001"
    )
    waiting = add_doc(
        root, id="feat_002", title="Waiting", tier="feature", parent="epic_001"
    )
    waiting.meta.approved_at = cancelled_at = cancel_work_item(
        "feat_001", "replace the approach", root=root
    ).cancelled_at
    write_doc(waiting, root=root)
    readiness = compute_feature_readiness("feat_002", root=root)

    assert cancelled_at is not None
    assert readiness is not None
    assert "parent_cancellation_pending" in readiness.blockers
    epic = read_doc("epic_001", root=root)
    assert epic.meta.cancellation_feedback[0].child_tier == "feature"
