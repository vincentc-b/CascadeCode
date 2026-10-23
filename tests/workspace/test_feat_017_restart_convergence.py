"""Restart convergence via serialized delivery (task_017_002_001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import clear_feature_graph_sessions, ensure_feature_graph
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import _event_tick, clear_watchdog_memory
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


def test_failed_background_turn_retries_staged_input_without_new_queue_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cascade.workspace.kickoff as kickoff

    runner = CountingBlockedTurnRunner()
    runner.install(monkeypatch)
    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)
    turns_before = runner.turn_count
    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_retry_staged",
    )

    invoke = kickoff._invoke_role_turn
    failures = 0

    def fail_once(*args, **kwargs) -> None:
        nonlocal failures
        failures += 1
        if failures == 1:
            raise RuntimeError("turn failed after queue cursor advanced")
        invoke(*args, **kwargs)

    monkeypatch.setattr(kickoff, "_invoke_role_turn", fail_once)
    _event_tick(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert failures == 1
    assert int(feature_graph_values(feature_id, root=root)["last_queue_offset"]) == queue_eof(
        feature_id, root=root
    )

    key = (root.resolve(), feature_id)
    with kickoff._registry_lock:
        tier, parent, attempts, _retry_at = kickoff._failed_queue_delivery[key]
        kickoff._failed_queue_delivery[key] = (tier, parent, attempts, 0)

    # The queue file is unchanged and its cursor is already at EOF.
    _event_tick(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert failures == 2
    assert runner.turn_count - turns_before == 2
    assert key not in kickoff._failed_queue_delivery

    _event_tick(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert failures == 2


def test_restart_recovers_unanswered_staged_input_at_queue_eof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import cascade.workspace.kickoff as kickoff

    runner = CountingBlockedTurnRunner()
    runner.install(monkeypatch)
    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)
    turns_before = runner.turn_count
    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_restart_staged",
    )

    def fail_before_turn(*_args, **_kwargs) -> None:
        raise RuntimeError("staged but unprocessed")

    with monkeypatch.context() as patcher:
        patcher.setattr(kickoff, "_invoke_role_turn", fail_before_turn)
        _event_tick(root)
        assert wait_for_background_kickoffs(timeout=15)

    assert int(feature_graph_values(feature_id, root=root)["last_queue_offset"]) == queue_eof(
        feature_id, root=root
    )
    kickoff.clear_kickoff_delivery_state()
    resume_inflight_graphs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert runner.turn_count - turns_before == 2
