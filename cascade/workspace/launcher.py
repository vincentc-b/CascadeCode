"""Stdlib-only ``cascade up`` launcher loop.

After ``cascade.workspace.up`` validates the workspace and binds the listen
socket, this module owns worker spawn, process-group sweep, a post-exit hook,
and relaunch. It must not import changing Cascade packages.
"""

from __future__ import annotations

import os
import select
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from cascade.workspace.git_lock_sweep import sweep_stale_git_locks

EXIT_UPDATE = 75
CRASH_RESTART_DELAY_S = 1.0
LISTEN_BACKLOG = 64
READINESS_TIMEOUT_S = 300.0
READINESS_MESSAGE = b"ready\n"

ENV_LISTEN_FD = "CASCADE_SUPERVISOR_LISTEN_FD"
ENV_READINESS_FD = "CASCADE_SUPERVISOR_READINESS_FD"
ENV_LOCK_TOKEN = "CASCADE_SUPERVISOR_LOCK_TOKEN"

_WORKER_MODULE = "cascade.workspace.worker"
_CASCADE_SOURCE_PARENT = str(Path(__file__).resolve().parents[2])


class _StopRequested(Exception):
    """Internal control flow for a stop requested during worker startup."""


def bind_listen_socket(*, host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        sock.listen(LISTEN_BACKLOG)
    except OSError:
        sock.close()
        raise
    return sock


def post_worker_exit(workspace_root: Path) -> None:
    """Hook after the worker process group is gone: sweep stale git locks."""

    sweep_stale_git_locks(workspace_root)


def _wait_readiness(
    readiness_fd: int,
    *,
    proc: subprocess.Popen[bytes],
    stop_requested: Callable[[], bool],
) -> None:
    buf = b""
    deadline = time.monotonic() + READINESS_TIMEOUT_S
    while b"\n" not in buf:
        if stop_requested():
            raise _StopRequested
        if proc.poll() is not None:
            raise RuntimeError(
                f"worker exited before readiness (code {proc.returncode})"
            )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("worker did not report readiness in time")
        ready, _, _ = select.select([readiness_fd], [], [], min(remaining, 0.2))
        if not ready:
            continue
        chunk = os.read(readiness_fd, 4096)
        if not chunk:
            raise RuntimeError("readiness pipe closed before worker signaled ready")
        buf += chunk
    if not buf.startswith(READINESS_MESSAGE):
        raise RuntimeError(f"unexpected readiness message: {buf!r}")


def _kill_worker_group(
    pgid: int, *, proc: subprocess.Popen[bytes] | None = None
) -> None:
    try:
        os.killpg(pgid, signal.SIGTERM)
    except ProcessLookupError:
        return
    grace_deadline = time.monotonic() + 5.0
    while time.monotonic() < grace_deadline:
        if proc is not None:
            proc.poll()
        try:
            os.killpg(pgid, 0)
        except ProcessLookupError:
            return
        time.sleep(0.05)
    try:
        os.killpg(pgid, signal.SIGKILL)
    except ProcessLookupError:
        pass


def _wait_for_restart_delay(stop_requested: Callable[[], bool]) -> bool:
    """Return false when shutdown interrupts the crash-restart delay."""

    deadline = time.monotonic() + CRASH_RESTART_DELAY_S
    while time.monotonic() < deadline:
        if stop_requested():
            return False
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    return not stop_requested()


def _spawn_worker(
    *,
    workspace_root: Path,
    listen_fd: int,
    lock_token: str,
) -> tuple[subprocess.Popen[bytes], int, int]:
    readiness_r, readiness_w = os.pipe()
    env = os.environ.copy()
    env[ENV_LISTEN_FD] = str(listen_fd)
    env[ENV_READINESS_FD] = str(readiness_w)
    env[ENV_LOCK_TOKEN] = lock_token
    current_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = (
        _CASCADE_SOURCE_PARENT
        if not current_pythonpath
        else os.pathsep.join((_CASCADE_SOURCE_PARENT, current_pythonpath))
    )

    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", _WORKER_MODULE],
            cwd=workspace_root,
            env=env,
            pass_fds=(listen_fd, readiness_w),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
        )
    except BaseException:
        os.close(readiness_r)
        os.close(readiness_w)
        raise
    else:
        os.close(readiness_w)
    pgid = proc.pid
    return proc, readiness_r, pgid


def run_launcher_loop(
    *,
    workspace_root: Path,
    listen_sock: socket.socket,
    lock_token: str,
    stop_when: Callable[[], bool] | None = None,
) -> None:
    """Spawn workers on ``listen_sock`` until operator stop or ``stop_when``."""

    listen_fd = listen_sock.fileno()
    operator_stop = False
    installed_signal_handlers = threading.current_thread() is threading.main_thread()
    previous_handlers: dict[int, signal.Handlers] = {}

    def on_operator_signal(_signum: int, _frame: object | None) -> None:
        nonlocal operator_stop
        operator_stop = True

    if installed_signal_handlers:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, on_operator_signal)

    def stop_requested() -> bool:
        return operator_stop or (stop_when is not None and stop_when())

    try:
        while True:
            if stop_requested():
                return

            proc, readiness_fd, pgid = _spawn_worker(
                workspace_root=workspace_root,
                listen_fd=listen_fd,
                lock_token=lock_token,
            )
            try:
                _wait_readiness(
                    readiness_fd,
                    proc=proc,
                    stop_requested=stop_requested,
                )
            except _StopRequested:
                _kill_worker_group(pgid, proc=proc)
                proc.wait(timeout=30)
                post_worker_exit(workspace_root)
                return
            except (OSError, RuntimeError, TimeoutError) as exc:
                print(
                    f"cascade launcher: worker readiness failed: {exc}",
                    file=sys.stderr,
                )
                _kill_worker_group(pgid, proc=proc)
                proc.wait(timeout=30)
                post_worker_exit(workspace_root)
                if not _wait_for_restart_delay(stop_requested):
                    return
                continue
            finally:
                os.close(readiness_fd)

            while True:
                if stop_requested():
                    proc.send_signal(signal.SIGTERM)
                try:
                    code = proc.wait(timeout=0.2)
                except subprocess.TimeoutExpired:
                    continue
                break

            _kill_worker_group(pgid)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

            post_worker_exit(workspace_root)

            if stop_requested() or code == 0:
                return
            if code == EXIT_UPDATE:
                continue
            if not _wait_for_restart_delay(stop_requested):
                return
    finally:
        if installed_signal_handlers:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
