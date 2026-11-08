"""Restart-safe scheduling for supervisor-owned health-audit passes.

The lane owns only timing, cross-process exclusion, and its compact runtime
receipt.  Candidate observation and recovery are supplied by the pass callback
so they can evolve without coupling audit progress to the ordinary watchdog.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import random
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cascade.board.context import get_project_context, resolve_root
from cascade.watchdog.config import HealthAuditConfig

_log = logging.getLogger(__name__)

_RUNTIME_DIR = "health_audit"
_RECEIPT_NAME = "receipt.json"
_CLAIM_NAME = "pass.lock"
_BUSY_RETRY_SECONDS = 1.0


@dataclass(frozen=True)
class AuditPassResult:
    """The small amount of completed-pass state retained by the scheduler."""

    next_cursor: str | None = None
    counts: Mapping[str, int] = field(default_factory=dict)


AuditPass = Callable[[str | None, threading.Event], AuditPassResult]


def canonical_audit_root(root: Path) -> Path:
    """Return the product workspace identity, never one of its child worktrees."""

    requested = resolve_root(root)
    project = get_project_context()
    if project is None:
        return requested
    product = project.target.root.resolve()
    tracking = project.tracking.root.resolve()
    if requested in {product, tracking} or requested.is_relative_to(
        product / ".cascade" / "worktrees"
    ):
        return product
    return requested


def audit_receipt_path(root: Path) -> Path:
    return canonical_audit_root(root) / ".cascade" / _RUNTIME_DIR / _RECEIPT_NAME


def read_audit_receipt(root: Path) -> dict[str, Any] | None:
    """Read a completed-pass receipt; malformed or partial files are ignored."""

    path = audit_receipt_path(root)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


class _WorkspaceClaim:
    def __init__(self, root: Path) -> None:
        self.path = canonical_audit_root(root) / ".cascade" / _RUNTIME_DIR / _CLAIM_NAME
        self._handle = None

    def acquire(self) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+", encoding="utf-8")
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            handle.close()
            return False
        self._handle = handle
        return True

    def release(self) -> None:
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> _WorkspaceClaim:
        if not self.acquire():
            raise BlockingIOError
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class HealthAuditLane:
    """Independent monotonic scheduler for one canonical product workspace."""

    def __init__(
        self,
        *,
        root: Path,
        config: HealthAuditConfig,
        run_pass: AuditPass,
        stop_event: threading.Event | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] | None = None,
        jitter: Callable[[float, float], float] | None = None,
    ) -> None:
        self.root = canonical_audit_root(root)
        self.config = config
        self._run_pass = run_pass
        self._stop = stop_event or threading.Event()
        self._monotonic = monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._jitter = jitter or random.SystemRandom().uniform
        self._thread: threading.Thread | None = None
        receipt = read_audit_receipt(self.root)
        self._receipt_marker = self._marker(receipt)
        self._deadline = self._restore_deadline(receipt)

    @property
    def deadline(self) -> float:
        return self._deadline

    def start(self) -> HealthAuditLane:
        """Start periodic work when enabled; disabled lanes allocate no thread."""

        if not self.config.enabled or self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._run,
            name="supervisor-health-audit",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def run_due_pass(self) -> bool:
        """Attempt one due pass, returning true only after its receipt is durable."""

        if not self.config.enabled or self._monotonic() < self._deadline:
            return False
        claim = _WorkspaceClaim(self.root)
        if not claim.acquire():
            # Keep the overdue request pending while avoiding a hot claim loop.
            self._deadline = self._monotonic() + min(
                _BUSY_RETRY_SECONDS, float(self.config.interval_seconds)
            )
            return False
        try:
            if self._stop.is_set():
                return False
            previous = read_audit_receipt(self.root)
            marker = self._marker(previous)
            if previous is not None and marker != self._receipt_marker:
                # Another process completed the overdue period while this lane
                # was waiting for the claim.  Adopt its schedule rather than
                # immediately running a duplicate pass.
                self._receipt_marker = marker
                self._deadline = self._restore_deadline(previous)
                return False
            previous = previous or {}
            cursor = previous.get("next_cursor")
            if not isinstance(cursor, str):
                cursor = None
            started_mono = self._monotonic()
            result = self._run_pass(cursor, self._stop)
            if self._stop.is_set():
                return False
            finished_mono = self._monotonic()
            finished_utc = self._aware_utc_now()
            delay = self._next_delay()
            self._deadline = finished_mono + delay
            receipt = {
                "last_completed_at": finished_utc.isoformat(),
                "next_scheduled_at": (
                    finished_utc + timedelta(seconds=delay)
                ).isoformat(),
                "interval_seconds": self.config.interval_seconds,
                "duration_seconds": max(0.0, finished_mono - started_mono),
                "counts": self._validated_counts(result.counts),
                "next_cursor": result.next_cursor,
            }
            _write_receipt(self.root, receipt)
            self._receipt_marker = self._marker(receipt)
            return True
        finally:
            claim.release()

    def _run(self) -> None:
        while not self._stop.is_set():
            wait = max(0.0, self._deadline - self._monotonic())
            if self._stop.wait(wait):
                return
            try:
                self.run_due_pass()
            except Exception:
                # A failed pass is not completed and never advances the receipt.
                # Keep unrelated delivery alive and retry after a bounded pause.
                _log.exception("supervisor health-audit pass failed")
                self._deadline = self._monotonic() + min(
                    _BUSY_RETRY_SECONDS, float(self.config.interval_seconds)
                )

    def _restore_deadline(self, receipt: Mapping[str, Any] | None) -> float:
        now_mono = self._monotonic()
        if receipt is None:
            return now_mono
        try:
            next_utc = datetime.fromisoformat(str(receipt["next_scheduled_at"]))
            if next_utc.tzinfo is None:
                raise ValueError("naive receipt timestamp")
            remaining = (next_utc - self._aware_utc_now()).total_seconds()
        except (KeyError, TypeError, ValueError):
            return now_mono
        # Wall time is consulted once at startup.  All later scheduling uses the
        # monotonic clock, so clock jumps cannot create storms or postponement.
        clamped = min(float(self.config.interval_seconds), max(0.0, remaining))
        return now_mono + clamped

    @staticmethod
    def _marker(receipt: Mapping[str, Any] | None) -> str | None:
        if receipt is None:
            return None
        return repr(
            (
                receipt.get("last_completed_at"),
                receipt.get("next_scheduled_at"),
                receipt.get("next_cursor"),
            )
        )

    def _next_delay(self) -> float:
        cap = min(float(self.config.interval_seconds) * 0.05, 60.0)
        sampled = self._jitter(0.0, cap)
        bounded = min(cap, max(0.0, float(sampled)))
        return float(self.config.interval_seconds) + bounded

    def _aware_utc_now(self) -> datetime:
        value = self._utc_now()
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @staticmethod
    def _validated_counts(counts: Mapping[str, int]) -> dict[str, int]:
        result: dict[str, int] = {}
        for name, value in counts.items():
            if (
                not isinstance(name, str)
                or isinstance(value, bool)
                or not isinstance(value, int)
            ):
                raise ValueError("audit counts must map string names to integers")
            if value < 0:
                raise ValueError("audit counts cannot be negative")
            result[name] = value
        return result


def _write_receipt(root: Path, receipt: Mapping[str, object]) -> None:
    path = audit_receipt_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(receipt, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


__all__ = [
    "AuditPass",
    "AuditPassResult",
    "HealthAuditLane",
    "audit_receipt_path",
    "canonical_audit_root",
    "read_audit_receipt",
]
