"""Hierarchical id allocation wired through mint and persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.epic.mint  # noqa: F401
import cascade.feature.mint  # noqa: F401
from cascade.board.errors import SchemaError
from cascade.board.store import list_board, read_doc, reset_id_reservations, write_doc
from cascade.board.types import WorkDoc
from cascade.epic.mint import mint_feature
from cascade.feature.mint import mint_task
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _reset_ids() -> None:
    reset_id_reservations()
    yield
    reset_id_reservations()


def test_mint_feature_emits_hierarchical_id_under_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_004_001",
        title="Existing",
        tier="feature",
        parent="epic_004",
    )
    feature_id = mint_feature("Child", epic_id="epic_004", root=root)
    assert feature_id == "feat_004_002"
    doc = read_doc(feature_id, root=root)
    assert doc.meta.parent == "epic_004"
    assert doc.meta.id == feature_id


def test_mint_task_emits_hierarchical_id_under_feature(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_004_002",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_004",
    )
    add_doc(
        root,
        id="task_004_002_001",
        title="First",
        tier="task",
        parent="feat_004_002",
    )
    task_id = mint_task("Second", feature_id="feat_004_002", root=root)
    assert task_id == "task_004_002_002"
    assert read_doc(task_id, root=root).meta.parent == "feat_004_002"


def test_sibling_namespaces_allocate_independently(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_003", title="A", tier="epic", status="active")
    add_doc(root, id="epic_004", title="B", tier="epic", status="active")
    assert mint_feature("F3", epic_id="epic_003", root=root) == "feat_003_001"
    assert mint_feature("F4", epic_id="epic_004", root=root) == "feat_004_001"


def test_write_doc_rejects_id_collision_for_new_docs(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Epic", tier="epic")
    existing = add_doc(
        root,
        id="feat_004_001",
        title="Taken",
        tier="feature",
        parent="epic_004",
    )
    path = root / "docs/features/1_backlog/feat_004_001_duplicate.md"
    duplicate = WorkDoc(
        meta=existing.meta,
        body=existing.body,
        sha=None,
    )
    duplicate.meta.title = "Duplicate"
    duplicate.meta.path = path
    with pytest.raises(SchemaError, match="id collision"):
        write_doc(duplicate, root=root)


def test_legacy_ids_remain_readable_after_hierarchical_mint(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_009",
        title="Legacy",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    legacy = read_doc("feat_009", root=root)
    mint_task("New", feature_id="feat_009", root=root)
    assert read_doc("feat_009", root=root).meta.title == legacy.meta.title
    assert "feat_009" in list_board(root).by_id
