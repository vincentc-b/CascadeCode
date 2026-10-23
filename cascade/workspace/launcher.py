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

from cascade.workspace.degraded_responder import serve_one_degraded_request
from cascade.workspace.git_lock_sweep import GitLockSweepResult, sweep_stale_git_locks
from cascade.workspace.source_fingerprint import source_fingerprint
from cascade.workspace.supervisor_status import (
    LastError,
    SupervisorState,
    SupervisorStatus,
    read_supervisor_status,
    utc_now_iso,
    write_supervisor_status,
)

EXIT_UPDATE = 75
POST_READY_CRASH_DELAY_S = 1.0
BACKOFF_INITIAL_S = 1.0
BACKOFF_MAX_S = 30.0
MAX_PRE_READY_ATTEMPTS = 5
READY_RESET_S = 60.0
STDERR_TAIL_MAX_BYTES = 8192
LISTEN_BACKLOG = 64
READINESS_TIMEOUT_S = 300.0
READINESS_MESSAGE = b"ready\n"

ENV_LISTEN_FD = "CASCADE_SUPERVISOR_LISTEN_FD"
ENV_READINESS_FD = "CASCADE_SUPERVISOR_READINESS_FD"
ENV_LOCK_TOKEN = "CASCADE_SUPERVISOR_LOCK_TOKEN"
ENV_LOCK_FD = "CASCADE_SUPERVISOR_LOCK_FD"
ENV_LOG_STDERR_FD = "CASCADE_SUPERVISOR_LOG_STDERR_FD"

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

    def snapshot_status(self) -> SupervisorStatus:
        return {
            "state": self._state,
            "worker_pid": self.worker_pid,
            "restart_count": self.restart_count,
            "last_error": self.last_error,
            "next_action": self.next_action,
            "trunk_lock_warning": self.trunk_lock_warning,
            "since": self._since,
            "updated_at": utc_now_iso(),
        }


class _StderrForwarder:
    """Forward worker stderr to the launcher and keep a bounded tail."""

    def __init__(self, *, max_bytes: int = STDERR_TAIL_MAX_BYTES) -> None:
        self._max_bytes = max_bytes
        self._tail = ""
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self, stream: object) -> None:
        self._thread = threading.Thread(
            target=self._run,
            args=(stream,),
            name="launcher-worker-stderr",
            daemon=True,
        )
        self._thread.start()

    def _run(self, stream: object) -> None:
        readline = getattr(stream, "readline", None)
        if readline is None:
            return
        while True:
            try:
                chunk = readline()
            except (OSError, ValueError):
                break
            if not chunk:
                break
            try:
                sys.stderr.buffer.write(chunk)
                sys.stderr.buffer.flush()
            except OSError:
                pass
            text = chunk.decode("utf-8", errors="replace")
            with self._lock:
                self._tail += text
                if len(self._tail) > self._max_bytes:
                    self._tail = self._tail[-self._max_bytes :]

    def tail(self) -> str:
        with self._lock:
            return self._tail

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout=timeout)


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


def _backoff_delay_s(restart_count: int) -> float:
    """Exponential backoff after a pre-ready failure (1s doubling, capped at 30s)."""

    if restart_count <= 0:
        return BACKOFF_INITIAL_S
    exponent = min(restart_count - 1, 20)
    return min(BACKOFF_INITIAL_S * (2**exponent), BACKOFF_MAX_S)


def _wait_for_delay(
    delay_s: float, stop_requested: Callable[[], bool]
) -> bool:
    """Return false when shutdown interrupts a restart delay."""

    deadline = time.monotonic() + delay_s
    while time.monotonic() < deadline:
        if stop_requested():
            return False
        time.sleep(min(0.1, max(0.0, deadline - time.monotonic())))
    return not stop_requested()


def _pre_ready_next_action(restart_count: int) -> str:
    if restart_count >= MAX_PRE_READY_ATTEMPTS:
        return (
            "Fix the worker error and save Cascade source; the launcher will "
            "retry automatically on the next change. To retry now, stop and "
            "rerun `cascade up`."
        )
    return (
        "The launcher is retrying with exponential backoff. Fix source errors "
        "or wait for the next automatic attempt."
    )


