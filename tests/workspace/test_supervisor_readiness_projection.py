"""Supervisor readiness projection (feat_012_001 / task_012_001_001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.workspace.supervisor_readiness import (
    observe_startup_phase,
    project_supervisor_health,
    read_supervisor_health_projection,
    record_loop_success,
    reset_supervisor_readiness_for_tests,
    snapshot_readiness_evidence,
)
from cascade.workspace.supervisor_status import utc_now_iso


@pytest.fixture(autouse=True)
def _clear_readiness_evidence() -> None:
    reset_supervisor_readiness_for_tests()
    yield
    reset_supervisor_readiness_for_tests()


def test_projection_separates_http_liveness_from_automation_readiness() -> None:
    now = utc_now_iso()
    status = {
        "state": "serving",
        "worker_pid": 99,
        "restart_count": 0,
        "last_error": None,
        "next_action": None,
        "trunk_lock_warning": None,
        "since": now,
        "updated_at": now,
    }
    evidence = snapshot_readiness_evidence()
    payload = project_supervisor_health(status, evidence, http_serving=True)
    assert payload is not None
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is False
    assert payload["state"] == "serving"
    assert "watchdog:no_success_yet" in payload["automation"]["degraded_reasons"]


def test_automation_becomes_ready_when_loops_and_phase_are_satisfied() -> None:
    observe_startup_phase("ready")
    record_loop_success("watchdog", at="2026-01-01T00:00:01+00:00")
    record_loop_success("reconciliation", at="2026-01-01T00:00:02+00:00")
    evidence = snapshot_readiness_evidence()
    payload = project_supervisor_health(None, evidence, http_serving=True)
    assert payload is not None
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is True
    assert payload["automation"]["degraded_reasons"] == []
    assert payload["loops"]["watchdog"]["last_success_at"] is not None


def test_supervisor_degraded_state_surfaces_actionable_reason() -> None:
    now = utc_now_iso()
    status = {
        "state": "degraded",
        "worker_pid": None,
        "restart_count": 5,
        "last_error": {"message": "worker unavailable"},
        "next_action": "Fix worker startup",
        "trunk_lock_warning": None,
        "since": now,
        "updated_at": now,
    }
    payload = project_supervisor_health(
        status,
        snapshot_readiness_evidence(),
        http_serving=True,
    )
    assert payload is not None
    assert payload["automation"]["ready"] is False
    assert "supervisor:degraded" in payload["automation"]["degraded_reasons"]


def test_read_projection_is_side_effect_free_on_board(tmp_path: Path) -> None:
    from tests.support import add_doc, make_repo

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    before = sorted(p.name for p in (root / "docs").rglob("*.md"))
    _ = read_supervisor_health_projection(root, http_serving=False)
    after = sorted(p.name for p in (root / "docs").rglob("*.md"))
    assert before == after


