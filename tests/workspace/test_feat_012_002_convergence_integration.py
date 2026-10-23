"""Convergence detection integration via watchdog maintenance (feat_012_002 / task_012_002_003)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.boss.view import compute_boss_view
from cascade.watchdog import activate_epic, append_event, dispatch_feature, dispatch_task, read_events
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory, watchdog_tick
from cascade.watchdog.types import Event
from cascade.workspace.convergence import (
    reset_convergence_detection_for_tests,
    set_convergence_clock_for_tests,
)
from tests.support import add_doc, approve_board_feature, make_repo


@pytest.fixture(autouse=True)
def _isolate_watchdog(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_hooks()
    clear_watchdog_memory()
    reset_convergence_detection_for_tests()
    monkeypatch.setattr(
        "cascade.workspace.kickoff.deliver_queue_kickoffs",
        lambda _root: None,
    )
    monkeypatch.setattr(
        "cascade.automation.advance_work",
        lambda _root: {"features": [], "tasks": []},
    )
    yield
    clear_hooks()
    clear_watchdog_memory()
    reset_convergence_detection_for_tests()


def _stall_toasts(root: Path) -> list[Event]:
    events, _ = read_events("war_room", 0, root=root)
    return [
        event
        for event in events
        if event.type == "Toast" and event.payload.get("kind") == "convergence_stall"
    ]


def _lifecycle_events(root: Path, work_id: str, event_type: str) -> list[Event]:
    events, _ = read_events(work_id, 0, root=root)
    return [event for event in events if event.type == event_type]


def _seed_dispatchable_feature(root: Path, *, threshold_seconds: float) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        f"[convergence]\nstall_threshold_seconds = {int(threshold_seconds)}\n",
        encoding="utf-8",
    )
    view = compute_boss_view(root=root)
    assert "feat_001" in view.dispatchable_features


def test_watchdog_tick_emits_one_convergence_diagnostic_after_threshold(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _seed_dispatchable_feature(root, threshold_seconds=60)
    now = {"t": 100.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    watchdog_tick(root)
    assert _stall_toasts(root) == []

    now["t"] = 161.0
    watchdog_tick(root)
    toasts = _stall_toasts(root)
    assert len(toasts) == 1
    assert toasts[0].payload["id"] == "feat_001"
    assert toasts[0].payload["blocker"] == "no_durable_progress"

    now["t"] = 500.0
    for _ in range(3):
        watchdog_tick(root)
    assert len(_stall_toasts(root)) == 1


def test_watchdog_tick_convergence_respects_gates_and_readiness_predicate(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Unapproved feature", tier="feature", parent="epic_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 1\n",
        encoding="utf-8",
    )
    view = compute_boss_view(root=root)
    assert view.dispatchable_features == []

    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    watchdog_tick(root)
    now["t"] = 100.0
    watchdog_tick(root)
    assert _stall_toasts(root) == []

    add_doc(root, id="feat_002", title="Approved feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Cap task", tier="task", parent="feat_002")
    add_doc(root, id="task_002", title="Wait task", tier="task", parent="feat_002")
    approve_board_feature(root, "feat_002")
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_002", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    (root / "cascade.toml").write_text(
        "task_parallelism = 1\n[convergence]\nstall_threshold_seconds = 1\n",
        encoding="utf-8",
    )
    capped = compute_boss_view(root=root)
    assert "task_002" not in capped.dispatchable_tasks

    now["t"] = 200.0
    watchdog_tick(root)
    now["t"] = 400.0
    watchdog_tick(root)
    stall_ids = {toast.payload["id"] for toast in _stall_toasts(root)}
    assert "task_002" not in stall_ids


def test_watchdog_tick_convergence_recovery_then_later_stall_re_emits(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _seed_dispatchable_feature(root, threshold_seconds=10)
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    watchdog_tick(root)
    now["t"] = 100.0
    watchdog_tick(root)
    assert len(_stall_toasts(root)) == 1

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
    watchdog_tick(root)
    assert len(_stall_toasts(root)) == 1

    now["t"] = 200.0
    watchdog_tick(root)
    assert len(_stall_toasts(root)) == 2


def test_watchdog_tick_convergence_is_read_only_against_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    _seed_dispatchable_feature(root, threshold_seconds=5)
    dispatch_calls: list[tuple[str, str]] = []

    def _record_dispatch(work_id: str, by: str, *, root: Path, **_kwargs: object) -> object:
        dispatch_calls.append((work_id, by))
        from cascade.watchdog.types import DispatchResult

        return DispatchResult(ok=False, reason="blocked_in_test", event=None)

    monkeypatch.setattr("cascade.watchdog.dispatch_feature", _record_dispatch)
    monkeypatch.setattr("cascade.watchdog.dispatch_task", _record_dispatch)

    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    watchdog_tick(root)
    now["t"] = 100.0
    watchdog_tick(root)

    assert len(_stall_toasts(root)) == 1
    assert dispatch_calls == []
    assert _lifecycle_events(root, "feat_001", "TaskDispatched") == []
    assert _lifecycle_events(root, "feat_001", "FeatureReadyToPlan") == []

    doc_path = next(
        (path for path in (root / "docs" / "features" / "1_backlog").glob("feat_001*.md")),
        None,
    )
    assert doc_path is not None
    assert doc_path.parent.name == "1_backlog"
