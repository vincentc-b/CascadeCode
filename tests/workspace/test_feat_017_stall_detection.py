"""Stall and duplicate-kickoff observability (task_017_002_002)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import clear_feature_graph_sessions, ensure_feature_graph
from cascade.war_room.chat_store import read_messages
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory, watchdog_tick
from cascade.workspace.kickoff import (
    deliver_queue_kickoffs,
    wait_for_background_kickoffs,
)
from tests.harness.queue_delivery import (
    append_lifecycle_event,
    boot_feature_graph,
    feature_graph_values,
    install_queue_delivery_test_isolation,
    queue_eof,
    seed_active_feature_board,
)
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _isolate_graphs(monkeypatch: pytest.MonkeyPatch) -> None:
    install_queue_delivery_test_isolation(monkeypatch)
    yield
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def test_forced_stall_emits_one_warning_and_war_room_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)

    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_stall_pending",
    )
    values = feature_graph_values(feature_id, root=root)
    cursor = int(values.get("last_queue_offset") or 0)
    assert queue_eof(feature_id, root=root) > cursor

    monkeypatch.setattr(
        "cascade.workspace.kickoff.deliver_queue_kickoffs",
        lambda _root: None,
    )

    caplog.set_level(logging.WARNING, logger="cascade.workspace.queue_observability")
    for _ in range(3):
        watchdog_tick(root)

    stall_logs = [
        record
        for record in caplog.records
        if record.name == "cascade.workspace.queue_observability"
        and getattr(record, "kind", None) == "stall"
        and record.getMessage().startswith("graph queue stall")
    ]
    assert len(stall_logs) == 1
    assert stall_logs[0].work_id == feature_id
    assert stall_logs[0].offset == cursor

    system_notes = [
        message
        for message in read_messages(feature_id, root=root)
        if message.get("author") == "system" and "Queue stall" in message.get("body", "")
    ]
    assert len(system_notes) == 1


def test_duplicate_kickoff_emits_one_warning_and_war_room_note(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)

    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_dup_kickoff",
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)

    eof = queue_eof(feature_id, root=root)
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    rolled = dict(snapshot.values or {})
    rolled["last_queue_offset"] = 0
    graph.update_state(config, rolled)

    caplog.set_level(logging.WARNING, logger="cascade.workspace.queue_observability")
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)

    dup_logs = [
        record
        for record in caplog.records
        if record.name == "cascade.workspace.queue_observability"
        and getattr(record, "kind", None) == "duplicate_kickoff"
    ]
    assert len(dup_logs) == 1
    assert dup_logs[0].work_id == feature_id
    assert dup_logs[0].offset == eof

    system_notes = [
        message
        for message in read_messages(feature_id, root=root)
        if message.get("author") == "system"
        and "Queue duplicate kickoff" in message.get("body", "")
    ]
    assert len(system_notes) == 1
