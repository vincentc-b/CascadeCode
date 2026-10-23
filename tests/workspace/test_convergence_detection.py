"""Bounded convergence-state detection (feat_012_002 / task_012_002_001)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.task.execution import heartbeat, mark_queued, mark_running
from cascade.watchdog import append_event
from cascade.watchdog.types import Event
from cascade.workspace.convergence import (
    observe_convergence_states,
    reset_convergence_detection_for_tests,
    set_convergence_clock_for_tests,
)
from tests.support import add_doc, approve_board_feature, make_repo


@pytest.fixture(autouse=True)
def _reset_convergence_memory() -> None:
    reset_convergence_detection_for_tests()
    yield
    reset_convergence_detection_for_tests()


def _obs(root: Path, work_id: str):
    rows = {row.work_id: row for row in observe_convergence_states(root=root)}
    return rows.get(work_id)


def test_gated_unapproved_feature_is_not_stalled(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    now = {"t": 0.0}

    def clock() -> float:
        return now["t"]

    set_convergence_clock_for_tests(clock)
    row = _obs(root, "feat_001")
    assert row is not None
    assert row.state == "gated"
    assert row.blocker == "not_approved"
    now["t"] = 10_000.0
    again = _obs(root, "feat_001")
    assert again is not None
    assert again.state == "gated"


def test_dispatchable_feature_becomes_stalled_after_threshold(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 60\n",
        encoding="utf-8",
    )
    now = {"t": 100.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    first = _obs(root, "feat_001")
    assert first is not None
    assert first.state == "progressing"
    assert first.dispatchable is True

    now["t"] = 161.0
    stalled = _obs(root, "feat_001")
    assert stalled is not None
    assert stalled.state == "stalled"
    assert stalled.stalled_for_seconds == pytest.approx(61.0)
    assert stalled.blocker == "no_durable_progress"


def test_durable_lifecycle_progress_resets_stall(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 10\n",
        encoding="utf-8",
    )
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    observe_convergence_states(root=root)
    now["t"] = 100.0
    stalled = _obs(root, "feat_001")
    assert stalled is not None
    assert stalled.state == "stalled"

    append_event(
        "feat_001",
        Event(
            type="FeatureReadyToPlan",
            ts=datetime.now(timezone.utc),
            payload={"id": "feat_001"},
            dest="feat_001",
        ),
        root=root,
    )
    recovered = _obs(root, "feat_001")
    assert recovered is not None
    assert recovered.state == "recovered"

    again = _obs(root, "feat_001")
    assert again is not None
    assert again.state == "progressing"


def test_execution_lease_heartbeat_does_not_count_as_progress(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 5\n",
        encoding="utf-8",
    )
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mark_queued("task_001", root=root, now=started)
    mark_running("task_001", root=root, now=started)
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    observe_convergence_states(root=root)
    heartbeat("task_001", root=root, now=started + timedelta(minutes=5))
    now["t"] = 100.0
    row = _obs(root, "task_001")
    assert row is not None
    assert row.state == "stalled"


def test_at_cap_task_is_gated_not_stalled(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Cap task", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Wait task", tier="task", parent="feat_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "task_parallelism = 1\n[convergence]\nstall_threshold_seconds = 1\n",
        encoding="utf-8",
    )
    from cascade.board import move_doc

    move_doc("task_001", "active", root=root)
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    observe_convergence_states(root=root)
    now["t"] = 100.0
    row = _obs(root, "task_002")
    assert row is not None
    assert row.state == "gated"
    assert row.blocker == "at_cap"
