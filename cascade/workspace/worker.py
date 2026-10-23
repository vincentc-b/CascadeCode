"""Replaceable ``cascade up`` worker: War Room on an inherited listen fd + watchdog.

Spawned only by the launcher (``task_018_001_002``). Refuses to start without the
handshake env vars below; does not take ``.cascade/supervisor.lock``.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
import time
import traceback
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from cascade.workspace.drain import begin_drain, draining_event
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.supervisor_status import (
    LastError,
    SupervisorState,
    SupervisorStatus,
    read_supervisor_status,
    utc_now_iso,
    write_supervisor_status,
)
from cascade.workspace.update_preflight import run_update_preflight
from cascade.workspace.up import (
    _SOURCE_CHECK_INTERVAL_SECONDS,
    _source_fingerprint,
    prepare_up,
    repair_registered_worktrees,
    submit_recovered_turns,
)

# Launcher passes these when spawning ``python -m cascade.workspace.worker``.
ENV_LISTEN_FD = "CASCADE_SUPERVISOR_LISTEN_FD"
ENV_READINESS_FD = "CASCADE_SUPERVISOR_READINESS_FD"
ENV_LOCK_TOKEN = "CASCADE_SUPERVISOR_LOCK_TOKEN"
ENV_LOCK_FD = "CASCADE_SUPERVISOR_LOCK_FD"
ENV_LOG_STDERR_FD = "CASCADE_SUPERVISOR_LOG_STDERR_FD"

READINESS_MESSAGE = b"ready\n"
EXIT_UPDATE = 75
CANCEL_GRACE_S = 5.0


@dataclass(frozen=True)
class LauncherHandshake:
    listen_fd: int
    readiness_fd: int
    lock_fd: int
    lock_token: str


def _fail(message: str, *, code: int = 2) -> NoReturn:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def parse_launcher_handshake(
    environ: Mapping[str, str] | None = None,
) -> LauncherHandshake:
    """Return handshake fields or exit non-zero with a clear message."""

    env = environ if environ is not None else os.environ
    missing = [
        name
        for name in (ENV_LISTEN_FD, ENV_READINESS_FD, ENV_LOCK_FD, ENV_LOCK_TOKEN)
        if not env.get(name)
    ]
    if missing:
        _fail(
            "cascade workspace worker requires launcher handshake env "
            f"({', '.join(missing)} missing); start via `cascade up`, not directly"
        )

    token = env[ENV_LOCK_TOKEN].strip()
    if not token:
        _fail(
            f"{ENV_LOCK_TOKEN} is empty; cascade workspace worker must run under the launcher"
        )

    try:
        listen_fd = int(env[ENV_LISTEN_FD])
        readiness_fd = int(env[ENV_READINESS_FD])
        lock_fd = int(env[ENV_LOCK_FD])
    except ValueError:
        _fail(
            f"{ENV_LISTEN_FD}, {ENV_READINESS_FD}, and {ENV_LOCK_FD} must be "
            "integer file descriptors"
        )

    return LauncherHandshake(
        listen_fd=listen_fd,
        readiness_fd=readiness_fd,
        lock_fd=lock_fd,
        lock_token=token,
    )


def _attach_launcher_log_stderr() -> None:
    """Duplicate the launcher's stderr onto fd 2 so logs survive stderr piping."""

    raw = os.environ.get(ENV_LOG_STDERR_FD)
    if not raw:
        return
    try:
        log_fd = int(raw)
    except ValueError:
        return
    try:
        os.dup2(log_fd, 2)
    except OSError:
        return


def _write_readiness(readiness_fd: int) -> None:
    try:
        os.write(readiness_fd, READINESS_MESSAGE)
    except OSError as exc:
        _fail(f"failed to write readiness to launcher pipe: {exc}")


def _worker_supervisor_status(
    workspace_root: Path,
    *,
    state: SupervisorState,
    last_error: LastError | None = None,
    next_action: str | None = None,
) -> SupervisorStatus:
    existing = read_supervisor_status(workspace_root)
    now = utc_now_iso()
    previous_state = existing.get("state") if existing else None
    since = existing["since"] if existing and previous_state == state else now
    return {
        "state": state,
        "worker_pid": os.getpid(),
        "restart_count": int(existing.get("restart_count", 0)) if existing else 0,
        "last_error": last_error,
        "next_action": next_action,
        "trunk_lock_warning": existing.get("trunk_lock_warning") if existing else None,
        "since": since,
        "updated_at": now,
    }


