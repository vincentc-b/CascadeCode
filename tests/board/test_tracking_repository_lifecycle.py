"""Planning artifacts persist through the resolved tracking repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.board import list_board, move_doc, pin_parent, read_doc, write_doc
from cascade.epic.decisions import record_decision
from cascade.workspace import prepare_up
from tests.support import add_doc, make_repo


def _commit_initial(root: Path) -> None:
    (root / "README.md").write_text("repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initialize"], cwd=root, check=True)


def test_split_repository_routes_complete_artifact_lifecycle(tmp_path: Path) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    (target / "cascade.toml").write_text(
        f'tracking_repository = "{tracking}"\n', encoding="utf-8"
    )
    _commit_initial(target)
    _commit_initial(tracking)

    workspace = prepare_up(target)
    assert workspace.board == tracking / "docs"

    epic = add_doc(
        target,
        id="epic_001",
        title="Split epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    feature = add_doc(
        target,
        id="feat_001",
        title="Split feature",
        tier="feature",
        status="active",
        parent=epic.meta.id,
        children=["task_001"],
    )
    add_doc(
        target,
        id="task_001",
        title="Split task",
        tier="task",
        parent=feature.meta.id,
    )

    parent_revision = pin_parent("task_001", "feat_001", root=target)
    task = read_doc("task_001", root=target)
    assert task.meta.parent_rev == read_doc("feat_001", root=target).sha
    assert parent_revision == task.sha

    task.meta.title = "Updated split task"
    write_doc(task, root=target)
    move_doc("task_001", "completed", root=target)
    decision_id = record_decision(
        "Storage",
        "Use tracking",
        "Planning history belongs with planning artifacts.",
        "The configured repository roles.",
        epic_id="epic_001",
        root=target,
    )

    board = list_board(target)
    assert set(board.by_id) == {"epic_001", "feat_001", "task_001"}
    assert board.by_id["task_001"].status == "completed"
    assert read_doc("task_001", root=target).meta.title == "Updated split task"
    assert decision_id in read_doc("epic_001", root=target).body
    assert all(meta.path.is_relative_to(tracking) for meta in board.by_id.values())
    assert not list((target / "docs").rglob("*.md"))
    assert len(list((tracking / "docs").rglob("*.md"))) == 3


def test_colocated_repository_keeps_existing_storage_behavior(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _commit_initial(root)

    workspace = prepare_up(root)
    doc = add_doc(root, id="epic_001", title="Colocated", tier="epic")

    assert workspace.target_repository is workspace.tracking_repository
    assert workspace.board == root / "docs"
    assert read_doc(doc.meta.id, root=root).meta.path.is_relative_to(root)
    assert set(list_board(root).by_id) == {doc.meta.id}
