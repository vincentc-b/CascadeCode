"""Live model turns for bounded worker drain and cancellation."""

from __future__ import annotations

import asyncio
import contextvars
import os
import signal
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

CANCEL_GRACE_S = 5.0

_current_turn: contextvars.ContextVar[LiveTurn | None] = contextvars.ContextVar(
    "_current_turn",
    default=None,
)
_live: dict[str, LiveTurn] = {}
_lock = threading.Lock()


@dataclass
class LiveTurn:
    turn_id: str
    role: str
    loop: asyncio.AbstractEventLoop
    task: asyncio.Task[Any]
    pid: int | None = None
    cancelled: bool = False


@contextmanager
def register_turn(role: str) -> Iterator[LiveTurn]:
    """Register the current asyncio task as a live turn (enter inside ``run_role``)."""

    loop = asyncio.get_running_loop()
    task = asyncio.current_task()
    if task is None:
        raise RuntimeError("register_turn requires a running asyncio task")

    live = LiveTurn(
        turn_id=uuid.uuid4().hex,
        role=role,
        loop=loop,
        task=task,
    )
    token = _current_turn.set(live)
    with _lock:
        _live[live.turn_id] = live
    try:
        yield live
    finally:
        with _lock:
            _live.pop(live.turn_id, None)
        _current_turn.reset(token)


def set_current_turn_pid(pid: int) -> None:
    live = _current_turn.get()
    if live is None:
        return
    live.pid = pid


def get_live_turn(turn_id: str) -> LiveTurn | None:
    with _lock:
        return _live.get(turn_id)


def live_turns() -> list[LiveTurn]:
    with _lock:
        return list(_live.values())


def wait_until_idle(timeout: float) -> bool:
    """Return True when no live turns remain within ``timeout`` seconds."""

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with _lock:
            if not _live:
                return True
        time.sleep(0.05)
    with _lock:
        return not _live


def _request_cancel_turn(turn: LiveTurn) -> None:
    turn.cancelled = True
    if turn.pid is not None:
        try:
            os.kill(turn.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    turn.loop.call_soon_threadsafe(turn.task.cancel)


def cancel_live_turn(
    turn_id: str,
    *,
    grace_seconds: float = CANCEL_GRACE_S,
    escalate_to_sigkill: bool = False,
) -> tuple[LiveTurn | None, bool]:
    """Cancel one registered turn by id (SIGTERM; optional bounded SIGKILL).

    Returns ``(turn, force_kill_applied)``. Unknown ids return ``(None, False)``.
    """

    with _lock:
        turn = _live.get(turn_id)
    if turn is None:
        return None, False

    pid = turn.pid
    _request_cancel_turn(turn)
    force_kill = False
    if pid is not None and escalate_to_sigkill and grace_seconds > 0:
        deadline = time.monotonic() + grace_seconds
        while time.monotonic() < deadline:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pid = None
                break
            time.sleep(0.05)
        if pid is not None:
            try:
                os.kill(pid, signal.SIGKILL)
                force_kill = True
            except ProcessLookupError:
                pass
    return turn, force_kill


def cancel_live_turns() -> list[LiveTurn]:
    turns = live_turns()
    for turn in turns:
        _request_cancel_turn(turn)
    return turns
