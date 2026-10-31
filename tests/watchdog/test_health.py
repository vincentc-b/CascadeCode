"""Supervisor health observation and bounded remediation."""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock
from types import SimpleNamespace

from cascade.board.store import read_doc, write_doc
from cascade.task.execution import execution_view, mark_terminal
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    supervisor_health_sweep_seconds,
)
from cascade.watchdog import health as health_module
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
    tmp_path: Path, monkeypatch,
) -> None:
    root = _active_feature_with_blocked_task(tmp_path)
    calls = 0
    calls_lock = Lock()
    real_retry = health_module.retry_task

    def counted_retry(*args, **kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        return real_retry(*args, **kwargs)

    monkeypatch.setattr(health_module, "retry_task", counted_retry)

    with ThreadPoolExecutor(max_workers=4) as pool:
        sweeps = list(pool.map(lambda _: sweep_supervisor_health(root), range(4)))
    repeated = sweep_supervisor_health(root)

    assert [
        (item.child_id, item.classification)
        for observations in sweeps
        for item in observations
        if item.child_id == "task_001"
        and item.classification == "remediation_eligible"
    ] == [("task_001", "remediation_eligible")]
    assert calls == 1
    assert read_doc("task_001", root=root).meta.status == "active"
    assert execution_view("task_001", root=root)["health"] == "queued"
    repeated_task = next(item for item in repeated if item.child_id == "task_001")
    assert repeated_task.classification == "no_action"
    ledger = (root / ".cascade" / "remediation_dispositions.json").read_text(
        encoding="utf-8"
    )
    assert '"result": "accepted"' in ledger


def test_health_sweep_is_noop_for_healthy_and_terminal_work(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Active epic",
        tier="epic",
        status="active",
        children=["feat_010", "feat_011"],
    )
    add_doc(
        root,
        id="feat_010",
        title="Active feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_010", "task_011"],
    )
    add_doc(
        root,
        id="feat_011",
        title="Terminal supervisor",
        tier="feature",
        status="completed",
        parent="epic_001",
        children=["task_012"],
    )
    add_doc(
        root,
        id="task_010",
        title="Healthy task",
        tier="task",
        status="active",
        parent="feat_010",
    )
    add_doc(
        root,
        id="task_011",
        title="Terminal task",
        tier="task",
        status="completed",
        parent="feat_010",
    )
    add_doc(
        root,
        id="task_012",
        title="Blocked child of terminal supervisor",
        tier="task",
        status="blocked",
        parent="feat_011",
    )

    observations = sweep_supervisor_health(root)

    by_child = {item.child_id: item for item in observations}
    assert by_child["task_010"].classification == "no_action"
    assert by_child["task_011"].reason == "terminal_child"
    assert by_child["feat_011"].reason == "terminal_child"
    assert "task_012" not in by_child
    assert not (root / ".cascade" / "remediation_dispositions.json").exists()


