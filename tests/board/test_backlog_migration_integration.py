"""End-to-end backlog migration integrity and failure safety (task_023)."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import cascade.board.backlog_migration as backlog_migration
from cascade.board.backlog_migration import (
    BacklogMigrationApplyError,
    BacklogMigrationPlan,
    BacklogMigrationValidationError,
    ReferenceUpdate,
    apply_backlog_migration,
    build_backlog_migration_plan,
)
from cascade.board.errors import GitError
from cascade.board.store import list_board, pin_parent, read_doc, write_doc
from tests.support import TASK_BODY, add_doc, make_repo


def _body_with_parent_link(feature_id: str) -> str:
    return TASK_BODY.replace(
        "Parent feature and parent_rev.",
        f"[{feature_id}](../../features/1_backlog/{feature_id}.md)",
    )


def _docs_tree_bytes(root: Path) -> dict[Path, bytes]:
    docs = root / "docs"
    return {
        path: path.read_bytes()
        for path in sorted(docs.rglob("*"))
        if path.is_file()
    }


def _non_backlog_bytes(root: Path) -> dict[Path, bytes]:
    docs = root / "docs"
    kept: dict[Path, bytes] = {}
    for column in ("2_active", "3_completed"):
        column_root = docs
        for tier in ("epics", "features", "tasks"):
            folder = column_root / tier / column
            if not folder.is_dir():
                continue
            for path in sorted(folder.rglob("*.md")):
                if path.is_file():
                    kept[path] = path.read_bytes()
    return kept


def _write_comment_sidecar(root: Path, work_id: str, *, doc_id: str, blocks: list[str]) -> None:
    path = root / "docs" / "_comments" / f"{work_id}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"doc_id": doc_id, "blocks": blocks}
    path.write_text(json.dumps(payload, separators=(",", ":")) + "\n", encoding="utf-8")


def _seed_multi_epic_board(root: Path) -> None:
    add_doc(root, id="epic_004", title="Active epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_004",
        title="Active feature",
        tier="feature",
        status="active",
        parent="epic_004",
    )
    add_doc(
        root,
        id="task_004",
        title="Completed task",
        tier="task",
        status="completed",
        parent="feat_004",
    )
    pin_parent("feat_004", "epic_004", root=root)
    pin_parent("task_004", "feat_004", root=root)

    add_doc(root, id="epic_001", title="North backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_005",
        title="North legacy feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    pin_parent("feat_005", "epic_001", root=root)

    add_doc(root, id="epic_002", title="South backlog epic", tier="epic", status="backlog")
    add_doc(
        root,
        id="feat_001",
        title="South legacy feature",
        tier="feature",
        status="backlog",
        parent="epic_002",
        depends_on=["feat_005"],
    )
    pin_parent("feat_001", "epic_002", root=root)

    add_doc(
        root,
        id="task_006",
        title="North legacy task",
        tier="task",
        status="backlog",
        parent="feat_005",
        depends_on=["feat_001"],
    )
    pin_parent("task_006", "feat_005", root=root)

    add_doc(
        root,
        id="task_001",
        title="South legacy task",
        tier="task",
        status="backlog",
        parent="feat_001",
        depends_on=["task_006", "feat_005"],
    )
    pin_parent("task_001", "feat_001", root=root)

    south_task = read_doc("task_001", root=root)
    south_task.body = _body_with_parent_link("feat_001") + "\nCross-ref feat_005 in prose.\n"
    write_doc(south_task, root=root)

    _write_comment_sidecar(
        root,
        "feat_001",
        doc_id="feat_001",
        blocks=["task_001", "feat_005"],
    )


def test_integration_migrates_multiple_backlog_epics_with_cross_references(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)

    plan = build_backlog_migration_plan(root=root)
    assert dict(plan.renames) == {
        "feat_001": "feat_002_001",
        "feat_005": "feat_001_001",
        "task_001": "task_002_001_001",
        "task_006": "task_001_001_001",
    }

    sha = apply_backlog_migration(root=root)
    assert sha is not None

    board = list_board(root)
    assert board.by_id["feat_002_001"].parent == "epic_002"
    assert board.by_id["feat_001_001"].parent == "epic_001"
    assert board.by_id["task_002_001_001"].parent == "feat_002_001"
    assert board.by_id["task_001_001_001"].parent == "feat_001_001"

    south_task = read_doc("task_002_001_001", root=root)
    assert south_task.meta.depends_on == ["task_001_001_001", "feat_001_001"]
    assert "feat_001_001" in south_task.body
    assert "feat_005" not in south_task.body

    north_task = read_doc("task_001_001_001", root=root)
    assert north_task.meta.depends_on == ["feat_002_001"]

    sidecar = (root / "docs" / "_comments" / "feat_002_001.jsonl").read_text(encoding="utf-8")
    assert "feat_002_001" in sidecar
    assert "task_002_001_001" in sidecar
    assert "feat_001_001" in sidecar
    assert not (root / "docs" / "_comments" / "feat_001.jsonl").exists()

    assert "epic_004" in board.by_id
    assert "task_004" in board.by_id
    assert "feat_001" not in board.by_id


def test_integration_leaves_active_and_completed_bytes_unchanged(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)
    before = _non_backlog_bytes(root)

    apply_backlog_migration(root=root)

    assert _non_backlog_bytes(root) == before


def test_integration_second_apply_is_noop(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)

    first_sha = apply_backlog_migration(root=root)
    assert first_sha is not None
    after_first = _docs_tree_bytes(root)

    assert apply_backlog_migration(root=root) is None
    assert _docs_tree_bytes(root) == after_first


def test_integration_rejects_forced_id_collision_without_board_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)
    before = _docs_tree_bytes(root)
    real_assign = backlog_migration._assign_target_ids

    def duplicate_targets(board, scoped, errors):
        mapping = real_assign(board, scoped, errors)
        if "feat_001" in mapping and "feat_005" in mapping:
            mapping["feat_005"] = mapping["feat_001"]
        return mapping

    monkeypatch.setattr(backlog_migration, "_assign_target_ids", duplicate_targets)

    with pytest.raises(BacklogMigrationValidationError) as exc:
        build_backlog_migration_plan(root=root)
    assert any("collision" in err for err in exc.value.errors)
    assert _docs_tree_bytes(root) == before


def test_integration_apply_rolls_back_on_malformed_body_reference(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)
    before = _docs_tree_bytes(root)
    real_build = build_backlog_migration_plan

    def plan_with_bad_body_reference(*, root: Path) -> BacklogMigrationPlan:
        plan = real_build(root=root)
        task_path = read_doc("task_001", root=root).meta.path
        bogus = ReferenceUpdate(
            path=task_path,
            owner_id="task_001",
            location="body:1",
            old_value="feat_005",
            new_value="feat_001_001",
        )
        return replace(plan, reference_updates=plan.reference_updates + (bogus,))

    monkeypatch.setattr(
        backlog_migration,
        "build_backlog_migration_plan",
        plan_with_bad_body_reference,
    )

    with pytest.raises(BacklogMigrationApplyError, match="missing expected token"):
        apply_backlog_migration(root=root)

    assert _docs_tree_bytes(root) == before


def test_integration_apply_rolls_back_when_commit_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _seed_multi_epic_board(root)
    before = _docs_tree_bytes(root)

    def fail_commit(*_args, **_kwargs):
        raise GitError("commit rejected")

    monkeypatch.setattr(backlog_migration, "commit_paths", fail_commit)

    with pytest.raises(GitError, match="commit rejected"):
        apply_backlog_migration(root=root)

    assert _docs_tree_bytes(root) == before
    assert "feat_001" in list_board(root).by_id
