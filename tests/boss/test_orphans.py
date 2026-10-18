"""Orphan detector flags inconsistent boards without repairing them."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from cascade.board import move_doc
from cascade.board.parse import render_doc
from cascade.board.paths import column_dir, slugify
from cascade.board.store import list_board
from cascade.board.types import WorkDoc, WorkMeta
from cascade.boss.orphans import OrphanRecord, detect_orphans
from tests.support import FEATURE_BODY, make_repo, add_doc


def _write_unvalidated(root: Path, doc: WorkDoc) -> None:
    path = doc.meta.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(doc), encoding="utf-8")


def _feature_doc(
    root: Path,
    *,
    id: str,
    title: str,
    parent: str | None,
    status: str = "backlog",
) -> WorkDoc:
    from cascade.board.paths import column_for_status

    column = column_for_status(status)  # type: ignore[arg-type]
    path = root / column_dir("feature", column) / f"{id}_{slugify(title)}.md"
    return WorkDoc(
        meta=WorkMeta(
            id=id,
            title=title,
            tier="feature",
            status=status,  # type: ignore[arg-type]
            parent=parent,
            children=[],
            depends_on=[],
            owners=["tester"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 9),
            updated=date(2026, 10, 9),
            path=path,
        ),
        body=FEATURE_BODY,
    )


def test_clean_board_returns_empty(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")

    assert detect_orphans(root=root) == []
    assert list_board(root).by_id  # indexed


def test_empty_repo_returns_empty(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert detect_orphans(root=root) == []


def test_feature_without_parent_null(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_unvalidated(root, _feature_doc(root, id="feat_001", title="Lonely", parent=None))

    records = detect_orphans(root=root)
    assert len(records) == 1
    record = records[0]
    assert record.kind == "feature_without_parent"
    assert record.work_id == "feat_001"
    assert "feat_001" in record.message
    assert record.toast_payload == {
        "kind": "orphan",
        "id": "feat_001",
        "message": record.message,
    }


def test_feature_with_missing_parent_id(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _write_unvalidated(
        root,
        _feature_doc(root, id="feat_002", title="Broken link", parent="epic_999"),
    )

    records = detect_orphans(root=root)
    assert [r.kind for r in records] == ["feature_without_parent"]
    assert records[0].work_id == "feat_002"
    assert "epic_999" in records[0].message


def test_task_after_feature_completed(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Open task", tier="task", parent="feat_001")
    move_doc("feat_001", "completed", root=root)

    records = detect_orphans(root=root)
    assert len(records) == 1
    record = records[0]
    assert record == OrphanRecord(
        kind="task_after_feature_completed",
        work_id="task_001",
        message=record.message,
        toast_payload={
            "kind": "orphan",
            "id": "task_001",
            "message": record.message,
        },
    )
    assert "feat_001" in record.message
    assert "3_completed" in record.message


def test_epic_with_active_child_listed_only_on_epic_children(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Active via children list",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    move_doc("epic_001", "completed", root=root)

    records = detect_orphans(root=root)
    assert len(records) == 1
    assert records[0].kind == "epic_with_active_child"
    assert records[0].work_id == "epic_001"
    assert "feat_001" in records[0].message


def test_epic_with_active_child_in_backlog_and_active(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Backlog child", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Active child", tier="feature", parent="epic_001")
    move_doc("feat_002", "active", root=root)
    move_doc("epic_001", "completed", root=root)

    records = detect_orphans(root=root)
    assert len(records) == 1
    record = records[0]
    assert record.kind == "epic_with_active_child"
    assert record.work_id == "epic_001"
    assert "feat_001" in record.message
    assert "feat_002" in record.message
    assert record.toast_payload["kind"] == "orphan"
    assert record.toast_payload["id"] == "epic_001"
