"""Unified work-item cancellation acceptance contract."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc
from cascade.cancellation import (
    CancellationReasonRequired,
    CancellationResult,
    CancellationTransitionRejected,
    cancel_work_item,
)
from tests.support import add_doc, make_repo


@pytest.mark.parametrize(
    ("work_id", "tier", "parent"),
    [
        ("epic_001", "epic", None),
        ("feat_001", "feature", "epic_001"),
        ("task_001", "task", "feat_001"),
    ],
)
@pytest.mark.parametrize("initial_status", ["backlog", "active"])
def test_cancel_work_item_has_one_contract_for_every_tier(
    tmp_path: Path,
    work_id: str,
    tier: str,
    parent: str | None,
    initial_status: str,
) -> None:
    root = make_repo(tmp_path, git=False)
    if tier in ("feature", "task"):
        add_doc(root, id="epic_001", title="Epic", tier="epic")
    if tier == "task":
        add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    original = add_doc(root, id=work_id, title="Work", tier=tier, parent=parent)
    if initial_status == "active":
        move_doc(work_id, "active", root=root)

    observed: list[tuple[str, str, str | None, object]] = []

    def observe_persisted_cancellation(
        value: CancellationResult, _root: Path
    ) -> None:
        stored = read_doc(value.work_id, root=root)
        observed.append(
            (
                stored.meta.id,
                stored.meta.status,
                stored.meta.cancellation_reason,
                stored.meta.cancelled_at,
            )
        )

    result = cancel_work_item(
        work_id,
        "  superseded by a smaller approach  ",
        root=root,
        effect=observe_persisted_cancellation,
    )

    stored = read_doc(work_id, root=root)
    assert result.changed is True
    assert stored.meta.status == "cancelled"
    assert stored.meta.path.parent.name == "3_completed"
    assert stored.meta.cancellation_reason == "superseded by a smaller approach"
    assert stored.meta.cancelled_at == result.cancelled_at
    assert observed == [
        (
            work_id,
            "cancelled",
            "superseded by a smaller approach",
            result.cancelled_at,
        )
    ]
    assert not original.meta.path.exists()

    again = cancel_work_item(
        work_id,
        "a different reason",
        root=root,
        effect=observe_persisted_cancellation,
    )
    assert again.changed is False
    assert again.reason == result.reason
    assert again.cancelled_at == result.cancelled_at
    assert read_doc(work_id, root=root).meta.cancellation_reason == result.reason
    assert len(observed) == 1


@pytest.mark.parametrize("reason", [None, " \n\t "])
def test_cancel_rejects_missing_or_blank_reason_without_mutation(
    tmp_path: Path, reason: str | None
) -> None:
    root = make_repo(tmp_path, git=False)
    doc = add_doc(root, id="epic_001", title="Epic", tier="epic")
    before = doc.meta.path.read_bytes()

    with pytest.raises(CancellationReasonRequired) as exc_info:
        cancel_work_item("epic_001", reason, root=root)  # type: ignore[arg-type]

    assert exc_info.value.code == "reason_required"
    stored = read_doc("epic_001", root=root)
    assert stored.meta.path == doc.meta.path
    assert stored.meta.path.read_bytes() == before


@pytest.mark.parametrize(
    ("work_id", "tier", "parent"),
    [
        ("epic_001", "epic", None),
        ("feat_001", "feature", "epic_001"),
        ("task_001", "task", "feat_001"),
    ],
)
def test_cancel_rejects_completed_work_without_mutation(
    tmp_path: Path, work_id: str, tier: str, parent: str | None
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    if tier == "task":
        add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    if tier != "epic":
        add_doc(root, id=work_id, title="Work", tier=tier, parent=parent)
    move_doc(work_id, "completed", root=root)
    before = read_doc(work_id, root=root)
    before_bytes = before.meta.path.read_bytes()

    with pytest.raises(CancellationTransitionRejected) as exc_info:
        cancel_work_item(
            work_id,
            "too late",
            root=root,
            effect=lambda *_: pytest.fail("rejected cancellation emitted its effect"),
        )

    assert exc_info.value.code == "transition_rejected"
    after = read_doc(work_id, root=root)
    assert after.meta.status == "completed"
    assert after.meta.cancellation_reason is None
    assert after.meta.cancelled_at is None
    assert after.meta.path == before.meta.path
    assert after.meta.path.read_bytes() == before_bytes
