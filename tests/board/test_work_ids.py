"""Canonical hierarchical work id parse, validate, and allocation."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from cascade.board.errors import SchemaError
from cascade.board.id_reservations import reset_id_reservations, reserve_work_id
from cascade.board.types import BoardIndex, WorkMeta
from cascade.board.work_ids import (
    allocate_hierarchical_id,
    format_hierarchical_feature_id,
    format_hierarchical_task_id,
    parse_work_id_parts,
    validate_work_id_identity,
)


def _meta(
    work_id: str,
    *,
    tier: str,
    parent: str | None,
    path: Path | None = None,
) -> WorkMeta:
    return WorkMeta(
        id=work_id,
        title="t",
        tier=tier,  # type: ignore[arg-type]
        status="backlog",
        parent=parent,
        children=[],
        depends_on=[],
        owners=[],
        skills=[],
        parent_rev=None,
        created=date.today(),
        updated=date.today(),
        path=path or Path(f"docs/{tier}s/1_backlog/{work_id}_t.md"),
    )


def test_parse_hierarchical_and_legacy_shapes() -> None:
    assert parse_work_id_parts("epic_004").segments == (4,)
    assert parse_work_id_parts("feat_009").form == "legacy"
    parsed = parse_work_id_parts("feat_004_002")
    assert parsed.form == "hierarchical"
    assert parsed.segments == (4, 2)
    assert parse_work_id_parts("task_004_002_003").segments == (4, 2, 3)
    assert parse_work_id_parts("task_009_000_001").segments == (9, 0, 1)


def test_rejects_malformed_ids() -> None:
    for bad in (
        "epic_004_001",
        "feat_004_002_003",
        "task_004_002",
        "feature_001",
        "task_0",
        "epic_000",
    ):
        with pytest.raises(SchemaError):
            parse_work_id_parts(bad)


def test_validate_parent_scoping_for_hierarchical_ids() -> None:
    validate_work_id_identity(
        "feat_004_001",
        tier="feature",
        parent="epic_004",
    )
    validate_work_id_identity(
        "task_004_001_002",
        tier="task",
        parent="feat_004_001",
    )
    validate_work_id_identity(
        "task_009_000_003",
        tier="task",
        parent="feat_009",
    )
    with pytest.raises(SchemaError):
        validate_work_id_identity(
            "feat_004_001",
            tier="feature",
            parent="epic_003",
        )
    with pytest.raises(SchemaError):
        validate_work_id_identity(
            "task_004_001_002",
            tier="task",
            parent="feat_004_002",
        )


def test_allocate_epic_uses_monotonic_global_numbers() -> None:
    reset_id_reservations()
    board = BoardIndex(
        by_id={
            "epic_002": _meta("epic_002", tier="epic", parent=None),
            "epic_004": _meta("epic_004", tier="epic", parent=None),
        }
    )
    assert allocate_hierarchical_id("epic", board) == "epic_005"
    reset_id_reservations()
    board_gap = BoardIndex(
        by_id={
            "epic_001": _meta("epic_001", tier="epic", parent=None),
            "epic_003": _meta("epic_003", tier="epic", parent=None),
        }
    )
    assert allocate_hierarchical_id("epic", board_gap) == "epic_004"


def test_allocate_feature_scoped_to_parent_epic() -> None:
    reset_id_reservations()
    board = BoardIndex(
        by_id={
            "epic_004": _meta("epic_004", tier="epic", parent=None),
            "feat_004_001": _meta(
                "feat_004_001",
                tier="feature",
                parent="epic_004",
            ),
            "feat_009": _meta("feat_009", tier="feature", parent="epic_004"),
            "feat_003_001": _meta(
                "feat_003_001",
                tier="feature",
                parent="epic_003",
            ),
        }
    )
    assert allocate_hierarchical_id("feature", board, parent_id="epic_004") == "feat_004_010"
    reset_id_reservations()
    assert allocate_hierarchical_id("feature", board, parent_id="epic_003") == "feat_003_002"


def test_allocate_task_scoped_to_parent_feature() -> None:
    reset_id_reservations()
    board = BoardIndex(
        by_id={
            "feat_004_002": _meta(
                "feat_004_002",
                tier="feature",
                parent="epic_004",
            ),
            "task_004_002_001": _meta(
                "task_004_002_001",
                tier="task",
                parent="feat_004_002",
            ),
        }
    )
    assert allocate_hierarchical_id("task", board, parent_id="feat_004_002") == "task_004_002_002"

    reset_id_reservations()
    board_legacy = BoardIndex(
        by_id={
            "feat_009": _meta("feat_009", tier="feature", parent="epic_004"),
            "task_009_000_004": _meta(
                "task_009_000_004",
                tier="task",
                parent="feat_009",
            ),
        }
    )
    assert (
        allocate_hierarchical_id("task", board_legacy, parent_id="feat_009")
        == "task_009_000_005"
    )


def test_allocate_rejects_collisions() -> None:
    reset_id_reservations()
    board = BoardIndex(
        by_id={
            "epic_001": _meta("epic_001", tier="epic", parent=None),
            "feat_001_001": _meta(
                "feat_001_001",
                tier="feature",
                parent="epic_001",
            ),
        }
    )
    reserve_work_id("feat_001_002")
    with pytest.raises(SchemaError, match="collision"):
        allocate_hierarchical_id("feature", board, parent_id="epic_001")
