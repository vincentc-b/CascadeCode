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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, NoReturn

from cascade.workspace.drain import begin_drain, draining_event
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.up import (
    _SOURCE_CHECK_INTERVAL_SECONDS,
    _source_fingerprint,
    prepare_up,
    resume_legally_active_graphs,
)

# Launcher passes these when spawning ``python -m cascade.workspace.worker``.
ENV_LISTEN_FD = "CASCADE_SUPERVISOR_LISTEN_FD"
ENV_READINESS_FD = "CASCADE_SUPERVISOR_READINESS_FD"
ENV_LOCK_TOKEN = "CASCADE_SUPERVISOR_LOCK_TOKEN"

READINESS_MESSAGE = b"ready\n"
EXIT_UPDATE = 75
CANCEL_GRACE_S = 5.0


@dataclass(frozen=True)
class LauncherHandshake:
    listen_fd: int
    readiness_fd: int
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
        for name in (ENV_LISTEN_FD, ENV_READINESS_FD, ENV_LOCK_TOKEN)
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
    except ValueError:
        _fail(
            f"{ENV_LISTEN_FD} and {ENV_READINESS_FD} must be integer file descriptors"
        )

    return LauncherHandshake(
        listen_fd=listen_fd, readiness_fd=readiness_fd, lock_token=token
    )


def _write_readiness(readiness_fd: int) -> None:
    try:
        os.write(readiness_fd, READINESS_MESSAGE)
    except OSError as exc:
        _fail(f"failed to write readiness to launcher pipe: {exc}")


def drain_and_shutdown(
    server,
    server_thread: threading.Thread,
    *,
    root: Path,
    reason: Literal["update", "stop", "crash"],
    drain_seconds: float,
) -> bool:
    """Drain HTTP handlers and live turns, then shut down the War Room server."""

    from cascade.agent.turn_registry import cancel_live_turns, wait_until_idle
    from cascade.war_room.server import HTTP_HANDLER_JOIN_TIMEOUT_S, REQUEST_DEADLINE_S

    begin_drain()
    snapshot = server.snapshot_handler_threads()
    started = time.monotonic()
    turn_window = 0.0 if reason == "crash" else drain_seconds

    http_abandoned: list[str] = []
    cancelled_turn_count = 0

    def _http_join() -> None:
        http_abandoned.extend(
            server.join_handler_threads(snapshot, timeout=HTTP_HANDLER_JOIN_TIMEOUT_S)
        )

    def _turn_drain() -> None:
        nonlocal cancelled_turn_count
        if not wait_until_idle(turn_window):
            cancelled_turn_count = len(cancel_live_turns())
            wait_until_idle(CANCEL_GRACE_S)

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
    next_source_check_at = time.monotonic() + _SOURCE_CHECK_INTERVAL_SECONDS
    shutdown_reason: Literal["update", "stop", "crash"] = "stop"
    abnormal_exit = False
    handlers_abandoned = False

    def should_stop() -> bool:
        nonlocal next_source_check_at, source_changed, shutdown_reason
        if operator_stop.is_set():
            begin_drain()
            shutdown_reason = "stop"
            return True
        now = time.monotonic()
        if now < next_source_check_at:
            return False
        next_source_check_at = now + _SOURCE_CHECK_INTERVAL_SECONDS
        source_changed = _source_fingerprint() != source_at_start
        if source_changed:
            begin_drain()
            shutdown_reason = "update"
        return source_changed

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
    try:
        resume_legally_active_graphs(ws.path)
        _write_readiness(handshake.readiness_fd)
        run_watchdog(root=ws.path, stop_when=should_stop)
    except BaseException:
        abnormal_exit = True
        if not operator_stop.is_set() and not source_changed:
            shutdown_reason = "crash"
        raise
    finally:
        if abnormal_exit and not operator_stop.is_set() and not source_changed:
            shutdown_reason = "crash"
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
        )

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
