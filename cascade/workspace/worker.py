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
from typing import NoReturn

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

_worker_draining: threading.Event | None = None


def worker_draining_event() -> threading.Event:
    """Return the active worker's draining event (set when shutdown begins)."""

    if _worker_draining is None:
        raise WorkspaceError(
            "worker draining event is unavailable outside an active run_worker"
        )
    return _worker_draining


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


def run_worker(*, stop_event: threading.Event | None = None) -> int:
    """Run until operator stop (0), source update (75), or crash (other non-zero)."""

    global _worker_draining

    handshake = parse_launcher_handshake()
    operator_stop = stop_event if stop_event is not None else threading.Event()
    draining = threading.Event()
    _worker_draining = draining

    def on_operator_stop(_signum: int, _frame: object | None) -> None:
        operator_stop.set()

    signal.signal(signal.SIGTERM, on_operator_stop)
    signal.signal(signal.SIGINT, on_operator_stop)

    from cascade.war_room.server import join_http_handlers, serve
    from cascade.watchdog.loop import run_watchdog

    ws = prepare_up()
    source_at_start = _source_fingerprint()
    source_changed = False
    next_source_check_at = time.monotonic() + _SOURCE_CHECK_INTERVAL_SECONDS

    def should_stop() -> bool:
        nonlocal next_source_check_at, source_changed
        if operator_stop.is_set():
            draining.set()
            return True
        now = time.monotonic()
        if now < next_source_check_at:
            return False
        next_source_check_at = now + _SOURCE_CHECK_INTERVAL_SECONDS
        source_changed = _source_fingerprint() != source_at_start
        if source_changed:
            draining.set()
        return source_changed

    try:
        listen_socket = socket.socket(fileno=handshake.listen_fd)
    except OSError as exc:
        _fail(f"invalid inherited listen fd {handshake.listen_fd}: {exc}")

    server = serve(root=ws.path, listen_socket=listen_socket, draining=draining)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    try:
        resume_legally_active_graphs(ws.path)
        _write_readiness(handshake.readiness_fd)
        run_watchdog(root=ws.path, stop_when=should_stop)
    finally:
        draining.set()
        server.shutdown()
        join_http_handlers(server)
        server.server_close()
        server_thread.join(timeout=10)
        _worker_draining = None

    if operator_stop.is_set():
        return 0
    if source_changed:
        return EXIT_UPDATE
    return 0


def main() -> None:
    try:
        code = run_worker()
    except WorkspaceError as exc:
        _fail(str(exc))
    except SystemExit:
        raise
    except Exception:
        raise
    else:
        raise SystemExit(code)


if __name__ == "__main__":
    main()
