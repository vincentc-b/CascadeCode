"""Hierarchical id allocation wired through mint and persistence."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

import cascade.epic.mint as epic_mint_mod
import cascade.feature.mint as feature_mint_mod
from cascade.board.errors import SchemaError
from cascade.board.paths import slugify
from cascade.board.store import allocate_id, list_board, read_doc, reset_id_reservations, write_doc
from cascade.board.types import WorkDoc, WorkMeta
from cascade.board.work_ids import validate_work_id_identity
from cascade.board import store as board_store
from cascade.epic import scoped_docs as epic_scoped_docs
from cascade.epic.mint import mint_feature
from cascade.feature.mint import mint_task
from tests.support import EPIC_BODY, add_doc, make_repo


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


def _persist_new_epic(root: Path, *, title: str) -> str:
    """Create an epic through the same allocate-then-write path briefs use."""

    epic_id = allocate_id("epic", list_board(root))
    path = root / "docs" / "epics" / "1_backlog" / f"{epic_id}_{slugify(title)}.md"
    today = date.today()
    write_doc(
        WorkDoc(
            meta=WorkMeta(
                id=epic_id,
                title=title,
                tier="epic",
                status="backlog",
                parent=None,
                children=[],
                depends_on=[],
                owners=["epic_manager", "epic_architect"],
                skills=[],
                parent_rev=None,
                created=today,
                updated=today,
                path=path,
            ),
            body=EPIC_BODY.replace("# Title", f"# {title}", 1),
            sha=None,
        ),
        root=root,
    )
    return epic_id


def test_hierarchical_work_creation_end_to_end(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Existing epic", tier="epic", status="active")

    epic_id = _persist_new_epic(root, title="Hierarchy E2E")
    assert epic_id == "epic_005"

    feature_id = mint_feature("Child feature", epic_id=epic_id, root=root)
    assert feature_id == "feat_005_001"

    first_task = mint_task("First task", feature_id=feature_id, root=root)
    second_task = mint_task(
        "Second task",
        depends_on=[first_task],
        feature_id=feature_id,
        root=root,
    )
    assert first_task == "task_005_001_001"
    assert second_task == "task_005_001_002"

    board = list_board(root)
    for work_id, tier, parent in (
        (epic_id, "epic", None),
        (feature_id, "feature", epic_id),
        (first_task, "task", feature_id),
        (second_task, "task", feature_id),
    ):
        meta = board.by_id[work_id]
        assert meta.tier == tier
        assert meta.parent == parent
        validate_work_id_identity(work_id, tier=tier, parent=parent)

    epic = read_doc(epic_id, root=root)
    feature = read_doc(feature_id, root=root)
    second = read_doc(second_task, root=root)
    assert feature_id in epic.meta.children
    assert feature.meta.children == [first_task, second_task]
    assert second.meta.depends_on == [first_task]
    assert epic.meta.path.is_file() and feature.meta.path.is_file()


def test_mint_feature_retries_after_persistence_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Epic", tier="epic", status="active")
    real_write = epic_scoped_docs.epic_write_doc
    attempts = {"count": 0}

    def flaky_write(doc: WorkDoc, **kwargs: object) -> str | None:
        if doc.meta.tier != "feature":
            return real_write(doc, **kwargs)  # type: ignore[arg-type]
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise SchemaError("id collision: feat_004_001")
        return real_write(doc, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(epic_scoped_docs, "epic_write_doc", flaky_write)
    monkeypatch.setattr(epic_mint_mod, "epic_write_doc", flaky_write)
    feature_id = mint_feature("Retried", epic_id="epic_004", root=root)
    assert feature_id == "feat_004_001"
    assert attempts["count"] == 2
    assert read_doc(feature_id, root=root).meta.parent == "epic_004"


def test_mint_task_retries_after_persistence_collision(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_004", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_004_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_004",
    )
    real_write = board_store.write_doc
    attempts = {"count": 0}

    def flaky_write(doc: WorkDoc, **kwargs: object) -> str | None:
        if doc.meta.tier != "task":
            return real_write(doc, **kwargs)  # type: ignore[arg-type]
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise SchemaError("id collision: task_004_001_001")
        return real_write(doc, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(board_store, "write_doc", flaky_write)
    monkeypatch.setattr(feature_mint_mod, "write_doc", flaky_write)
    task_id = mint_task("Retried task", feature_id="feat_004_001", root=root)
    assert task_id == "task_004_001_001"
    assert attempts["count"] == 2
