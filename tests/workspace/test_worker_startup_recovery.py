"""Worker startup recovery does not block watchdog (task_012_001_003)."""

from __future__ import annotations

import os
import socket
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cascade.workspace import worker as worker_mod


def test_watchdog_starts_before_slow_recovery_submission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path
    release_recovery = threading.Event()
    watchdog_started = threading.Event()
    recovery_running = threading.Event()

    def slow_submit(_root: Path) -> None:
        recovery_running.set()
        release_recovery.wait(5)

    def watchdog(*, root: Path, stop_when):  # type: ignore[no-untyped-def]
        watchdog_started.set()
        stop_when()
        return None

    ws = MagicMock(path=root)
    monkeypatch.setattr(worker_mod, "prepare_up", lambda: ws)
    monkeypatch.setattr(worker_mod, "repair_registered_worktrees", lambda _root: None)
    monkeypatch.setattr(worker_mod, "submit_recovered_turns", slow_submit)
    monkeypatch.setattr("cascade.watchdog.loop.run_watchdog", watchdog)
    monkeypatch.setattr(
        "cascade.watchdog.config.worker_drain_seconds", lambda _root: 0.0
    )
    monkeypatch.setattr(worker_mod, "drain_and_shutdown", lambda *args, **kwargs: False)
    monkeypatch.setattr(worker_mod, "_source_fingerprint", lambda: "test")
    monkeypatch.setattr(worker_mod.signal, "signal", lambda *args, **kwargs: None)

    mock_server = MagicMock()
    monkeypatch.setattr("cascade.war_room.server.serve", lambda **kwargs: mock_server)

    listen_r, listen_w = socket.socketpair()
    ready_r, ready_w = os.pipe()
    monkeypatch.setenv("CASCADE_SUPERVISOR_LISTEN_FD", str(listen_w.fileno()))
    monkeypatch.setenv("CASCADE_SUPERVISOR_READINESS_FD", str(ready_w))
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_FD", "3")
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_TOKEN", "test-lock")

    stop = threading.Event()
    worker_mod.run_worker(stop_event=stop)

    assert recovery_running.is_set()
    assert watchdog_started.is_set()
    release_recovery.set()