def test_health_sweep_recovers_abandoned_awaiting_merge_delivery(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    monkeypatch.setattr(
        health_module,
        "execution_views",
        lambda *_args, **_kwargs: {
            "task_001": {
                "attempt": 7,
                "phase": "awaiting_merge",
                "outcome": None,
                "health": "awaiting_merge",
            }
        },
    )
    calls: list[tuple[str, Path, str]] = []
    monkeypatch.setattr(
        health_module,
        "supervisor_recover_task_delivery",
        lambda task_id, *, root, observed_incident: (
            calls.append((task_id, root, observed_incident))
            or SimpleNamespace(decision="requeue_commit", reason="validated")
        ),
    )

    sweep_supervisor_health(root)

    assert calls == [("task_001", root, "task_001:delivery:7")]


def test_health_sweep_does_not_nominate_live_task_owner(
    tmp_path: Path, monkeypatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    monkeypatch.setattr(
        health_module,
        "execution_views",
        lambda *_args, **_kwargs: {
            "task_001": {
                "attempt": 7,
                "phase": "running",
                "outcome": None,
                "health": "healthy",
            }
        },
    )
    calls: list[object] = []
    monkeypatch.setattr(
        health_module,
        "supervisor_recover_task_delivery",
        lambda *_args, **_kwargs: calls.append("unexpected recovery"),
    )

    sweep_supervisor_health(root)

    assert calls == []


def test_recovery_failure_is_recorded_once_for_concurrent_and_repeated_sweeps(
    tmp_path: Path, monkeypatch,
) -> None:
    root = _active_feature_with_blocked_task(tmp_path)
    calls = 0
    calls_lock = Lock()

    def fail_retry(*_args, **_kwargs):
        nonlocal calls
        with calls_lock:
            calls += 1
        raise RuntimeError("transient dispatch failure")

    monkeypatch.setattr(health_module, "retry_task", fail_retry)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: sweep_supervisor_health(root), range(4)))
    sweep_supervisor_health(root)

    assert calls == 1
    assert read_doc("task_001", root=root).meta.status == "blocked"
    ledger = json.loads(
        (root / ".cascade" / "remediation_dispositions.json").read_text(
            encoding="utf-8"
        )
    )
    dispositions = list(ledger["dispositions"].values())
    assert len(dispositions) == 1
    assert dispositions[0]["result"] == "error"
    assert dispositions[0]["reason"] == "RuntimeError: transient dispatch failure"


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


def test_health_sweeps_propagate_and_reconcile_task_to_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001", "task_002"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Sibling task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: sweep_supervisor_health(root), range(2)))
    sweep_supervisor_health(root)

    feature = read_doc("feat_001", root=root)
    epic = read_doc("epic_001", root=root)
    assert feature.meta.status == "blocked"
    assert [
        (item.child_id, item.reason, item.blocked_supervisor)
        for item in feature.meta.monitoring_blockers
    ] == [
        ("task_001", "blocked_task_without_terminal_failure", True),
        ("task_002", "blocked_task_without_terminal_failure", False),
    ]
    assert epic.meta.status == "blocked"
    assert [
        (item.child_id, item.reason, item.blocked_supervisor)
        for item in epic.meta.monitoring_blockers
    ] == [("feat_001", "blocked_feature_has_no_safe_retry", True)]

    task = read_doc("task_001", root=root)
    task.meta.status = "active"
    write_doc(task, root=root)
    sweep_supervisor_health(root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "blocked"
    assert [
        (item.child_id, item.blocked_supervisor)
        for item in feature.meta.monitoring_blockers
    ] == [("task_002", True)]
    assert read_doc("epic_001", root=root).meta.status == "blocked"

    sibling = read_doc("task_002", root=root)
    sibling.meta.status = "active"
    write_doc(sibling, root=root)
    sweep_supervisor_health(root)
    assert read_doc("feat_001", root=root).meta.status == "active"
    assert read_doc("epic_001", root=root).meta.status == "blocked"

    sweep_supervisor_health(root)

    assert read_doc("feat_001", root=root).meta.status == "active"
    assert read_doc("epic_001", root=root).meta.status == "active"


def test_health_sweep_preserves_manual_blockage_and_terminal_work(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Manually blocked epic",
        tier="epic",
        status="blocked",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Manually blocked feature",
        tier="feature",
        status="blocked",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Recovered task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="epic_002",
        title="Completed epic",
        tier="epic",
        status="completed",
        children=["feat_002"],
    )
    add_doc(
        root,
        id="feat_002",
        title="Blocked child of terminal epic",
        tier="feature",
        status="blocked",
        parent="epic_002",
    )

    observations = sweep_supervisor_health(root)

    assert observations == []
    assert read_doc("feat_001", root=root).meta.status == "blocked"
    assert read_doc("epic_001", root=root).meta.status == "blocked"
    assert read_doc("epic_002", root=root).meta.status == "completed"
    assert read_doc("feat_002", root=root).meta.status == "blocked"
