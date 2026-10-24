"""Worker startup recovery does not block watchdog (task_012_001_003)."""

from __future__ import annotations

import os
import socket
import threading
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
    monkeypatch.setattr("cascade.watchdog.config.worker_drain_seconds", lambda _root: 0.0)
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
