"""Restart-safe scheduling for supervisor-owned health-audit passes.

The lane owns only timing, cross-process exclusion, and its compact runtime
receipt.  Candidate observation and recovery are supplied by the pass callback
so they can evolve without coupling audit progress to the ordinary watchdog.
"""

from __future__ import annotations

import fcntl
import json
import logging
import multiprocessing
import os
import random
import signal
import stat
import subprocess
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cascade.agent.mcp_project_context import (
    project_context_payload,
    restore_project_context,
)
from cascade.board.context import get_project_context, resolve_root
from cascade.board.gitutil import inherited_git_process_group
from cascade.watchdog.audit import (
    CandidateBudget,
    _restore_parent_observation_episodes,
    _snapshot_parent_observation_episodes,
    project_audit_observation,
    select_audit_candidates,
)
from cascade.watchdog.config import HealthAuditConfig

_log = logging.getLogger(__name__)

_RUNTIME_DIR = "health_audit"
_RECEIPT_NAME = "receipt.json"
_FAILURE_NAME = "failure.json"
_CLAIM_NAME = "pass.lock"
_BUSY_RETRY_SECONDS = 1.0
_PASS_MAX_ITEMS = 100
_PASS_MAX_SECONDS = 60.0
_OBSERVER_CANCEL_GRACE_SECONDS = 0.25
_OBSERVER_COORDINATION_RESERVE_SECONDS = 0.8


class _LaneStop(threading.Event):
    """Combine an external shutdown request with lane-owned cancellation."""

    def __init__(self, external: threading.Event | None) -> None:
        super().__init__()
        self._external = external

    def is_set(self) -> bool:
        return super().is_set() or (
            self._external is not None and self._external.is_set()
        )

    def wait(self, timeout: float | None = None) -> bool:
        deadline = None if timeout is None else time.monotonic() + timeout
        while not self.is_set():
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            super().wait(min(0.05, remaining) if remaining is not None else 0.05)
        return True


@dataclass(frozen=True)
class AuditPassResult:
    """The small amount of completed-pass state retained by the scheduler."""

    next_cursor: str | None = None
    counts: Mapping[str, int] = field(default_factory=dict)
    incident_work_ids: tuple[str, ...] = ()
    timed_out_candidates: tuple[str, ...] = ()
    reassessed_candidates: tuple[str, ...] = ()


AuditPass = Callable[[str | None, threading.Event], AuditPassResult]
AuditHandoff = Callable[[tuple[str, ...]], None]


class AuditPassTimedOut(TimeoutError):
    """The shared observer/coordinator budget expired before page completion."""


class AuditPassCancelled(RuntimeError):
    """Supervisor shutdown cancelled an in-flight pass."""


def canonical_audit_root(root: Path) -> Path:
    """Return the product workspace identity, never one of its child worktrees."""

    requested = resolve_root(root)
    project = get_project_context()
    if project is not None:
        product = project.target.root.resolve()
        tracking = project.tracking.root.resolve()
        for repository in {product, tracking}:
            if (
                requested == repository
                or _owned_worktree_trunk(requested) == repository
            ):
                return product
    trunk = _owned_worktree_trunk(requested)
    if trunk is not None:
        return trunk
    return requested


def _owned_worktree_trunk(path: Path) -> Path | None:
    """Find the owning checkout from Cascade's fixed worktree layout."""

    worktrees = path.parent
    if worktrees.name != "worktrees" or worktrees.parent.name != ".cascade":
        return None
    if not path.name.startswith(("epic_", "feat_", "task_")):
        return None
    return worktrees.parent.parent


def audit_receipt_path(root: Path) -> Path:
    return canonical_audit_root(root) / ".cascade" / _RUNTIME_DIR / _RECEIPT_NAME


def audit_failure_path(root: Path) -> Path:
    return canonical_audit_root(root) / ".cascade" / _RUNTIME_DIR / _FAILURE_NAME