def _publish_worker_supervisor_state(
    workspace_root: Path,
    *,
    state: SupervisorState,
    last_error: LastError | None = None,
    next_action: str | None = None,
) -> None:
    write_supervisor_status(
        workspace_root,
        _worker_supervisor_status(
            workspace_root,
            state=state,
            last_error=last_error,
            next_action=next_action,
        ),
    )


def drain_and_shutdown(
    server,
    server_thread: threading.Thread,
    *,
    root: Path,
    reason: Literal["update", "stop", "crash", "launcher_lost"],
    drain_seconds: float,
    launcher_parent_pid: int | None = None,
) -> bool:
    """Drain HTTP handlers and live turns, then shut down the War Room server."""

    from cascade.agent.turn_registry import cancel_live_turns, wait_until_idle
    from cascade.war_room.server import HTTP_HANDLER_JOIN_TIMEOUT_S, REQUEST_DEADLINE_S

    if reason != "launcher_lost":
        begin_drain()
    snapshot = server.snapshot_handler_threads()
    started = time.monotonic()
    if reason in ("crash", "launcher_lost"):
        turn_window = 0.0
    else:
        turn_window = drain_seconds

    def _launcher_parent_gone() -> bool:
        return (
            launcher_parent_pid is not None and os.getppid() != launcher_parent_pid
        )

    http_abandoned: list[str] = []
    cancelled_turn_count = 0

    def _http_join() -> None:
        http_abandoned.extend(
            server.join_handler_threads(snapshot, timeout=HTTP_HANDLER_JOIN_TIMEOUT_S)
        )

    def _wait_idle_or_parent_gone(timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _launcher_parent_gone():
                return False
            if wait_until_idle(min(0.05, max(0.0, deadline - time.monotonic()))):
                return True
        return wait_until_idle(0.0)

    def _grace_after_agent_sigterm() -> None:
        deadline = time.monotonic() + CANCEL_GRACE_S
        while time.monotonic() < deadline:
            if _launcher_parent_gone():
                return
            wait_until_idle(min(0.05, max(0.0, deadline - time.monotonic())))

    def _turn_drain() -> None:
        nonlocal cancelled_turn_count
        if reason == "launcher_lost" or _launcher_parent_gone():
            cancelled_turn_count = len(cancel_live_turns())
            _grace_after_agent_sigterm()
            return
        if not _wait_idle_or_parent_gone(turn_window):
            cancelled_turn_count = len(cancel_live_turns())
            _wait_idle_or_parent_gone(CANCEL_GRACE_S)

    http_thread = threading.Thread(target=_http_join, name="worker-http-drain", daemon=True)
    turn_thread = threading.Thread(target=_turn_drain, name="worker-turn-drain", daemon=True)
    http_thread.start()
    turn_thread.start()
    http_thread.join()
    turn_thread.join()

    server.shutdown()
    final_abandoned = server.join_handler_threads(
        server.snapshot_handler_threads(),
        timeout=REQUEST_DEADLINE_S,
    )
    http_abandoned.extend(final_abandoned)
    server.server_close()
    server_thread.join(timeout=10)

    snapshot_names = {t.name for t in snapshot}
    abandoned_from_snapshot = {n for n in http_abandoned if n in snapshot_names}
    joined_handlers = len(snapshot) - len(abandoned_from_snapshot)
    elapsed = time.monotonic() - started
    sys.stderr.write(
        f"worker drain ({reason}): elapsed={elapsed:.1f}s "
        f"handlers_joined≈{max(0, joined_handlers)} "
        f"handlers_abandoned={len(http_abandoned)} "
        f"turns_cancelled={cancelled_turn_count}\n"
    )
    sys.stderr.flush()
    return bool(http_abandoned)


def run_worker(*, stop_event: threading.Event | None = None) -> tuple[int, bool]:
    """Run until operator stop (0), source update (75), or crash (other non-zero)."""

    handshake = parse_launcher_handshake()
    _attach_launcher_log_stderr()
    # Inherited ``handshake.lock_fd`` (supervisor lock) stays open until process exit.
    launcher_parent_pid = os.getppid()
    operator_stop = stop_event if stop_event is not None else threading.Event()

    def on_operator_stop(_signum: int, _frame: object | None) -> None:
        operator_stop.set()

    signal.signal(signal.SIGTERM, on_operator_stop)
    signal.signal(signal.SIGINT, on_operator_stop)

    from cascade.war_room.server import serve
    from cascade.watchdog.config import worker_drain_seconds
    from cascade.watchdog.loop import run_watchdog

    ws = prepare_up()
    drain_seconds = worker_drain_seconds(ws.path)
    source_at_start = _source_fingerprint()
    source_changed = False
    blocked_preflight_fingerprint: str | None = None
    next_source_check_at = time.monotonic() + _SOURCE_CHECK_INTERVAL_SECONDS
    shutdown_reason: Literal["update", "stop", "crash", "launcher_lost"] = "stop"
    launcher_lost = False
    abnormal_exit = False
    handlers_abandoned = False

    def should_stop() -> bool:
        nonlocal next_source_check_at, source_changed, shutdown_reason, launcher_lost
        nonlocal blocked_preflight_fingerprint
        if os.getppid() != launcher_parent_pid:
            shutdown_reason = "launcher_lost"
            launcher_lost = True
            return True
        if operator_stop.is_set():
            begin_drain()
            shutdown_reason = "stop"
            return True
        now = time.monotonic()
        if now < next_source_check_at:
            return False
        next_source_check_at = now + _SOURCE_CHECK_INTERVAL_SECONDS
        fingerprint = _source_fingerprint()
        if fingerprint == source_at_start:
            return False
        if fingerprint == blocked_preflight_fingerprint:
            return False
        preflight = run_update_preflight(ws.path)
        if not preflight.ok:
            blocked_preflight_fingerprint = fingerprint
            _publish_worker_supervisor_state(
                ws.path,
                state="update_blocked",
                last_error={
                    "exit_code": preflight.exit_code,
                    "stderr_tail": preflight.stderr_tail or None,
                    "message": preflight.message,
                },
                next_action="Fix the syntax error and save again.",
            )
            return False
        blocked_preflight_fingerprint = None
        _publish_worker_supervisor_state(
            ws.path,
            state="serving",
            last_error=None,
            next_action=None,
        )
        source_changed = True
        begin_drain()
        shutdown_reason = "update"
        return True

    try:
        listen_socket = socket.socket(fileno=handshake.listen_fd)
    except OSError as exc:
        _fail(f"invalid inherited listen fd {handshake.listen_fd}: {exc}")

    server = serve(
        root=ws.path,
        listen_socket=listen_socket,
        draining=draining_event(),
    )
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    from cascade.workspace.supervisor_readiness import (
        observe_http_live,
        observe_startup_phase,
    )

    observe_http_live(live=True)
    _write_readiness(handshake.readiness_fd)
    observe_startup_phase("recovery")
    repair_registered_worktrees(ws.path)

    def _submit_recovery() -> None:
        submit_recovered_turns(ws.path)

    threading.Thread(
        target=_submit_recovery,
        name="worker-recovery",
        daemon=True,
    ).start()
    try:
        run_watchdog(root=ws.path, stop_when=should_stop)
    except BaseException:
        abnormal_exit = True
        if not operator_stop.is_set() and not source_changed:
            shutdown_reason = "crash"
        raise
    finally:
        if abnormal_exit and not operator_stop.is_set() and not source_changed:
            shutdown_reason = "crash"
        elif launcher_lost:
            shutdown_reason = "launcher_lost"
        elif operator_stop.is_set():
            shutdown_reason = "stop"
        elif source_changed:
            shutdown_reason = "update"
        handlers_abandoned = drain_and_shutdown(
            server,
            server_thread,
            root=ws.path,
            reason=shutdown_reason,
            drain_seconds=drain_seconds,
            launcher_parent_pid=launcher_parent_pid,
        )
        if abnormal_exit and handlers_abandoned:
            traceback.print_exc()
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(1)

    if launcher_lost:
        return 1, handlers_abandoned
    if operator_stop.is_set():
        return 0, handlers_abandoned
    if source_changed:
        return EXIT_UPDATE, handlers_abandoned
    return 0, handlers_abandoned


def main() -> None:
    try:
        code, handlers_abandoned = run_worker()
    except WorkspaceError as exc:
        _fail(str(exc))
    except SystemExit:
        raise
    except Exception:
        raise
    else:
        if handlers_abandoned:
            sys.stdout.flush()
            sys.stderr.flush()
            os._exit(code)
        raise SystemExit(code)


if __name__ == "__main__":
    main()