def test_audit_lane_starts_before_blocking_worktree_repair(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.watchdog.audit_lane import read_audit_receipt
    from cascade.watchdog.config import HealthAuditConfig

    repair_entered = threading.Event()
    release_repair = threading.Event()

    def repair(_root: Path) -> None:
        repair_entered.set()
        assert release_repair.wait(15)

    ws = MagicMock(path=tmp_path)
    monkeypatch.setattr(worker_mod, "prepare_up", lambda: ws)
    monkeypatch.setattr(worker_mod, "repair_registered_worktrees", repair)
    monkeypatch.setattr(worker_mod, "submit_recovered_turns", lambda _root: None)
    monkeypatch.setattr(
        "cascade.watchdog.config.read_health_audit_config",
        lambda _root: HealthAuditConfig(enabled=True, interval_seconds=60),
    )
    monkeypatch.setattr("cascade.watchdog.loop.run_watchdog", lambda **_kwargs: None)
    monkeypatch.setattr(
        "cascade.watchdog.config.worker_drain_seconds", lambda _root: 0.0
    )
    monkeypatch.setattr(worker_mod, "drain_and_shutdown", lambda *args, **kwargs: False)
    monkeypatch.setattr(worker_mod, "_source_fingerprint", lambda: "test")
    monkeypatch.setattr(worker_mod.signal, "signal", lambda *args, **kwargs: None)
    mock_server = MagicMock()
    monkeypatch.setattr("cascade.war_room.server.serve", lambda **kwargs: mock_server)

    listen_r, listen_w = socket.socketpair()
    ready_r, ready_w = os.pipe()
    monkeypatch.setenv("CASCADE_SUPERVISOR_LISTEN_FD", str(listen_w.fileno()))
    monkeypatch.setenv("CASCADE_SUPERVISOR_READINESS_FD", str(ready_w))
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_FD", "3")
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_TOKEN", "test-lock")

    worker = threading.Thread(
        target=worker_mod.run_worker, kwargs={"stop_event": threading.Event()}
    )
    worker.start()
    assert repair_entered.wait(2)
    deadline = time.monotonic() + 10
    while read_audit_receipt(tmp_path) is None and time.monotonic() < deadline:
        time.sleep(0.01)
    receipt = read_audit_receipt(tmp_path)
    release_repair.set()
    worker.join(2)

    assert receipt is not None
    assert all(value == 0 for value in receipt["counts"].values())
    assert not worker.is_alive()


def test_operator_stop_cancels_audit_during_blocked_startup_and_cleans_up(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.watchdog import audit_lane as audit_module
    from cascade.watchdog.config import HealthAuditConfig

    repair_entered = threading.Event()
    release_repair = threading.Event()
    audit_cancelled = threading.Event()
    audit_stopped = threading.Event()
    operator_stop = threading.Event()
    errors: list[BaseException] = []

    class ProbeLane:
        def __init__(self, *, stop_event: threading.Event, **_kwargs: object) -> None:
            self.stop_event = stop_event

        def start(self):  # type: ignore[no-untyped-def]
            def wait_for_cancellation() -> None:
                if self.stop_event.wait(2):
                    audit_cancelled.set()

            threading.Thread(
                target=wait_for_cancellation,
                daemon=True,
            ).start()
            return self

        def stop(self, timeout: float | None = None) -> None:
            audit_stopped.set()

    def repair(_root: Path) -> None:
        repair_entered.set()
        assert release_repair.wait(2)
        raise RuntimeError("startup repair failed")

    monkeypatch.setattr(audit_module, "HealthAuditLane", ProbeLane)
    monkeypatch.setattr(worker_mod, "prepare_up", lambda: MagicMock(path=tmp_path))
    monkeypatch.setattr(worker_mod, "repair_registered_worktrees", repair)
    monkeypatch.setattr(
        "cascade.watchdog.config.read_health_audit_config",
        lambda _root: HealthAuditConfig(enabled=True, interval_seconds=60),
    )
    monkeypatch.setattr(
        "cascade.watchdog.config.worker_drain_seconds", lambda _root: 0.0
    )
    monkeypatch.setattr(worker_mod, "drain_and_shutdown", lambda *args, **kwargs: False)
    monkeypatch.setattr(worker_mod, "_source_fingerprint", lambda: "test")
    monkeypatch.setattr(worker_mod.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.war_room.server.serve", lambda **kwargs: MagicMock())

    listen_r, listen_w = socket.socketpair()
    ready_r, ready_w = os.pipe()
    monkeypatch.setenv("CASCADE_SUPERVISOR_LISTEN_FD", str(listen_w.fileno()))
    monkeypatch.setenv("CASCADE_SUPERVISOR_READINESS_FD", str(ready_w))
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_FD", "3")
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_TOKEN", "test-lock")

    def run() -> None:
        try:
            worker_mod.run_worker(stop_event=operator_stop)
        except BaseException as exc:
            errors.append(exc)

    worker = threading.Thread(target=run)
    worker.start()
    try:
        assert repair_entered.wait(2)
        operator_stop.set()
        assert audit_cancelled.wait(1)
    finally:
        release_repair.set()
        worker.join(2)
        listen_r.close()
        listen_w.close()
        os.close(ready_r)
        os.close(ready_w)

    assert not worker.is_alive()
    assert audit_stopped.is_set()
    assert len(errors) == 1 and str(errors[0]) == "startup repair failed"


@pytest.mark.parametrize("outcome", ["update", "crash"])
def test_audit_cleanup_preserves_worker_shutdown_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, outcome: str
) -> None:
    from cascade.watchdog.config import HealthAuditConfig

    ws = MagicMock(path=tmp_path)
    operator_stop = threading.Event()
    shutdown_reasons: list[str] = []
    fingerprints = iter(["before", "after"])
    monkeypatch.setattr(worker_mod, "prepare_up", lambda: ws)
    monkeypatch.setattr(worker_mod, "repair_registered_worktrees", lambda _root: None)
    monkeypatch.setattr(worker_mod, "submit_recovered_turns", lambda _root: None)
    monkeypatch.setattr(
        "cascade.watchdog.config.read_health_audit_config",
        lambda _root: HealthAuditConfig(enabled=False, interval_seconds=60),
    )
    monkeypatch.setattr(
        "cascade.watchdog.config.worker_drain_seconds", lambda _root: 0.0
    )
    monkeypatch.setattr(worker_mod, "_source_fingerprint", lambda: next(fingerprints))
    monkeypatch.setattr(worker_mod, "_SOURCE_CHECK_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(worker_mod.signal, "signal", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        worker_mod,
        "drain_and_shutdown",
        lambda *args, **kwargs: shutdown_reasons.append(kwargs["reason"]) or False,
    )
    monkeypatch.setattr("cascade.war_room.server.serve", lambda **kwargs: MagicMock())

    if outcome == "update":
        monkeypatch.setattr(
            worker_mod, "run_update_preflight", lambda _root: MagicMock(ok=True)
        )

        def watchdog(*, root: Path, stop_when):  # type: ignore[no-untyped-def]
            assert stop_when()

    else:

        def watchdog(*, root: Path, stop_when):  # type: ignore[no-untyped-def]
            raise RuntimeError("watchdog failed")

    monkeypatch.setattr("cascade.watchdog.loop.run_watchdog", watchdog)
    listen_r, listen_w = socket.socketpair()
    ready_r, ready_w = os.pipe()
    monkeypatch.setenv("CASCADE_SUPERVISOR_LISTEN_FD", str(listen_w.fileno()))
    monkeypatch.setenv("CASCADE_SUPERVISOR_READINESS_FD", str(ready_w))
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_FD", "3")
    monkeypatch.setenv("CASCADE_SUPERVISOR_LOCK_TOKEN", "test-lock")
    try:
        if outcome == "update":
            code, abandoned = worker_mod.run_worker(stop_event=operator_stop)
            assert (code, abandoned) == (worker_mod.EXIT_UPDATE, False)
        else:
            with pytest.raises(RuntimeError, match="watchdog failed"):
                worker_mod.run_worker(stop_event=operator_stop)
    finally:
        listen_r.close()
        # run_worker takes ownership of the inherited listener descriptor.
        listen_w.detach()
        os.close(ready_r)
        os.close(ready_w)

    assert not operator_stop.is_set()
    assert shutdown_reasons == [outcome]
