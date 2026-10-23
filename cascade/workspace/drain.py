"""Process-local worker drain flag (shared by HTTP, kickoff, and shutdown)."""

from __future__ import annotations

import threading

_draining = threading.Event()


def begin_drain() -> None:
    """Mark the worker as draining (idempotent)."""

    _draining.set()


def is_draining() -> bool:
    return _draining.is_set()


def draining_event() -> threading.Event:
    """Event passed to ``serve(draining=...)``."""

    return _draining


def reset_drain_for_tests() -> None:
    _draining.clear()
