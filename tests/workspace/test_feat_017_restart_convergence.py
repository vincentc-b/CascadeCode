"""Restart convergence via serialized delivery (task_017_002_001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import clear_feature_graph_sessions, ensure_feature_graph
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory
from cascade.workspace.kickoff import (
    deliver_queue_kickoffs,
    resume_inflight_graphs,
    wait_for_background_kickoffs,
)
from tests.harness.queue_delivery import (
    CountingBlockedTurnRunner,
    append_lifecycle_event,
    boot_feature_graph,
    feature_graph_values,
    install_queue_delivery_test_isolation,
    queue_eof,
    seed_active_feature_board,
)
from tests.support import make_repo

_FEATURE_PLANNING_ROLES_PER_INVOKE = 2
# Synthetic interrupt replays lead+architect, then one queue-event turn for pending lines.
_ROLES_AFTER_SIMULATED_RESTART = 2 * _FEATURE_PLANNING_ROLES_PER_INVOKE


@pytest.fixture(autouse=True)
def _isolate_graphs(monkeypatch: pytest.MonkeyPatch) -> None:
    install_queue_delivery_test_isolation(monkeypatch)
    yield
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def _simulate_interrupted_checkpoint(feature_id: str, *, root: Path) -> None:
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    assert not snapshot.next
    graph.update_state(config, dict(snapshot.values or {}), as_node="feature_lead")
    interrupted = graph.get_state(config)
    assert interrupted.next


def test_restart_convergence_resumes_once_catches_up_queue_and_settles_idle(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = CountingBlockedTurnRunner()
    runner.install(monkeypatch)

    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)

    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_restart_seed",
    )
    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_restart_pending",
    )
    _simulate_interrupted_checkpoint(feature_id, root=root)
    turns_before_restart = runner.turn_count
    assert queue_eof(feature_id, root=root) > int(
        feature_graph_values(feature_id, root=root).get("last_queue_offset") or 0
    )

    resume_inflight_graphs(root)
    assert wait_for_background_kickoffs(timeout=15)

    assert runner.turn_count - turns_before_restart == _ROLES_AFTER_SIMULATED_RESTART

    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    assert not snapshot.next
    values = dict(snapshot.values or {})
    assert int(values.get("last_queue_offset") or 0) == queue_eof(feature_id, root=root)
    events = [m for m in values.get("messages") or [] if m.get("role") == "event"]
    assert len([m for m in events if "dec_restart_seed" in m.get("content", "")]) == 1
    assert len([m for m in events if "dec_restart_pending" in m.get("content", "")]) == 1

    turns_before_repeat = runner.turn_count
    resume_inflight_graphs(root)
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert runner.turn_count == turns_before_repeat
