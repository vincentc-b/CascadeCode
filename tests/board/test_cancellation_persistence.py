"""Cancellation lifecycle persistence coverage."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc, write_doc
from cascade.board.parse import parse_text, render_doc
from tests.support import add_doc, make_repo


@pytest.mark.parametrize(
    ("work_id", "tier", "parent"),
    [
        ("epic_001", "epic", None),
        ("feat_001", "feature", "epic_001"),
        ("task_001", "task", "feat_001"),
    ],
)
def test_cancelled_work_round_trips_metadata_at_every_tier(
    tmp_path: Path, work_id: str, tier: str, parent: str | None
) -> None:
    root = make_repo(tmp_path, git=False)
    if tier in ("feature", "task"):
        add_doc(root, id="epic_001", title="Parent epic", tier="epic")
    if tier == "task":
        add_doc(
            root,
            id="feat_001",
            title="Parent feature",
            tier="feature",
            parent="epic_001",
        )
    doc = add_doc(
        root,
        id=work_id,
        title=f"Cancelled {tier}",
        tier=tier,
        parent=parent,
    )
    move_doc(work_id, "completed", root=root)
    doc = read_doc(work_id, root=root)
    doc.meta.status = "cancelled"
    doc.meta.cancellation_reason = "No longer aligned with current priorities"
    doc.meta.cancelled_at = datetime(2026, 10, 25, 12, 30, tzinfo=timezone.utc)

    write_doc(doc, root=root)
    again = read_doc(work_id, root=root)
    rendered = render_doc(again)
    reparsed = parse_text(rendered, again.meta.path)

    assert again.meta.status == "cancelled"
    assert again.meta.path.parent.name == "3_completed"
    assert again.meta.cancellation_reason == doc.meta.cancellation_reason
    assert again.meta.cancelled_at == doc.meta.cancelled_at
    assert reparsed.meta.status == again.meta.status
    assert reparsed.meta.cancellation_reason == again.meta.cancellation_reason
    assert reparsed.meta.cancelled_at == again.meta.cancelled_at


def test_legacy_record_without_cancellation_metadata_is_unchanged(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    doc = add_doc(root, id="epic_001", title="Legacy epic", tier="epic")

    again = parse_text(render_doc(doc), doc.meta.path)

    assert again.meta.status == doc.meta.status
    assert again.meta.cancellation_reason is None
    assert again.meta.cancelled_at is None
    assert "cancellation_reason:" not in render_doc(again)
    assert "cancelled_at:" not in render_doc(again)
