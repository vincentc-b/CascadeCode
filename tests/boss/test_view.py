"""BossView read model: deps, cap, and failed tasks."""

from pathlib import Path

from cascade.board import move_doc, read_doc, write_doc
from cascade.boss import BossView, compute_boss_view
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from tests.support import add_doc, commit_board, make_repo


def test_empty_board(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    view = compute_boss_view(root=root)
    assert view == BossView(
        dispatchable_features=[],
        dispatchable_tasks=[],
        slots_free=4,
        failed_tasks=[],
    )


def test_backlog_feature_and_task_with_met_and_unmet_deps(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Ready feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_003", title="Dep feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Waiting feature", tier="feature", parent="epic_001", depends_on=["feat_003"])
    add_doc(root, id="task_001", title="Ready task", tier="task", parent="feat_001")
    add_doc(root, id="task_003", title="Dep task", tier="task", parent="feat_001")
    add_doc(
        root,
        id="task_002",
        title="Waiting task",
        tier="task",
        parent="feat_001",
        depends_on=["task_003"],
    )

    view = compute_boss_view(root=root)
    assert view.dispatchable_features == ["feat_001", "feat_003"]
    assert view.dispatchable_tasks == ["task_001", "task_003"]
    assert view.slots_free == 4
    assert view.failed_tasks == []

    move_doc("feat_003", "completed", root=root)
    move_doc("task_003", "completed", root=root)
    after = compute_boss_view(root=root)
    assert after.dispatchable_features == ["feat_001", "feat_002"]
    assert after.dispatchable_tasks == ["task_001", "task_002"]


def test_ready_to_plan_feature_in_backlog_is_dispatchable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(
        root,
        id="feat_001",
        title="Plan me",
        tier="feature",
        parent="epic_001",
        status="ready_to_plan",
    )
    view = compute_boss_view(root=root)
    assert view.dispatchable_features == ["feat_001"]
    assert view.dispatchable_tasks == []
    assert view.slots_free == 4


def test_cap_full_excludes_dispatchable_tasks_and_reports_slots_free(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parallelism=2)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task A", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Task B", tier="task", parent="feat_001")
    add_doc(root, id="task_003", title="Task C", tier="task", parent="feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok

    assert dispatch_task("task_001", "human", root=root).ok
    assert dispatch_task("task_002", "human", root=root).ok
    assert dispatch_task("task_003", "human", root=root).ok is False

    view = compute_boss_view(root=root)
    assert view.dispatchable_tasks == []
    assert view.slots_free == 0
    assert view.dispatchable_features == []

    blocked = read_doc("task_001", root=root)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=root)
    freed = compute_boss_view(root=root)
    assert freed.slots_free == 1
    assert freed.dispatchable_tasks == ["task_003"]
    assert freed.failed_tasks == ["task_001"]


def test_blocked_task_in_active_is_failed_not_dispatchable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Failed task", tier="task", parent="feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    doc = read_doc("task_001", root=root)
    doc.meta.status = "blocked"
    write_doc(doc, root=root)

    view = compute_boss_view(root=root)
    assert view.failed_tasks == ["task_001"]
    assert view.dispatchable_tasks == []
    assert "task_001" not in view.dispatchable_tasks
