"""Regression harness for epic_017 queue cursor races (task_017_001_001)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions, ingest_queue
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory
from cascade.workspace.kickoff import deliver_queue_kickoffs, kickoff_turn, wait_for_background_kickoffs
from cascade.workspace.types import KickoffReason
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


@dataclass
class _RaceScenario:
    root: Path
    feature_id: str
    runner: CountingBlockedTurnRunner
    seed_offset: int
    turns_before_race: int = 0


@pytest.fixture(autouse=True)
def _isolate_graphs(monkeypatch: pytest.MonkeyPatch) -> None:
    install_queue_delivery_test_isolation(monkeypatch)
    yield
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def _wait_until(predicate, *, timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise TimeoutError("condition not met before timeout")


def _run_mid_turn_append_race(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _RaceScenario:
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
        entry="dec_race_seed",
    )
    seeded = ingest_queue(feature_id, root=root)
    seed_offset = int(seeded["last_queue_offset"])
    assert seed_offset > 0

    turns_before_race = runner.turn_count
    runner.arm_block_on_next_turn()

    turn_error: list[BaseException] = []

    def _run_queue_turn() -> None:
        try:
            kickoff_turn(
                KickoffReason(
                    kind="queue_event",
                    work_id=feature_id,
                    by="watchdog",
                    root=root,
                )
            )
        except BaseException as exc:  # pragma: no cover - surfaced below
            turn_error.append(exc)

    turn_thread = threading.Thread(target=_run_queue_turn, name="blocked-turn")
    turn_thread.start()
    runner.wait_blocked()

    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_race_append",
    )
    queue_size_after_append = queue_eof(feature_id, root=root)
    assert queue_size_after_append > seed_offset

    deliver_error: list[BaseException] = []

    def _deliver() -> None:
        try:
            deliver_queue_kickoffs(root)
        except BaseException as exc:  # pragma: no cover - surfaced below
            deliver_error.append(exc)

    deliver_thread = threading.Thread(target=_deliver, name="watchdog-deliver")
    deliver_thread.start()

    def _ingest_visible() -> bool:
        values = feature_graph_values(feature_id, root=root)
        return int(values.get("last_queue_offset") or 0) >= queue_size_after_append

    _wait_until(_ingest_visible)

    runner.release()
    turn_thread.join(timeout=15)
    deliver_thread.join(timeout=15)
    assert wait_for_background_kickoffs(timeout=15)
    if turn_error:
        raise turn_error[0]
    if deliver_error:
        raise deliver_error[0]

    return _RaceScenario(
        root=root,
        feature_id=feature_id,
        runner=runner,
        seed_offset=seed_offset,
        turns_before_race=turns_before_race,
    )


def test_append_during_blocked_inflight_turn_reproduces_cursor_loss_and_duplicate_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = _run_mid_turn_append_race(tmp_path, monkeypatch)
    final = feature_graph_values(scenario.feature_id, root=scenario.root)
    final_offset = int(final.get("last_queue_offset") or 0)
    event_messages = [m for m in final.get("messages") or [] if m.get("role") == "event"]

    assert final_offset == scenario.seed_offset
    seed_rows = [m for m in event_messages if "dec_race_seed" in m.get("content", "")]
    append_rows = [m for m in event_messages if "dec_race_append" in m.get("content", "")]
    assert len(seed_rows) == 1
    assert not append_rows
    race_turns = scenario.runner.turn_count - scenario.turns_before_race
    assert race_turns >= 2

    turns_before_redeliver = scenario.runner.turn_count
    deliver_queue_kickoffs(scenario.root)
    assert wait_for_background_kickoffs(timeout=15)
    assert scenario.runner.turn_count - turns_before_redeliver >= 1


@pytest.mark.xfail(reason="feat_017_001: cursor must stay at EOF after mid-turn append")
def test_mid_turn_append_cursor_ends_at_eof(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = _run_mid_turn_append_race(tmp_path, monkeypatch)
    values = feature_graph_values(scenario.feature_id, root=scenario.root)
    assert int(values.get("last_queue_offset") or 0) == queue_eof(scenario.feature_id, root=scenario.root)


@pytest.mark.xfail(reason="feat_017_001: appended queue event must be ingested exactly once")
def test_mid_turn_append_event_ingested_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    scenario = _run_mid_turn_append_race(tmp_path, monkeypatch)
    values = feature_graph_values(scenario.feature_id, root=scenario.root)
    events = [m for m in values.get("messages") or [] if m.get("role") == "event"]
    append_rows = [m for m in events if "dec_race_append" in m.get("content", "")]
    assert len(append_rows) == 1
    assert len(events) == 2
