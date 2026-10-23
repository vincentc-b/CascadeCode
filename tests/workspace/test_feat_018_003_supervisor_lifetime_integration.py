"""Supervisor lifetime integration (feat_018_003 / task_018_003_002)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from tests.harness.cascade_up_subprocess import (
    free_port,
    poll_until,
    process_exists,
    start_cascade_up,
)


def _warm_cascade_cli(env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "-c", "import cascade.cli; import cascade.workspace.up"],
        env=env,
        capture_output=True,
        check=True,
    )


def test_kill9_launcher_worker_exits_nonzero_and_holds_supervisor_lock(
    tmp_path: Path,
) -> None:
    proc = start_cascade_up(tmp_path)
    worker_pid = proc.worker_pid
    assert worker_pid is not None
    assert proc.launcher.pid is not None
    subprocess_cwd = proc.stderr_path.parent / "second_up_cwd"
    subprocess_cwd.mkdir(exist_ok=True)
    _warm_cascade_cli(proc.env)
    try:
        competing = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "cascade.cli",
                "up",
                "--root",
                str(proc.root),
                "--host",
                "127.0.0.1",
                "--port",
                str(free_port()),
            ],
            cwd=subprocess_cwd,
            env=proc.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Allow the child to finish importing before the launcher is SIGKILL'd.
        time.sleep(2.5)
        os.kill(proc.launcher.pid, signal.SIGKILL)
        proc.launcher.wait(timeout=10)

        try:
            _stdout, stderr = competing.communicate(timeout=15.0)
        except subprocess.TimeoutExpired:
            competing.kill()
            competing.communicate(timeout=5)
            raise AssertionError(
                "competing cascade up started serving instead of refusing the lock"
            ) from None
        combined = stderr.lower()
        assert competing.returncode != 0, stderr
        assert "already running" in combined

        poll_until(lambda: not process_exists(worker_pid), timeout=20.0)

        log = proc.stderr_path.read_text(encoding="utf-8")
        assert "launcher_lost" in log
    finally:
        if proc.launcher.poll() is None:
            proc.launcher.kill()
            proc.launcher.wait(timeout=10)
        proc.stderr_stream.close()


def test_second_sigterm_while_stopping_kills_worker_group_at_once(
    tmp_path: Path,
) -> None:
    proc = start_cascade_up(tmp_path)
    worker_pid = proc.worker_pid
    assert worker_pid is not None
    try:
        proc.launcher.send_signal(signal.SIGTERM)
        time.sleep(0.05)
        proc.launcher.send_signal(signal.SIGTERM)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if not process_exists(worker_pid):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("worker survived second SIGTERM escalation")
        proc.launcher.wait(timeout=10)
    finally:
        if proc.launcher.poll() is None:
            proc.launcher.kill()
            proc.launcher.wait(timeout=10)
        proc.stderr_stream.close()
