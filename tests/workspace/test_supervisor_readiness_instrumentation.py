"""Watchdog and startup wiring for supervisor readiness (feat_012_001 / task_012_001_002)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.watchdog.loop import clear_watchdog_memory, run_watchdog
from cascade.workspace.supervisor_readiness import (
    observe_startup_phase,
    project_supervisor_health,
    reset_supervisor_readiness_for_tests,
    snapshot_readiness_evidence,
)
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _reset_watchdog_and_readiness() -> None:
    clear_watchdog_memory()
    reset_supervisor_readiness_for_tests()
    yield
    clear_watchdog_memory()
    reset_supervisor_readiness_for_tests()


def test_run_watchdog_records_reconciliation_and_watchdog_success(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    observe_startup_phase("watchdog")
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    run_watchdog(root=root, poll_interval=0, stop_when=stop)

    evidence = snapshot_readiness_evidence()
    assert evidence.reconciliation.last_success_at is not None
    assert evidence.watchdog.last_success_at is not None
    payload = project_supervisor_health(None, evidence, http_serving=True)
    assert payload is not None
    assert payload["automation"]["ready"] is True
    assert payload["automation"]["phase"] == "ready"


def test_run_watchdog_records_watchdog_error_on_failed_tick(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    observe_startup_phase("watchdog")
    loop_visits = [0]

    def tick(_root: Path) -> None:
        raise RuntimeError("transient tick failure")

    monkeypatch.setattr("cascade.watchdog.loop.watchdog_tick", tick)
    monkeypatch.setattr("cascade.watchdog.loop.time.sleep", lambda _seconds: None)

    def stop() -> bool:
        loop_visits[0] += 1
        return loop_visits[0] > 1

    run_watchdog(root=root, poll_interval=0, stop_when=stop)

    evidence = snapshot_readiness_evidence()
    assert evidence.reconciliation.last_success_at is not None
    assert evidence.watchdog.last_error is not None
    assert evidence.watchdog.last_error["code"] == "RuntimeError"
    assert evidence.watchdog.last_success_at is None
    payload = project_supervisor_health(None, evidence, http_serving=True)
    assert payload is not None
    assert payload["automation"]["ready"] is False
    assert "watchdog:no_success_yet" in payload["automation"]["degraded_reasons"]
