"""Supervisor health observation and bounded remediation."""

from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.task.execution import mark_terminal
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    supervisor_health_sweep_seconds,
)
from cascade.watchdog.health import classify_child, sweep_supervisor_health
from tests.support import add_doc, approve_board_feature, make_repo


def _active_feature_with_blocked_task(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="ready_to_plan",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        parent="feat_001",
    )
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=task.meta.path.parents[3])
    mark_terminal("task_001", "failed", root=root, error="worker failed")
    return root


def test_health_sweep_retries_failed_blocked_task_once_through_dispatch(
    tmp_path: Path,
) -> None:
    root = _active_feature_with_blocked_task(tmp_path)

    observations = sweep_supervisor_health(root)
    repeated = sweep_supervisor_health(root)

    assert [
        (item.child_id, item.classification)
        for item in observations
        if item.child_id == "task_001"
    ] == [("task_001", "remediation_eligible")]
    assert read_doc("task_001", root=root).meta.status == "active"
    repeated_task = next(item for item in repeated if item.child_id == "task_001")
    assert repeated_task.classification == "no_action"
    ledger = (root / ".cascade" / "remediation_dispositions.json").read_text(
        encoding="utf-8"
    )
    assert '"result": "accepted"' in ledger


def test_classifier_excludes_terminal_and_exposes_blocked_feature(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    supervisor = add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    blocked = add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="blocked",
        parent="epic_001",
    )
    assert classify_child(supervisor, blocked).classification == "unresolved"

    terminal = read_doc("feat_001", root=root)
    terminal.meta.status = "cancelled"
    terminal.meta.path = root / "docs" / "features" / "3_completed" / terminal.meta.path.name
    observation = classify_child(supervisor, terminal)
    assert observation.classification == "no_action"
    assert observation.reason == "terminal_child"


def test_supervisor_health_cadence_defaults_and_validates(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert supervisor_health_sweep_seconds(root) == 60.0

    (root / "cascade.toml").write_text(
        "[supervisor_health]\nsweep_seconds = 30\n",
        encoding="utf-8",
    )
    assert supervisor_health_sweep_seconds(root) == 30.0

    (root / "cascade.toml").write_text(
        "[supervisor_health]\nsweep_seconds = 0\n",
        encoding="utf-8",
    )
    assert supervisor_health_sweep_seconds(root) == 60.0
