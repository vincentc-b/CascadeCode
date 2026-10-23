"""In-flight SWE turn useful-progress and stall episode tracking (feat_012_004 / task_012_004_001).

Transport/process liveness is tracked separately from useful progress. Lease renewal,
a connected transport, and a pending provider await are liveness evidence only and do
not advance or reset a stall episode.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

UsefulProgressKind = Literal[
    "provider_event",
    "completed_tool_call",
    "checkpoint_advancement",
    "worktree_advancement",
]

TurnProgressState = Literal["progressing", "no_progress_deadline_exceeded"]

DEFAULT_NO_PROGRESS_DEADLINE_SECONDS = 600.0


@dataclass(frozen=True)
class UsefulProgressEvidence:
    """Durable useful-progress counters and fingerprints for one in-flight turn."""

    provider_events: int = 0
    completed_tool_calls: int = 0
    checkpoint_fingerprint: tuple[int, int] | None = None
    worktree_fingerprint: str | None = None


@dataclass(frozen=True)
class TurnTransportLiveness:
    """Provider transport and worker process liveness (not useful progress)."""

    transport_connected: bool = False
    pending_provider_await: bool = False
    process_alive: bool = False
    lease_renewed: bool = False


@dataclass(frozen=True)
class TurnProgressObservation:
    turn_id: str
    episode_signature: str
    state: TurnProgressState
    stalled_for_seconds: float | None
    transport_connected: bool
    process_alive: bool
    pending_provider_await: bool
    last_progress_kind: UsefulProgressKind | None
    last_progress_at_monotonic: float | None


@dataclass
class _Episode:
    signature: str
    since_monotonic: float
    last_progress_kind: UsefulProgressKind | None
    last_progress_at_monotonic: float | None


_episodes: dict[str, _Episode] = {}
_prior_evidence: dict[str, UsefulProgressEvidence] = {}
_clock: Callable[[], float] = time.monotonic


def reset_turn_progress_for_tests() -> None:
    """Clear in-process episode memory (tests only)."""

    _episodes.clear()
    _prior_evidence.clear()
    global _clock
    _clock = time.monotonic


def set_turn_progress_clock_for_tests(clock: Callable[[], float]) -> None:
    """Inject monotonic time (tests only)."""

    global _clock
    _clock = clock


def clear_turn_progress_memory() -> None:
    """Forget tracked episodes without resetting the clock (watchdog/tests)."""

    _episodes.clear()
    _prior_evidence.clear()


def useful_progress_signature(evidence: UsefulProgressEvidence) -> str:
    """Stable hash of useful-progress evidence (excludes transport/liveness)."""

    payload = {
        "provider_events": evidence.provider_events,
        "completed_tool_calls": evidence.completed_tool_calls,
        "checkpoint": evidence.checkpoint_fingerprint,
        "worktree": evidence.worktree_fingerprint,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def observe_turn_progress(
    turn_id: str,
    *,
    evidence: UsefulProgressEvidence,
    transport: TurnTransportLiveness | None = None,
    deadline_seconds: float | None = None,
    root: Path | None = None,
) -> TurnProgressObservation:
    """Update stall-episode state for one in-flight turn and return the observation."""

    transport = transport or TurnTransportLiveness()
    if deadline_seconds is None:
        from cascade.board.context import resolve_root

        repo = resolve_root(root)
        deadline_seconds = _no_progress_deadline_seconds(repo)

    now = _clock()
    signature = useful_progress_signature(evidence)
    prior = _prior_evidence.get(turn_id)
    episode = _episodes.get(turn_id)

    progress_kind: UsefulProgressKind | None = None
    if prior is None or useful_progress_signature(prior) != signature:
        progress_kind = _progress_kind_delta(prior, evidence)
        episode = _Episode(
            signature=signature,
            since_monotonic=now,
            last_progress_kind=progress_kind,
            last_progress_at_monotonic=now if progress_kind is not None else None,
        )
        _episodes[turn_id] = episode
        _prior_evidence[turn_id] = evidence
    elif episode is None:
        episode = _Episode(
            signature=signature,
            since_monotonic=now,
            last_progress_kind=None,
            last_progress_at_monotonic=None,
        )
        _episodes[turn_id] = episode
        _prior_evidence[turn_id] = evidence

    assert episode is not None
    stalled_for = max(0.0, now - episode.since_monotonic)
    if stalled_for >= deadline_seconds:
        state: TurnProgressState = "no_progress_deadline_exceeded"
    else:
        state = "progressing"

    return TurnProgressObservation(
        turn_id=turn_id,
        episode_signature=episode.signature,
        state=state,
        stalled_for_seconds=stalled_for if state == "no_progress_deadline_exceeded" else None,
        transport_connected=transport.transport_connected,
        process_alive=transport.process_alive,
        pending_provider_await=transport.pending_provider_await,
        last_progress_kind=episode.last_progress_kind,
        last_progress_at_monotonic=episode.last_progress_at_monotonic,
    )


def drop_turn_progress(turn_id: str) -> None:
    """Forget episode state when a turn completes or is cancelled."""

    _episodes.pop(turn_id, None)
    _prior_evidence.pop(turn_id, None)


def checkpoint_content_fingerprint(task_id: str, *, root: Path) -> tuple[int, int] | None:
    """Return checkpoint file (mtime_ns, size) when present."""

    from cascade.task.checkpoint import checkpoint_path

    path = checkpoint_path(task_id, root=root)
    try:
        stat = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    return (stat.st_mtime_ns, stat.st_size)


def task_worktree_content_fingerprint(task_id: str, *, root: Path) -> str | None:
    """Hash sorted relative paths with mtime_ns and size under the task worktree."""

    from cascade.workspace.integration_worktree import get_integration_worktree

    entry = get_integration_worktree(root, "task", task_id)
    if entry is None or not entry.path.is_dir():
        return None
    return _tree_fingerprint(entry.path)


def _tree_fingerprint(root: Path) -> str:
    entries: list[tuple[str, int, int]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if ".git" in path.parts:
            continue
        rel = path.relative_to(root).as_posix()
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append((rel, stat.st_mtime_ns, stat.st_size))
    payload = json.dumps(entries, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _progress_kind_delta(
    prior: UsefulProgressEvidence | None,
    current: UsefulProgressEvidence,
) -> UsefulProgressKind | None:
    if prior is None:
        if current.provider_events > 0:
            return "provider_event"
        if current.completed_tool_calls > 0:
            return "completed_tool_call"
        if current.checkpoint_fingerprint is not None:
            return "checkpoint_advancement"
        if current.worktree_fingerprint is not None:
            return "worktree_advancement"
        return None

    if current.provider_events > prior.provider_events:
        return "provider_event"
    if current.completed_tool_calls > prior.completed_tool_calls:
        return "completed_tool_call"
    if current.checkpoint_fingerprint != prior.checkpoint_fingerprint:
        return "checkpoint_advancement"
    if current.worktree_fingerprint != prior.worktree_fingerprint:
        return "worktree_advancement"
    return None


def _no_progress_deadline_seconds(root: Path) -> float:
    from cascade.watchdog.config import turn_progress_no_progress_deadline_seconds

    return turn_progress_no_progress_deadline_seconds(root)