def _run_degraded_responder(
    *,
    listen_sock: socket.socket,
    status_ctx: _LauncherStatusContext,
    stop_requested: Callable[[], bool],
    stop_state: _OperatorStopState,
) -> bool:
    """Hold the listen socket and serve 503 until source changes. Returns True to relaunch."""

    fingerprint_at_entry = source_fingerprint()
    _launcher_transition(
        status_ctx,
        state="degraded",
        log_line="cascade launcher: degraded (worker unavailable)",
        worker_pid=None,
        next_action=_pre_ready_next_action(status_ctx.restart_count),
    )
    while True:
        if stop_state.escalate or stop_requested():
            return False
        if source_fingerprint() != fingerprint_at_entry:
            status_ctx.restart_count = 0
            _launcher_transition(
                status_ctx,
                state="restarting",
                log_line="cascade launcher: source changed, relaunching worker",
                worker_pid=None,
            )
            return True
        ready, _, _ = select.select([listen_sock], [], [], 0.5)
        if not ready:
            continue
        try:
            conn, _addr = listen_sock.accept()
        except OSError:
            continue
        with conn:
            status = read_supervisor_status(status_ctx.workspace_root)
            if status is None:
                status = status_ctx.snapshot_status()
            serve_one_degraded_request(conn, status=status)


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
    log_stderr_fd = os.dup(2)
    env[ENV_LOG_STDERR_FD] = str(log_stderr_fd)
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
            pass_fds=(listen_fd, readiness_w, lock_fd, log_stderr_fd),
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except BaseException:
        os.close(readiness_r)
        os.close(readiness_w)
        os.close(log_stderr_fd)
        raise
    else:
        os.close(readiness_w)
        os.close(log_stderr_fd)
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
            stderr_forwarder = _StderrForwarder()
            if proc.stderr is not None:
                stderr_forwarder.start(proc.stderr)

            def _finalize_worker() -> None:
                _kill_worker_group(pgid, proc=proc)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                stderr_forwarder.join(timeout=2.0)
                status_ctx.apply_sweep(post_worker_exit(workspace_root))

            def _handle_pre_ready_failure(exc: BaseException) -> bool:
                """Return True to continue the outer spawn loop, False to exit the launcher."""

                status_ctx.restart_count += 1
                _kill_worker_group(pgid, proc=proc)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=10)
                stderr_forwarder.join(timeout=2.0)
                exit_code = proc.returncode
                _launcher_transition(
                    status_ctx,
                    state="restarting",
                    log_line=f"cascade launcher: worker readiness failed: {exc}",
                    worker_pid=proc.pid,
                    last_error={
                        "exit_code": exit_code,
                        "stderr_tail": stderr_forwarder.tail() or None,
                        "message": str(exc),
                    },
                    next_action=_pre_ready_next_action(status_ctx.restart_count),
                )
                status_ctx.apply_sweep(post_worker_exit(workspace_root))
                if status_ctx.restart_count >= MAX_PRE_READY_ATTEMPTS:
                    return _run_degraded_responder(
                        listen_sock=listen_sock,
                        status_ctx=status_ctx,
                        stop_requested=stop_requested,
                        stop_state=stop_state,
                    )
                delay = _backoff_delay_s(status_ctx.restart_count)
                return _wait_for_delay(delay, stop_requested)

            try:
                _wait_readiness(
                    readiness_fd,
                    proc=proc,
                    stop_requested=stop_requested,
                )
            except _EscalatedStop:
                _finalize_worker()
                return
            except _StopRequested:
                _launcher_transition(
                    status_ctx,
                    state="draining",
                    log_line="cascade launcher: draining worker (stop during startup)",
                    worker_pid=proc.pid,
                )
                _finalize_worker()
                return
            except (OSError, RuntimeError, TimeoutError) as exc:
                if not _handle_pre_ready_failure(exc):
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
                next_action=None,
            )
            ready_since = time.monotonic()
            restart_count_reset = False

            while True:
                raise_if_escalated(pgid, proc=proc)
                if (
                    not restart_count_reset
                    and status_ctx.restart_count > 0
                    and time.monotonic() - ready_since >= READY_RESET_S
                ):
                    status_ctx.restart_count = 0
                    restart_count_reset = True
                    _launcher_transition(
                        status_ctx,
                        state="serving",
                        log_line=(
                            f"cascade launcher: worker stable (pid {proc.pid}); "
                            "restart counter reset"
                        ),
                        worker_pid=proc.pid,
                    )
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

            _finalize_worker()

            if stop_requested() or code == 0:
                return
            if code == EXIT_UPDATE:
                status_ctx.restart_count = 0
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
                    "stderr_tail": stderr_forwarder.tail() or None,
                    "message": f"worker exited with code {code}",
                },
            )
            if not _wait_for_delay(POST_READY_CRASH_DELAY_S, stop_requested):
                return
    finally:
        if installed_signal_handlers:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)
