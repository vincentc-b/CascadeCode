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
from dataclasses import dataclass, field
from pathlib import Path

from cascade.workspace.git_lock_sweep import GitLockSweepResult, sweep_stale_git_locks
from cascade.workspace.source_fingerprint import source_fingerprint
from cascade.workspace.supervisor_status import (
    LastError,
    SupervisorState,
    SupervisorStatus,
    utc_now_iso,
    write_supervisor_status,
)

EXIT_UPDATE = 75
CRASH_RESTART_DELAY_S = 1.0
LISTEN_BACKLOG = 64
READINESS_TIMEOUT_S = 300.0
READINESS_MESSAGE = b"ready\n"

ENV_LISTEN_FD = "CASCADE_SUPERVISOR_LISTEN_FD"
ENV_READINESS_FD = "CASCADE_SUPERVISOR_READINESS_FD"
ENV_LOCK_TOKEN = "CASCADE_SUPERVISOR_LOCK_TOKEN"
ENV_LOCK_FD = "CASCADE_SUPERVISOR_LOCK_FD"

_WORKER_MODULE = "cascade.workspace.worker"
_CASCADE_SOURCE_PARENT = str(Path(__file__).resolve().parents[2])


class _StopRequested(Exception):
    """Internal control flow for a stop requested during worker startup."""


class _EscalatedStop(Exception):
    """Second operator signal while stopping: kill worker group and exit."""


@dataclass
class _OperatorStopState:
    requested: bool = False
    worker_stop_forwarded: bool = False
    escalate: bool = False


@dataclass
class _LauncherStatusContext:
    workspace_root: Path
    restart_count: int = 0
    worker_pid: int | None = None
    last_error: LastError | None = None
    next_action: str | None = None
    trunk_lock_warning: str | None = None
    _state: SupervisorState = "restarting"
    _since: str = field(default_factory=utc_now_iso)

    def apply_sweep(self, sweep: GitLockSweepResult) -> None:
        if sweep.trunk_index_lock_path is not None:
            self.trunk_lock_warning = sweep.trunk_index_lock_path


def _launcher_transition(
    ctx: _LauncherStatusContext,
    *,
    state: SupervisorState,
    log_line: str,
    worker_pid: int | None | object = ...,
    last_error: LastError | None | object = ...,
    next_action: str | None | object = ...,
) -> None:
    print(log_line, file=sys.stderr)
    if state != ctx._state:
        ctx._state = state
        ctx._since = utc_now_iso()
    if worker_pid is not ...:
        ctx.worker_pid = worker_pid  # type: ignore[assignment]
    if last_error is not ...:
        ctx.last_error = last_error  # type: ignore[assignment]
    if next_action is not ...:
        ctx.next_action = next_action  # type: ignore[assignment]
    status: SupervisorStatus = {
        "state": ctx._state,
        "worker_pid": ctx.worker_pid,
        "restart_count": ctx.restart_count,
        "last_error": ctx.last_error,
        "next_action": ctx.next_action,
        "trunk_lock_warning": ctx.trunk_lock_warning,
        "since": ctx._since,
        "updated_at": utc_now_iso(),
    }
    write_supervisor_status(ctx.workspace_root, status)


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


