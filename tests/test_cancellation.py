"""Unified work-item cancellation contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc
from cascade.cancellation import (
    CancellationReasonRequired,
    CancellationTransitionRejected,
    cancel_work_item,
)
from tests.support import add_doc, make_repo


@pytest.mark.parametrize(
    ("work_id", "tier", "parent", "active"),
    [
        ("epic_001", "epic", None, False),
        ("feat_001", "feature", "epic_001", True),
        ("task_001", "task", "feat_001", False),
    ],
)
def test_cancel_work_item_has_one_contract_for_every_tier(
    tmp_path: Path,
    work_id: str,
    tier: str,
    parent: str | None,
    active: bool,
) -> None:
    root = make_repo(tmp_path, git=False)
    if tier in ("feature", "task"):
        add_doc(root, id="epic_001", title="Epic", tier="epic")
    if tier == "task":
        add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    original = add_doc(root, id=work_id, title="Work", tier=tier, parent=parent)
    if active:
        move_doc(work_id, "active", root=root)

    observed: list[tuple[str, str]] = []
    result = cancel_work_item(
        work_id,
        "  superseded by a smaller approach  ",
        root=root,
        effect=lambda value, _root: observed.append(
            (value.work_id, read_doc(value.work_id, root=root).meta.status)
        ),
    )

    stored = read_doc(work_id, root=root)
    assert result.changed is True
    assert stored.meta.status == "cancelled"
    assert stored.meta.path.parent.name == "3_completed"
    assert stored.meta.cancellation_reason == "superseded by a smaller approach"
    assert stored.meta.cancelled_at == result.cancelled_at
    assert observed == [(work_id, "cancelled")]
    assert not original.meta.path.exists()

    again = cancel_work_item(
        work_id,
        "a different reason",
        root=root,
        effect=lambda *_: pytest.fail("idempotent cancellation replayed its effect"),
    )
    assert again.changed is False
    assert again.reason == result.reason
    assert again.cancelled_at == result.cancelled_at
    assert read_doc(work_id, root=root).meta.cancellation_reason == result.reason


def test_cancel_rejects_blank_reason_without_mutation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    doc = add_doc(root, id="epic_001", title="Epic", tier="epic")

    with pytest.raises(CancellationReasonRequired) as exc_info:
        cancel_work_item("epic_001", " \n\t ", root=root)

    assert exc_info.value.code == "reason_required"
    assert read_doc("epic_001", root=root).meta.path == doc.meta.path


def test_cancel_rejects_completed_work_without_mutation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    move_doc("epic_001", "completed", root=root)
    before = read_doc("epic_001", root=root)

    with pytest.raises(CancellationTransitionRejected) as exc_info:
        cancel_work_item("epic_001", "too late", root=root)

    assert exc_info.value.code == "transition_rejected"
    after = read_doc("epic_001", root=root)
    assert after.meta.status == "completed"
    assert after.meta.cancellation_reason is None
    assert after.meta.path == before.meta.path
