"""Best-effort notification of already committed recovery transitions.

Notifications are an optimization: a consumer must replay retained source
receipts after a missed call or process restart.  There is intentionally one
publisher per process so registration order cannot change delivery semantics.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from threading import Lock
from typing import Any

TransitionPublisher = Callable[[Path, Mapping[str, Any], Mapping[str, Any]], None]

_publisher: TransitionPublisher | None = None
_publisher_lock = Lock()


def register_transition_publisher(publisher: TransitionPublisher | None) -> None:
    """Install the process-local deterministic publisher (or clear it in tests)."""

    if publisher is not None and not callable(publisher):
        raise TypeError("transition publisher must be callable")
    global _publisher
    with _publisher_lock:
        _publisher = publisher


def notify_committed_transition(
    root: Path,
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
) -> bool:
    """Notify after commit without changing the source operation's outcome."""

    with _publisher_lock:
        publisher = _publisher
    if publisher is None:
        return False
    # Detach mutable caller state.  Publisher failures and malformed callbacks
    # cannot revoke or reinterpret the commit that already happened.
    committed_receipt = json.loads(json.dumps(dict(receipt)))
    committed_snapshot = json.loads(json.dumps(dict(snapshot)))
    try:
        publisher(root, committed_receipt, committed_snapshot)
    except Exception:
        return False
    return True


__all__ = [
    "TransitionPublisher",
    "notify_committed_transition",
    "register_transition_publisher",
]
