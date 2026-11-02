"""In-process admission and quiescence gate for Epic lifecycle transitions.

The durable transition owns persistence; this module owns the volatile boundary
that makes a durable transition safe to start.  A gate first refuses new turns
for the supplied graph, waits for already admitted turns to leave, and keeps
that refusal in place until the caller has completed its locked recheck and
transition step.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager


class LifecycleTurnRejected(RuntimeError):
    """A turn attempted to enter a graph which is quiescing."""


class LifecycleGate:
    """Serialize one Epic transition and prevent its graph from starting turns.

    This is intentionally process-local.  The transition journal added by the
    following slice supplies durable recovery; a process-local admission gate
    is the appropriate boundary for the live scheduler that owns model turns.
    """

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._epic_locks: dict[str, threading.Lock] = {}
        self._blocked_by_member: dict[str, str] = {}
        self._active_by_member: dict[str, int] = {}

    @contextmanager
    def turn(self, member_id: str) -> Iterator[None]:
        """Admit one turn, or reject it before it can cross a transition boundary."""

        with self._condition:
            if member_id in self._blocked_by_member:
                raise LifecycleTurnRejected(
                    f"lifecycle transition is quiescing {self._blocked_by_member[member_id]}"
                )
            self._active_by_member[member_id] = self._active_by_member.get(member_id, 0) + 1
        try:
            yield
        finally:
            with self._condition:
                remaining = self._active_by_member[member_id] - 1
                if remaining:
                    self._active_by_member[member_id] = remaining
                else:
                    self._active_by_member.pop(member_id, None)
                self._condition.notify_all()

    @contextmanager
    def transition(
        self, epic_id: str, member_ids: tuple[str, ...], *, timeout: float = 0.0
    ) -> Iterator[bool]:
        """Close graph admission and yield whether all admitted turns drained.

        The per-Epic lock covers quiescence through the caller's locked
        eligibility recheck and transition callback.  On timeout, admission is
        reopened and ``False`` is yielded, so callers can return a normal
        fail-closed eligibility refusal without durable mutation.
        """

        members = tuple(dict.fromkeys(member_ids))
        if not epic_id or not members or epic_id not in members:
            yield False
            return
        lock = self._lock_for(epic_id)
        with lock:
            if not self._close_admission(epic_id, members):
                yield False
                return
            quiesced = self._wait_for_quiescence(members, timeout)
            if not quiesced:
                self._open_admission(epic_id, members)
                yield False
                return
            try:
                yield True
            finally:
                self._open_admission(epic_id, members)

    def _lock_for(self, epic_id: str) -> threading.Lock:
        with self._condition:
            lock = self._epic_locks.get(epic_id)
            if lock is None:
                lock = threading.Lock()
                self._epic_locks[epic_id] = lock
            return lock

    def _close_admission(self, epic_id: str, members: tuple[str, ...]) -> bool:
        with self._condition:
            # A different Epic must not silently steal a member's admission
            # boundary.  The caller treats this as an unsafe, non-mutating
            # refusal and obtains a fresh graph snapshot on retry.
            if any(
                (owner := self._blocked_by_member.get(member)) is not None and owner != epic_id
                for member in members
            ):
                return False
            for member in members:
                self._blocked_by_member[member] = epic_id
            return True

    def _wait_for_quiescence(self, members: tuple[str, ...], timeout: float) -> bool:
        deadline = time.monotonic() + max(timeout, 0.0)
        with self._condition:
            while any(self._active_by_member.get(member, 0) for member in members):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._condition.wait(remaining)
            return True

    def _open_admission(self, epic_id: str, members: tuple[str, ...]) -> None:
        with self._condition:
            for member in members:
                if self._blocked_by_member.get(member) == epic_id:
                    self._blocked_by_member.pop(member, None)
            self._condition.notify_all()


_default_gate = LifecycleGate()


def lifecycle_gate() -> LifecycleGate:
    """Return the scheduler and return-command shared lifecycle gate."""

    return _default_gate