def read_audit_receipt(root: Path) -> dict[str, Any] | None:
    """Read a completed-pass receipt; malformed or partial files are ignored."""

    content = _read_runtime_json(audit_receipt_path(root))
    if content is None:
        return None
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def read_audit_failure(root: Path) -> dict[str, Any] | None:
    """Read the active pass failure evidence, if any."""

    content = _read_runtime_json(audit_failure_path(root))
    if content is None:
        return None
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_runtime_json(path: Path) -> bytes | None:
    """Read only a small regular runtime file without opening a FIFO reader."""

    try:
        descriptor = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
    except FileNotFoundError:
        return None
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode):
            raise OSError(f"audit runtime state is not a regular file: {path}")
        if info.st_size > 65536:
            raise OSError(f"audit runtime state is too large: {path}")
        content = os.read(descriptor, 65537)
        if len(content) > 65536:
            raise OSError(f"audit runtime state is too large: {path}")
        return content
    finally:
        os.close(descriptor)


def _pending_timeout_ids(failure: Mapping[str, Any] | None) -> set[str]:
    if failure is None:
        return set()
    value = failure.get("pending_timeout_work_ids")
    if value is None and failure.get("code") == "candidate_observation_timeout":
        value = failure.get("work_ids")  # Read older failure files.
    if not isinstance(value, list):
        return set()
    return {work_id for work_id in value if isinstance(work_id, str)}


def run_bounded_audit_pass(
    root: Path,
    cursor: str | None,
    cancel_event: threading.Event,
    *,
    max_items: int = _PASS_MAX_ITEMS,
    max_seconds: float = _PASS_MAX_SECONDS,
    monotonic: Callable[[], float] = time.monotonic,
) -> AuditPassResult:
    """Select and observe one fair page under one shared finite budget.

    The process boundary makes the coordinator return on deadline even if a
    local filesystem read cannot be interrupted by Python.  Cooperative
    cancellation first gives bounded Git calls a chance to reap their process
    groups; an unresponsive observer is then terminated and joined before the
    caller can release the workspace claim.
    """

    max_items = min(max_items, _PASS_MAX_ITEMS)
    max_seconds = min(max_seconds, _PASS_MAX_SECONDS)
    real_deadline = time.monotonic() + max_seconds
    # ``spawn`` cannot inherit locks held by another supervisor thread.  In
    # particular, ordinary watchdog maintenance may be blocked while this
    # independent lane still needs to inspect the workspace.
    context = multiprocessing.get_context("spawn")
    operation_cancel = context.Event()
    receiver, sender = context.Pipe(duplex=False)
    coordination_reserve = min(
        _OBSERVER_COORDINATION_RESERVE_SECONDS, max_seconds * 0.5
    )
    cleanup_grace = max(0.001, coordination_reserve / 3.0)
    observer_deadline = real_deadline - coordination_reserve
    worker = context.Process(
        target=_audit_observer_process,
        args=(
            sender,
            root,
            cursor,
            operation_cancel,
            max_items,
            observer_deadline,
            project_context_payload(),
            _snapshot_parent_observation_episodes(),
        ),
        name="health-audit-pass",
        daemon=True,
    )
    worker.start()
    sender.close()
    try:
        while True:
            if cancel_event.is_set():
                _reap_audit_observer(worker, operation_cancel, grace=cleanup_grace)
                raise AuditPassCancelled("health audit cancelled during pass")
            remaining = real_deadline - time.monotonic()
            if remaining <= 0:
                _reap_audit_observer(worker, operation_cancel, grace=cleanup_grace)
                raise AuditPassTimedOut(
                    f"health audit exceeded {max_seconds:g}s during pass"
                )
            if receiver.poll(min(0.05, remaining)):
                try:
                    succeeded, result = receiver.recv()
                except EOFError as exc:
                    _reap_audit_observer(worker, operation_cancel, grace=cleanup_grace)
                    raise RuntimeError(
                        "health audit observer exited without a result"
                    ) from exc
                _reap_audit_observer(
                    worker,
                    operation_cancel,
                    cancel_first=False,
                    grace=cleanup_grace,
                )
                if succeeded:
                    completed, episodes = result
                    _restore_parent_observation_episodes(episodes)
                    return completed
                raise result
            if not worker.is_alive():
                _reap_audit_observer(
                    worker,
                    operation_cancel,
                    cancel_first=False,
                    grace=cleanup_grace,
                )
                if receiver.poll(0):
                    try:
                        succeeded, result = receiver.recv()
                    except EOFError as exc:
                        raise RuntimeError(
                            "health audit observer exited without a result"
                        ) from exc
                    if succeeded:
                        completed, episodes = result
                        _restore_parent_observation_episodes(episodes)
                        return completed
                    raise result
                raise RuntimeError("health audit observer exited without a result")
    finally:
        receiver.close()


