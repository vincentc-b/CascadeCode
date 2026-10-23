"""Readiness live→ready transitions and observation boundaries (feat_012_001 / task_012_001_005)."""

from __future__ import annotations

import json
import threading
import urllib.request
from http import HTTPStatus

from cascade.board.store import read_doc
from cascade.watchdog import read_events
from tests.war_room.test_http_read import war_room_server


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def test_health_readiness_transition_and_degraded_details(war_room_server) -> None:
    from cascade.workspace.supervisor_readiness import (
        observe_startup_phase,
        record_loop_success,
        record_recovery_enqueued,
        record_recovery_failure,
        reset_supervisor_readiness_for_tests,
    )
    from cascade.workspace.supervisor_status import utc_now_iso, write_supervisor_status

    base, root, _server = war_room_server
    reset_supervisor_readiness_for_tests()

    now = utc_now_iso()
    write_supervisor_status(
        root,
        {
            "state": "update_blocked",
            "worker_pid": 1,
            "restart_count": 0,
            "last_error": {"message": "syntax error"},
            "next_action": "Fix cascade.toml",
            "trunk_lock_warning": None,
            "since": now,
            "updated_at": now,
        },
    )

    status, payload = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is False
    assert payload["state"] == "update_blocked"
    reasons = payload["automation"]["degraded_reasons"]
    assert "supervisor:update_blocked" in reasons
    assert "watchdog:no_success_yet" in reasons
    assert "reconciliation:no_success_yet" in reasons

    record_recovery_enqueued("feat_001")
    record_recovery_failure(
        "feat_001",
        code="background_error",
        message="model turn failed",
        at="2026-01-01T00:00:02+00:00",
    )
    status, payload = _get(f"{base}/api/health")
    assert payload["recovery"]["failures"][0]["work_id"] == "feat_001"
    assert "recovery:feat_001:background_error" in payload["automation"]["degraded_reasons"]

    reset_supervisor_readiness_for_tests()
    write_supervisor_status(
        root,
        {
            "state": "serving",
            "worker_pid": 1,
            "restart_count": 0,
            "last_error": None,
            "next_action": None,
            "trunk_lock_warning": None,
            "since": now,
            "updated_at": now,
        },
    )
    observe_startup_phase("ready")
    record_loop_success("watchdog", at="2026-01-01T00:00:03+00:00")
    record_loop_success("reconciliation", at="2026-01-01T00:00:04+00:00")

    status, payload = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is True
    assert payload["loops"]["watchdog"]["last_success_at"] == "2026-01-01T00:00:03+00:00"
    assert payload["loops"]["reconciliation"]["last_success_at"] == "2026-01-01T00:00:04+00:00"


def test_health_reads_do_not_mutate_lifecycle_or_dispatch(war_room_server) -> None:
    base, root, _server = war_room_server
    from cascade.workspace.supervisor_readiness import reset_supervisor_readiness_for_tests

    reset_supervisor_readiness_for_tests()
    task_before = read_doc("task_001", root=root)
    assert task_before.meta.status == "active"
    events_before, offset = read_events("feat_001", 0, root=root)

    for _ in range(3):
        status, _payload = _get(f"{base}/api/health")
        assert status == HTTPStatus.OK

    task_after = read_doc("task_001", root=root)
    assert task_after.meta.status == task_before.meta.status
    assert task_after.meta.updated == task_before.meta.updated
    events_after, _ = read_events("feat_001", offset, root=root)
    assert events_after == []
    before_docs = sorted(p.name for p in (root / "docs").rglob("*.md"))
    after_docs = sorted(p.name for p in (root / "docs").rglob("*.md"))
    assert before_docs == after_docs


def test_watchdog_loops_reported_over_http_while_recovery_still_in_flight(
    war_room_server,
) -> None:
    """Supervision milestones may land on /api/health before recovered turns finish."""

    from cascade.workspace.supervisor_readiness import (
        note_recovery_turn_finished,
        note_recovery_turn_started,
        observe_startup_phase,
        record_loop_success,
        record_recovery_enqueued,
        reset_supervisor_readiness_for_tests,
    )

    base, _root, _server = war_room_server
    reset_supervisor_readiness_for_tests()
    release_recovery = threading.Event()
    recovery_running = threading.Event()

    def slow_recovery() -> None:
        record_recovery_enqueued("feat_001")
        observe_startup_phase("recovery")
        note_recovery_turn_started("feat_001")
        recovery_running.set()
        assert release_recovery.wait(10)
        note_recovery_turn_finished("feat_001")

    threading.Thread(target=slow_recovery, daemon=True).start()
    assert recovery_running.wait(5)

    record_loop_success("reconciliation", at="2026-01-01T00:00:01+00:00")
    record_loop_success("watchdog", at="2026-01-01T00:00:02+00:00")

    status, payload = _get(f"{base}/api/health")
    assert status == HTTPStatus.OK
    assert payload["http"]["live"] is True
    assert payload["automation"]["ready"] is False
    assert payload["automation"]["phase"] == "recovery"
    assert payload["recovery"]["in_flight"] == 1
    assert payload["loops"]["reconciliation"]["last_success_at"] is not None
    assert payload["loops"]["watchdog"]["last_success_at"] is not None
    assert "startup:recovery" in payload["automation"]["degraded_reasons"]

    release_recovery.set()