def post_worker_exit(workspace_root: Path) -> GitLockSweepResult:
    """Hook after the worker process group is gone: sweep stale git locks."""

    return sweep_stale_git_locks(workspace_root)


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
    lock_fd: int,
    lock_token: str,
) -> tuple[subprocess.Popen[bytes], int, int]:
    readiness_r, readiness_w = os.pipe()
    env = os.environ.copy()
    env[ENV_LISTEN_FD] = str(listen_fd)
    env[ENV_READINESS_FD] = str(readiness_w)
    env[ENV_LOCK_FD] = str(lock_fd)
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
            pass_fds=(listen_fd, readiness_w, lock_fd),
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
    lock_fd: int,
    stop_when: Callable[[], bool] | None = None,
) -> None:
    """Spawn workers on ``listen_sock`` until operator stop or ``stop_when``."""

    source_fingerprint()

    listen_fd = listen_sock.fileno()
    stop_state = _OperatorStopState()
    installed_signal_handlers = threading.current_thread() is threading.main_thread()
    previous_handlers: dict[int, signal.Handlers] = {}
    status_ctx = _LauncherStatusContext(workspace_root=workspace_root)

    def on_operator_signal(_signum: int, _frame: object | None) -> None:
        if stop_state.requested and stop_state.worker_stop_forwarded:
            stop_state.escalate = True
        stop_state.requested = True

    if installed_signal_handlers:
        for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.getsignal(signum)
            signal.signal(signum, on_operator_signal)

    def stop_requested() -> bool:
        return stop_state.requested or (stop_when is not None and stop_when())

    def raise_if_escalated(
        pgid: int, *, proc: subprocess.Popen[bytes] | None = None
    ) -> None:
        if not stop_state.escalate:
            return
        _kill_worker_group(pgid, proc=proc)
        if proc is not None:
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        raise _EscalatedStop()

    try:
        while True:
            if stop_requested():
                return

            _launcher_transition(
                status_ctx,
                state="restarting",
                log_line="cascade launcher: restarting worker",
                worker_pid=None,
                last_error=None,
            )

            proc, readiness_fd, pgid = _spawn_worker(
                workspace_root=workspace_root,
                listen_fd=listen_fd,
                lock_fd=lock_fd,
                lock_token=lock_token,
            )
            try:
                _wait_readiness(
                    readiness_fd,
                    proc=proc,
                    stop_requested=stop_requested,
                )
            except _EscalatedStop:
                status_ctx.apply_sweep(post_worker_exit(workspace_root))
                return
            except _StopRequested:
                _launcher_transition(
                    status_ctx,
                    state="draining",
                    log_line="cascade launcher: draining worker (stop during startup)",
                    worker_pid=proc.pid,
                )
                _kill_worker_group(pgid, proc=proc)
                proc.wait(timeout=30)
                status_ctx.apply_sweep(post_worker_exit(workspace_root))
                return
            except (OSError, RuntimeError, TimeoutError) as exc:
                _launcher_transition(
                    status_ctx,
                    state="restarting",
                    log_line=f"cascade launcher: worker readiness failed: {exc}",
                    worker_pid=proc.pid,
                    last_error={
                        "exit_code": proc.returncode,
                        "stderr_tail": None,
                        "message": str(exc),
                    },
                )
                _kill_worker_group(pgid, proc=proc)
                proc.wait(timeout=30)
                status_ctx.apply_sweep(post_worker_exit(workspace_root))
                if not _wait_for_restart_delay(stop_requested):
                    return
                continue
            finally:
                os.close(readiness_fd)

            _launcher_transition(
                status_ctx,
                state="serving",
                log_line=f"cascade launcher: worker ready (pid {proc.pid})",
                worker_pid=proc.pid,
                last_error=None,
            )

            while True:
                raise_if_escalated(pgid, proc=proc)
                if stop_requested():
                    if not stop_state.worker_stop_forwarded:
                        _launcher_transition(
                            status_ctx,
                            state="draining",
                            log_line="cascade launcher: draining worker",
                            worker_pid=proc.pid,
                        )
                        proc.send_signal(signal.SIGTERM)
                        stop_state.worker_stop_forwarded = True
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

            sweep = post_worker_exit(workspace_root)
            status_ctx.apply_sweep(sweep)

            if stop_requested() or code == 0:
                return
            if code == EXIT_UPDATE:
                _launcher_transition(
                    status_ctx,
                    state="restarting",
                    log_line="cascade launcher: worker exited for source update",
                    worker_pid=None,
                )
                continue
            _launcher_transition(
                status_ctx,
                state="restarting",
                log_line=f"cascade launcher: worker exited unexpectedly (code {code})",
                worker_pid=None,
                last_error={
                    "exit_code": code,
                    "stderr_tail": None,
                    "message": f"worker exited with code {code}",
                },
            )
            if not _wait_for_restart_delay(stop_requested):
                return
    finally:
        if installed_signal_handlers:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
