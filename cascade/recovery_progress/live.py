"""Process-bound observations for admitted graph and recovery executor calls.

These records are deliberately ephemeral and observational.  They can describe
an already-admitted call, but cannot create, extend, reclaim, or finalize a
durable recovery claim.
"""

from __future__ import annotations

import hashlib
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Literal

LiveObservationKind = Literal["invocation", "executor"]
LiveObservationState = Literal["live", "stale", "unknown", "unmatched"]

MAX_LIVE_OBSERVATION_SECONDS = 30.0


@dataclass(frozen=True)
class LiveObservationIdentity:
    """Exact worker, graph, action, attempt, and claim identity for one call."""

    kind: LiveObservationKind
    token: str
    runtime_generation: str
    worker_pid: int
    boot_id: str
    process_start_id: str
    graph_id: str
    action_id: str | None
    action_generation: str | None
    attempt_number: int | None
    claim_id: str | None


@dataclass(frozen=True)
class LiveObservation:
    identity: LiveObservationIdentity
    began_at: datetime
    observed_at: datetime
    valid_until: datetime
    claim_expires_at: datetime | None


@dataclass(frozen=True)
class LiveObservationResult:
    state: LiveObservationState
    observation: LiveObservation | None
    reason: str


_lock = threading.Lock()
_observations: dict[str, LiveObservation] = {}
_process_probe: Callable[[int], tuple[str, str] | None]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _read_process_identity(pid: int) -> tuple[str, str] | None:
    """Return boot/process-start identity, None for a proven-dead process.

    Permission and malformed evidence remain errors so callers can distinguish
    inaccessible identity (unknown) from observed death (stale).
    """

    stat_path = f"/proc/{pid}/stat"
    try:
        stat_line = Path(stat_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    close = stat_line.rfind(")")
    if close < 0:
        raise OSError("process stat has no command terminator")
    fields = stat_line[close + 2 :].split()
    if len(fields) <= 19:
        raise OSError("process stat omitted start time")
    boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(
        encoding="utf-8"
    ).strip()
    return boot_id, f"linux:{boot_id}:{pid}:{fields[19]}"


_process_probe = _read_process_identity


def _runtime_identity() -> tuple[str, int, str, str]:
    pid = os.getpid()
    process = _process_probe(pid)
    if process is None:
        raise RuntimeError("current worker process identity is unavailable")
    boot_id, process_start_id = process
    generation = "sha256:" + hashlib.sha256(
        process_start_id.encode("utf-8")
    ).hexdigest()
    return generation, pid, boot_id, process_start_id


def _as_time(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("live observation times must include a timezone")
    return parsed.astimezone(timezone.utc)


def begin_live_observation(
    kind: LiveObservationKind,
    *,
    graph_id: str,
    action_id: str | None = None,
    action_generation: str | None = None,
    attempt_number: int | None = None,
    claim_id: str | None = None,
    claim_expires_at: datetime | str | None = None,
    now: datetime | None = None,
) -> LiveObservation:
    """Register begin evidence for an already-admitted call."""

    if kind not in ("invocation", "executor"):
        raise ValueError(f"unknown live observation kind: {kind}")
    if not graph_id:
        raise ValueError("graph identity is required")
    exact_action = (action_id, action_generation, attempt_number, claim_id)
    if any(value is not None for value in exact_action) and any(
        value is None for value in exact_action
    ):
        raise ValueError("action-bound live evidence requires exact generation, attempt, and claim")
    if kind == "executor" and any(value is None for value in exact_action):
        raise ValueError("executor live evidence requires exact action identity")

    observed_at = (now or _utc_now()).astimezone(timezone.utc)
    claim_expiry = _as_time(claim_expires_at)
    valid_until = observed_at + timedelta(seconds=MAX_LIVE_OBSERVATION_SECONDS)
    if claim_expiry is not None:
        valid_until = min(valid_until, claim_expiry)
    runtime_generation, pid, boot_id, process_start_id = _runtime_identity()
    identity = LiveObservationIdentity(
        kind=kind,
        token=uuid.uuid4().hex,
        runtime_generation=runtime_generation,
        worker_pid=pid,
        boot_id=boot_id,
        process_start_id=process_start_id,
        graph_id=graph_id,
        action_id=action_id,
        action_generation=action_generation,
        attempt_number=attempt_number,
        claim_id=claim_id,
    )
    observation = LiveObservation(
        identity=identity,
        began_at=observed_at,
        observed_at=observed_at,
        valid_until=valid_until,
        claim_expires_at=claim_expiry,
    )
    with _lock:
        _observations[identity.token] = observation
    return observation


def refresh_live_observation(
    identity: LiveObservationIdentity,
    *,
    now: datetime | None = None,
) -> LiveObservationResult:
    """Refresh only the exact registered token while its worker and claim match."""

    observed_at = (now or _utc_now()).astimezone(timezone.utc)
    with _lock:
        current = _observations.get(identity.token)
        if current is None or current.identity != identity:
            return LiveObservationResult("unmatched", None, "token_not_registered")
        if observed_at >= current.valid_until:
            _observations.pop(identity.token, None)
            return LiveObservationResult("stale", current, "observation_expired")
        try:
            process = _process_probe(identity.worker_pid)
        except (OSError, PermissionError):
            return LiveObservationResult("unknown", current, "process_identity_inaccessible")
        if process is None:
            _observations.pop(identity.token, None)
            return LiveObservationResult("stale", current, "process_stopped")
        if process != (identity.boot_id, identity.process_start_id):
            _observations.pop(identity.token, None)
            return LiveObservationResult("stale", current, "worker_generation_changed")
        valid_until = observed_at + timedelta(seconds=MAX_LIVE_OBSERVATION_SECONDS)
        if current.claim_expires_at is not None:
            valid_until = min(valid_until, current.claim_expires_at)
        if valid_until <= observed_at:
            _observations.pop(identity.token, None)
            return LiveObservationResult("stale", current, "claim_expired")
        refreshed = replace(
            current, observed_at=observed_at, valid_until=valid_until
        )
        _observations[identity.token] = refreshed
        return LiveObservationResult("live", refreshed, "matching_live_token")


def end_live_observation(identity: LiveObservationIdentity) -> bool:
    """Record call exit by removing only the matching registered token."""

    with _lock:
        current = _observations.get(identity.token)
        if current is None or current.identity != identity:
            return False
        _observations.pop(identity.token, None)
        return True


def registered_live_observations() -> tuple[LiveObservation, ...]:
    """Return detached process-local registrations for supervised projection."""

    with _lock:
        return tuple(_observations.values())


@contextmanager
def live_observation(
    kind: LiveObservationKind,
    **identity: object,
) -> Iterator[LiveObservationIdentity]:
    observation = begin_live_observation(kind, **identity)  # type: ignore[arg-type]
    try:
        yield observation.identity
    finally:
        end_live_observation(observation.identity)


def reset_live_observations_for_tests() -> None:
    global _process_probe
    with _lock:
        _observations.clear()
    _process_probe = _read_process_identity


def set_process_probe_for_tests(
    probe: Callable[[int], tuple[str, str] | None],
) -> None:
    global _process_probe
    _process_probe = probe


__all__ = [
    "LiveObservation",
    "LiveObservationIdentity",
    "LiveObservationResult",
    "MAX_LIVE_OBSERVATION_SECONDS",
    "begin_live_observation",
    "end_live_observation",
    "live_observation",
    "registered_live_observations",
    "refresh_live_observation",
]