def _audit_observer_process(
    sender: Any,
    root: Path,
    cursor: str | None,
    cancel_event: Any,
    max_items: int,
    deadline: float,
    context_payload: object,
    parent_observation_episodes: tuple[
        tuple[str, str, str, str, float, int], ...
    ],
) -> None:
    """Run observer work in a process that the claim owner can always reap."""

    try:
        # The observer owns a process group containing every Git/helper child.
        # The coordinator can therefore remove the complete tree before
        # releasing the workspace claim, even if this process is unresponsive.
        os.setsid()
        restore_project_context(context_payload)
        _restore_parent_observation_episodes(parent_observation_episodes)
        with inherited_git_process_group():
            result: AuditPassResult | BaseException = _run_bounded_audit_pass_inline(
                root,
                cursor,
                cancel_event,
                max_items=max_items,
                max_seconds=max(0.0, deadline - time.monotonic()),
                monotonic=time.monotonic,
            )
        payload = (True, (result, _snapshot_parent_observation_episodes()))
    except BaseException as exc:
        payload = (False, exc)
    try:
        sender.send(payload)
    except Exception:
        # The coordinator may already have timed out and closed its endpoint.
        pass
    finally:
        sender.close()


def _reap_audit_observer(
    worker: multiprocessing.Process,
    cancel_event: Any,
    *,
    cancel_first: bool = True,
    grace: float = _OBSERVER_CANCEL_GRACE_SECONDS,
) -> None:
    """Cooperatively cancel, then forcibly terminate and join the observer."""

    if cancel_first:
        cancel_event.set()
    worker.join(timeout=grace)
    if worker.is_alive():
        _signal_observer_group(worker, signal.SIGTERM)
        worker.join(timeout=grace)
    if worker.is_alive():
        _signal_observer_group(worker, signal.SIGKILL)
        worker.join(timeout=grace)
    if worker.is_alive():
        raise RuntimeError("health audit observer could not be reaped")
    # The observer can exit while a helper that inherited its pipes/group is
    # still alive.  Kill the owned group after joining before the claim drops.
    _signal_observer_group(worker, signal.SIGKILL)


def _signal_observer_group(
    worker: multiprocessing.Process, sig: signal.Signals
) -> None:
    pid = worker.pid
    if pid is None:
        return
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        if worker.is_alive():
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                pass


