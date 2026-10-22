"""Backlog epic migration preflight (task_021)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.board.backlog_migration import (
    BacklogMigrationValidationError,
    build_backlog_migration_plan,
)
from cascade.board.store import pin_parent, read_doc, write_doc
from tests.support import TASK_BODY, add_doc, make_repo


def _body_with_parent_link(feature_id: str) -> str:
    return TASK_BODY.replace(
        "Parent feature and parent_rev.",
        f"[{feature_id}](../../features/2_active/{feature_id}.md)",
    )


def test_maps_legacy_backlog_tree_under_backlog_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Active epic", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="Legacy feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    add_doc(
        root,
        id="task_001",
        title="Legacy task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )
    pin_parent("feat_001", "epic_002", root=root)
    pin_parent("task_001", "feat_001", root=root)

    plan = build_backlog_migration_plan(root=root)

    assert plan.scoped_ids == frozenset({"epic_002", "feat_001", "task_001"})
    assert dict(plan.renames) == {
        "feat_001": "feat_002_001",
        "task_001": "task_002_001_001",
    }
    assert len(plan.path_updates) == 2
    assert "epic_004" not in plan.scoped_ids


def test_reserves_numbers_from_existing_hierarchical_siblings(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_002_001",
        title="Already hierarchical sibling",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    add_doc(
        root,
        id="feat_003",
        title="Legacy backlog feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    pin_parent("feat_002_001", "epic_002", root=root)
    pin_parent("feat_003", "epic_002", root=root)

    plan = build_backlog_migration_plan(root=root)

    assert dict(plan.renames) == {"feat_003": "feat_002_002"}


def test_rejects_active_descendant_under_backlog_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="Active feature",
        tier="feature",
        status="active",
        parent="epic_002",
    )
    pin_parent("feat_001", "epic_002", root=root)

    with pytest.raises(BacklogMigrationValidationError) as exc:
        build_backlog_migration_plan(root=root)
    assert any("backlog-only" in err for err in exc.value.errors)


def test_rejects_inbound_reference_from_active_work(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="Backlog feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    add_doc(
        root,
        id="epic_004",
        title="Active epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    pin_parent("feat_001", "epic_002", root=root)

    with pytest.raises(BacklogMigrationValidationError) as exc:
        build_backlog_migration_plan(root=root)
    assert any("active/completed work must remain unchanged" in err for err in exc.value.errors)


def test_noop_when_backlog_epic_has_no_legacy_descendants(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_002_001",
        title="Already hierarchical",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    pin_parent("feat_002_001", "epic_002", root=root)

    plan = build_backlog_migration_plan(root=root)

    assert plan.renames == ()
    assert plan.path_updates == ()


def test_plan_is_deterministic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_010",
        title="Ten",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    add_doc(
        root,
        id="feat_002",
        title="Two",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    pin_parent("feat_010", "epic_002", root=root)
    pin_parent("feat_002", "epic_002", root=root)

    first = build_backlog_migration_plan(root=root)
    second = build_backlog_migration_plan(root=root)

    assert first.id_mapping == second.id_mapping
    assert dict(first.renames) == {
        "feat_002": "feat_002_001",
        "feat_010": "feat_002_002",
    }


def test_enumerates_body_reference_updates(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="Legacy feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    add_doc(
        root,
        id="task_001",
        title="Legacy task",
        tier="task",
        status="backlog",
        parent="feat_001",
        depends_on=["feat_001"],
    )
    pin_parent("feat_001", "epic_002", root=root)
    pin_parent("task_001", "feat_001", root=root)

    task_doc = read_doc("task_001", root=root)
    task_doc.body = _body_with_parent_link("feat_001")
    write_doc(task_doc, root=root)

    plan = build_backlog_migration_plan(root=root)

    assert any(row.location == "meta.depends_on[0]" for row in plan.reference_updates)
    assert any(row.location.startswith("body:") for row in plan.reference_updates)


def test_rejects_event_queue_runtime_artifact(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="Legacy feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
    )
    pin_parent("feat_001", "epic_002", root=root)
    queue = root / "docs" / "_queue" / "feat_001.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text('{"type":"noop"}\n', encoding="utf-8")

    with pytest.raises(BacklogMigrationValidationError) as exc:
        build_backlog_migration_plan(root=root)
    assert any("event queue sidecar" in err for err in exc.value.errors)