def _run_bounded_audit_pass_inline(
    root: Path,
    cursor: str | None,
    cancel_event: threading.Event,
    *,
    max_items: int,
    max_seconds: float,
    monotonic: Callable[[], float],
) -> AuditPassResult:
    """Run inside the finite coordinator boundary."""

    started = monotonic()

    def remaining(phase: str) -> float:
        if cancel_event.is_set():
            raise AuditPassCancelled(f"health audit cancelled during {phase}")
        value = max_seconds - (monotonic() - started)
        if value <= 0:
            raise AuditPassTimedOut(
                f"health audit exceeded {max_seconds:g}s during {phase}"
            )
        return value

    page = select_audit_candidates(
        cursor,
        CandidateBudget(max_items=max_items, max_seconds=remaining("selection")),
        root=root,
        monotonic=monotonic,
        cancel_event=cancel_event,
    )
    remaining("selection")
    counts: dict[str, int] = {
        "selected": len(page.candidates),
        "observed": 0,
        "healthy": 0,
        "expected_wait": 0,
        "proven_incident": 0,
        "unavailable_evidence": len(page.unavailable_evidence),
    }
    for tier in ("task", "feature", "epic"):
        for outcome in (
            "healthy",
            "expected_wait",
            "proven_incident",
            "unavailable_evidence",
        ):
            counts[f"tier.{tier}.{outcome}"] = 0
    incident_work_ids: list[str] = []
    completed_cursor = cursor
    timed_out_candidates: list[str] = []
    reassessed_candidates: list[str] = []

    def completed(next_cursor: str | None) -> AuditPassResult:
        return AuditPassResult(
            next_cursor=next_cursor,
            counts=counts,
            incident_work_ids=tuple(incident_work_ids),
            timed_out_candidates=tuple(timed_out_candidates),
            reassessed_candidates=tuple(reassessed_candidates),
        )

    for index, candidate in enumerate(page.candidates):
        work_id = str(candidate.work_id)
        tier = str(getattr(candidate, "tier", work_id.split("_", 1)[0]))
        continuations = getattr(page, "continuation_cursors", ())
        candidate_cursor = (
            continuations[index] if index < len(continuations) else page.next_cursor
        )
        if not candidate.evidence_available:
            # Selection already proved this identity cannot currently be
            # projected.  Count it as unavailable evidence and advance the
            # exact selector cursor so one malformed reference cannot pin the
            # page ahead of later healthy candidates.
            counts["observed"] += 1
            counts["unavailable_evidence"] += 1
            if tier in {"task", "feature", "epic"}:
                counts[f"tier.{tier}.unavailable_evidence"] += 1
            completed_cursor = candidate_cursor
            if monotonic() - started >= max_seconds:
                return completed(completed_cursor)
            continue
        allowance = remaining(f"observation:{work_id}")
        try:
            observation = project_audit_observation(
                work_id,
                root=root,
                timeout_seconds=allowance,
                cancel_event=cancel_event,
                monotonic=monotonic,
            )
        except InterruptedError as exc:
            raise AuditPassCancelled(
                f"health audit cancelled while observing {work_id}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            # A single slow candidate must not pin the cursor forever.  It is
            # unavailable, never healthy or observed, and the selector's
            # opaque continuation will revisit it on a later rotation.
            counts["unavailable_evidence"] += 1
            if tier in {"task", "feature", "epic"}:
                counts[f"tier.{tier}.unavailable_evidence"] += 1
            timed_out_candidates.append(work_id)
            completed_cursor = candidate_cursor
            _log.warning("health audit observation timed out for %s: %s", work_id, exc)
            if monotonic() - started >= max_seconds:
                return completed(completed_cursor)
            continue
        counts["observed"] += 1
        counts[observation.classification] += 1
        if tier in {"task", "feature", "epic"}:
            counts[f"tier.{tier}.{observation.classification}"] += 1
        if observation.classification == "proven_incident":
            incident_work_ids.append(work_id)
        if observation.classification != "unavailable_evidence":
            reassessed_candidates.append(work_id)
        completed_cursor = candidate_cursor

        if cancel_event.is_set():
            raise AuditPassCancelled(
                f"health audit cancelled during observation:{work_id}"
            )
        if monotonic() - started >= max_seconds:
            # The observation completed successfully. Persist its exact selector
            # continuation and leave the unobserved suffix for the next pass.
            return completed(completed_cursor)
    return completed(page.next_cursor)


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
        handoff: AuditHandoff | None = None,
        stop_event: threading.Event | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        utc_now: Callable[[], datetime] | None = None,
        jitter: Callable[[float, float], float] | None = None,
    ) -> None:
        self.root = canonical_audit_root(root)
        self.config = config
        self._run_pass = run_pass
        self._handoff = handoff
        self._stop = _LaneStop(stop_event)
        self._monotonic = monotonic
        self._utc_now = utc_now or (lambda: datetime.now(timezone.utc))
        self._jitter = jitter or random.SystemRandom().uniform
        self._thread: threading.Thread | None = None
        self._state_lock = threading.Lock()
        self._wake = threading.Event()
        self._manual_pending = False
        self._manual_retry_deadline: float | None = None
        self._in_flight = False
        receipt = read_audit_receipt(self.root)
        self._receipt_marker = self._marker(receipt)
        self._deadline = self._restore_deadline(receipt)

    @property
    def deadline(self) -> float:
        return self._deadline

    def start(self) -> HealthAuditLane:
        """Start periodic work when enabled; disabled lanes allocate no thread."""

        if not self.config.enabled:
            return self
        self._ensure_thread()
        return self

    def request_manual_pass(self) -> bool | None:
        """Admit one explicit pass, coalescing duplicates and active passes.

        Manual admission is independent of periodic enablement.  It only wakes
        this lane and never rewrites the monotonic periodic deadline.
        """

        with self._state_lock:
            if self._stop.is_set():
                return None
            if self._manual_pending or self._in_flight:
                return False
            self._manual_pending = True
            self._manual_retry_deadline = None
            self._ensure_thread_locked()
        self._wake.set()
        return True

    def stop(self, timeout: float | None = None) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout)

    def run_due_pass(self) -> bool:
        """Attempt one due pass, returning true only after its receipt is durable."""

        if not self.config.enabled or self._monotonic() < self._deadline:
            return False
        return self._run_pass_once(manual=False)

    def _run_pass_once(self, *, manual: bool) -> bool:
        periodic_deadline = self._deadline
        claim = _WorkspaceClaim(self.root)
        if not claim.acquire():
            # Keep the overdue request pending while avoiding a hot claim loop.
            if not manual:
                self._deadline = self._monotonic() + min(
                    _BUSY_RETRY_SECONDS, float(self.config.interval_seconds)
                )
            return False
        completed: AuditPassResult | None = None
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
            pending_timeouts = _pending_timeout_ids(read_audit_failure(self.root))
            cursor = previous.get("next_cursor")
            if not isinstance(cursor, str):
                cursor = None
            started_mono = self._monotonic()
            try:
                result = self._run_pass(cursor, self._stop)
            except AuditPassCancelled:
                return False
            except Exception as exc:
                if not manual:
                    self._deadline = self._monotonic() + min(
                        _BUSY_RETRY_SECONDS, float(self.config.interval_seconds)
                    )
                _write_failure(
                    self.root,
                    {
                        "failed_at": self._aware_utc_now().isoformat(),
                        "code": type(exc).__name__,
                        "message": str(exc) or type(exc).__name__,
                        "next_action": (
                            "Inspect the audit failure and its candidate cursor; "
                            "the supervisor will retry without advancing it."
                        ),
                        "retry_seconds": min(
                            _BUSY_RETRY_SECONDS,
                            float(self.config.interval_seconds),
                        ),
                        "cursor": cursor,
                        "pending_timeout_work_ids": sorted(pending_timeouts),
                    },
                )
                raise
            if self._stop.is_set():
                return False
            finished_mono = self._monotonic()
            finished_utc = self._aware_utc_now()
            if manual:
                self._deadline = periodic_deadline
                next_scheduled = finished_utc + timedelta(
                    seconds=max(0.0, periodic_deadline - finished_mono)
                )
            else:
                delay = self._next_delay()
                self._deadline = finished_mono + delay
                next_scheduled = finished_utc + timedelta(seconds=delay)
            receipt = {
                "last_completed_at": finished_utc.isoformat(),
                "next_scheduled_at": next_scheduled.isoformat(),
                "interval_seconds": self.config.interval_seconds,
                "duration_seconds": max(0.0, finished_mono - started_mono),
                "counts": self._validated_counts(result.counts),
                "next_cursor": result.next_cursor,
            }
            _write_receipt(self.root, receipt)
            pending_timeouts.difference_update(result.reassessed_candidates)
            pending_timeouts.update(result.timed_out_candidates)
            if pending_timeouts:
                _write_failure(
                    self.root,
                    {
                        "failed_at": finished_utc.isoformat(),
                        "code": "candidate_observation_timeout",
                        "work_ids": sorted(pending_timeouts),
                        "pending_timeout_work_ids": sorted(pending_timeouts),
                        "next_action": (
                            "Inspect the timed-out candidate I/O; the next cursor "
                            "rotation will retry these unavailable work items."
                        ),
                        "cursor": result.next_cursor,
                    },
                )
            else:
                audit_failure_path(self.root).unlink(missing_ok=True)
            self._receipt_marker = self._marker(receipt)
            completed = result
        finally:
            claim.release()
        if completed is not None and self._handoff is not None:
            try:
                self._handoff(completed.incident_work_ids)
            except Exception:
                # Observation is complete even if a supervised repair worker
                # cannot currently accept its durable handoff.
                _log.exception("health-audit recovery handoff failed")
        return completed is not None

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._state_lock:
                manual_wait = (
                    max(0.0, self._manual_retry_deadline - self._monotonic())
                    if self._manual_pending and self._manual_retry_deadline is not None
                    else None
                )
            periodic_wait = (
                max(0.0, self._deadline - self._monotonic())
                if self.config.enabled
                else None
            )
            waits = [
                value for value in (manual_wait, periodic_wait) if value is not None
            ]
            wait = min(waits) if waits else None
            self._wake.wait(wait)
            self._wake.clear()
            if self._stop.is_set():
                return
            with self._state_lock:
                # A request arriving exactly when the periodic deadline is due
                # joins that scheduled pass.  The scheduled completion advances
                # its own deadline; no second manual pass follows it.
                periodic_due = (
                    self.config.enabled and self._monotonic() >= self._deadline
                )
                manual_ready = self._manual_pending and (
                    self._manual_retry_deadline is None
                    or self._monotonic() >= self._manual_retry_deadline
                )
                manual = manual_ready and not periodic_due
                if not periodic_due and not manual:
                    continue
                self._manual_pending = False
                self._manual_retry_deadline = None
                self._in_flight = True
            completed = False
            try:
                if manual:
                    completed = self._run_pass_once(manual=True)
                else:
                    completed = self.run_due_pass()
            except Exception:
                # A failed pass is not completed and never advances the receipt.
                # Keep unrelated delivery alive and retry after a bounded pause.
                _log.exception("supervisor health-audit pass failed")
                if not manual:
                    self._deadline = self._monotonic() + min(
                        _BUSY_RETRY_SECONDS, float(self.config.interval_seconds)
                    )
            finally:
                with self._state_lock:
                    self._in_flight = False
                    if manual and not completed and not self._stop.is_set():
                        self._manual_pending = True
                        self._manual_retry_deadline = self._monotonic() + min(
                            _BUSY_RETRY_SECONDS,
                            float(self.config.interval_seconds),
                        )

    def _ensure_thread(self) -> None:
        with self._state_lock:
            self._ensure_thread_locked()

    def _ensure_thread_locked(self) -> None:
        if self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._run,
            name="supervisor-health-audit",
            daemon=True,
        )
        self._thread.start()

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


def _write_failure(root: Path, failure: Mapping[str, object]) -> None:
    _write_json_atomically(audit_failure_path(root), failure)


def _write_json_atomically(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
    )
    try:
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(value, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


__all__ = [
    "AuditPass",
    "AuditPassCancelled",
    "AuditPassResult",
    "AuditPassTimedOut",
    "HealthAuditLane",
    "audit_failure_path",
    "audit_receipt_path",
    "canonical_audit_root",
    "read_audit_failure",
    "read_audit_receipt",
    "run_bounded_audit_pass",
]
