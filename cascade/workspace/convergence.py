"""Read-only bounded convergence-state detection (feat_012_002 / task_012_002_001).

Uses Boss View dispatch eligibility and durable board, queue, cursor, and lifecycle
evidence. Process liveness (in-flight turns, execution lease heartbeats) is excluded
from progress signatures. Observation never dispatches work or mutates lifecycle state.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cascade.board.context import resolve_root
from cascade.board.types import BoardIndex, WorkMeta
from cascade.boss.view import compute_boss_view
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.queue_cursor import queue_byte_size
from cascade.watchdog.types import Event

ConvergenceState = Literal["stalled", "progressing", "gated", "recovered"]

DEFAULT_CONVERGENCE_STALL_THRESHOLD_SECONDS = 600.0
_CONVERGENCE_STALL_TOAST_KIND = "convergence_stall"


@dataclass(frozen=True)
class ConvergenceObservation:
    work_id: str
    tier: str
    state: ConvergenceState
    dispatchable: bool
    progress_signature: str
    stalled_for_seconds: float | None
    blocker: str | None


@dataclass
class _Episode:
    signature: str
    since_monotonic: float


_episodes: dict[str, _Episode] = {}
_prev_state: dict[str, ConvergenceState] = {}
_emitted_stall_evidence: dict[str, tuple[str, str | None, float]] = {}
_clock: Callable[[], float] = time.monotonic


def reset_convergence_detection_for_tests() -> None:
    """Clear in-process episode memory (tests only)."""

    _episodes.clear()
    _prev_state.clear()
    _emitted_stall_evidence.clear()
    global _clock
    _clock = time.monotonic


def clear_convergence_diagnostic_memory() -> None:
    """Forget emitted stall diagnostics (tests only)."""

    _emitted_stall_evidence.clear()


def set_convergence_clock_for_tests(clock: Callable[[], float]) -> None:
    """Inject monotonic time (tests only)."""

    global _clock
    _clock = clock


def observe_convergence_states(*, root: Path | None = None) -> list[ConvergenceObservation]:
    """Return convergence state for backlog features and tasks on the board."""

    from cascade.workspace.integration_worktree import merged_board

    repo = resolve_root(root)
    board = merged_board(repo)
    view = compute_boss_view(root=repo)
    dispatchable_features = set(view.dispatchable_features)
    dispatchable_tasks = set(view.dispatchable_tasks)
    threshold = _stall_threshold_seconds(repo)

    observations: list[ConvergenceObservation] = []
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.tier not in ("feature", "task"):
            continue
        if not _backlog_candidate(meta):
            _clear_episode(work_id)
            continue

        if meta.tier == "feature":
            dispatchable = work_id in dispatchable_features
            blocker = _feature_blocker(meta, board, root=repo, dispatchable=dispatchable)
        else:
            dispatchable = work_id in dispatchable_tasks
            blocker = _task_blocker(
                meta,
                board,
                root=repo,
                dispatchable=dispatchable,
                slots_free=view.slots_free,
            )

        signature = _progress_signature(meta, board=board, root=repo)
        observation = _observe_item(
            work_id=work_id,
            tier=meta.tier,
            dispatchable=dispatchable,
            signature=signature,
            threshold=threshold,
            blocker=blocker,
        )
        observations.append(observation)

    _drop_stale_episodes({obs.work_id for obs in observations})
    return observations


def publish_convergence_diagnostics(*, root: Path | None = None) -> None:
    """Emit deduplicated War Room toasts for dispatchable items beyond the stall threshold."""

    from datetime import datetime, timezone

    repo = resolve_root(root)
    threshold = _stall_threshold_seconds(repo)
    observations = observe_convergence_states(root=repo)
    for obs in observations:
        if obs.state != "stalled":
            _emitted_stall_evidence.pop(obs.work_id, None)
            continue
        evidence = (obs.progress_signature, obs.blocker, threshold)
        if _emitted_stall_evidence.get(obs.work_id) == evidence:
            continue
        _emitted_stall_evidence[obs.work_id] = evidence
        stalled_for = obs.stalled_for_seconds
        stalled_text = f"{stalled_for:.0f}s" if stalled_for is not None else "unknown duration"
        blocker = obs.blocker or "no_durable_progress"
        message = (
            f"{obs.work_id} ({obs.tier}) dispatchable but stalled: "
            f"{blocker} for {stalled_text} (threshold {threshold:.0f}s)"
        )
        payload: dict[str, object] = {
            "kind": _CONVERGENCE_STALL_TOAST_KIND,
            "id": obs.work_id,
            "message": message,
            "body": message,
            "tier": obs.tier,
            "blocker": blocker,
            "stall_threshold_seconds": threshold,
            "stalled_for_seconds": stalled_for,
            "progress_signature": obs.progress_signature,
        }
        try:
            append_event(
                "war_room",
                Event(
                    type="Toast",
                    ts=datetime.now(timezone.utc),
                    payload=payload,
                    dest="war_room",
                ),
                root=repo,
            )
        except OSError:
            _emitted_stall_evidence.pop(obs.work_id, None)


def _observe_item(
    *,
    work_id: str,
    tier: str,
    dispatchable: bool,
    signature: str,
    threshold: float,
    blocker: str | None,
) -> ConvergenceObservation:
    if not dispatchable:
        _clear_episode(work_id)
        _prev_state.pop(work_id, None)
        return ConvergenceObservation(
            work_id=work_id,
            tier=tier,
            state="gated",
            dispatchable=False,
            progress_signature=signature,
            stalled_for_seconds=None,
            blocker=blocker,
        )

    now = _clock()
    episode = _episodes.get(work_id)
    prior_state = _prev_state.get(work_id)
    stalled_for: float | None = None

    if episode is None or episode.signature != signature:
        _episodes[work_id] = _Episode(signature=signature, since_monotonic=now)
        if prior_state == "stalled":
            state: ConvergenceState = "recovered"
        else:
            state = "progressing"
    else:
        stalled_for = max(0.0, now - episode.since_monotonic)
        state = "progressing" if stalled_for < threshold else "stalled"

    if state == "stalled":
        stall_blocker = blocker or "no_durable_progress"
    else:
        stall_blocker = blocker

    if state == "recovered":
        _prev_state[work_id] = "progressing"
    else:
        _prev_state[work_id] = state

    return ConvergenceObservation(
        work_id=work_id,
        tier=tier,
        state=state,
        dispatchable=True,
        progress_signature=signature,
        stalled_for_seconds=stalled_for if state == "stalled" else None,
        blocker=stall_blocker if state in ("stalled", "gated") else None,
    )


def _progress_signature(meta: WorkMeta, *, board: BoardIndex, root: Path) -> str:
    payload = {
        "board": _board_fingerprint(meta),
        "queue_size": queue_byte_size(meta.id, root=root),
        "queue_cursor": _queue_cursor(meta, root=root),
        "lifecycle": _lifecycle_fingerprint(meta.id, root=root),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _board_fingerprint(meta: WorkMeta) -> tuple[object, ...]:
    try:
        stat = meta.path.stat()
        mtime_ns = stat.st_mtime_ns
        size = stat.st_size
    except OSError:
        mtime_ns = 0
        size = 0
    return (
        meta.path.parent.name,
        meta.status,
        mtime_ns,
        size,
        meta.parent_rev,
        tuple(meta.depends_on),
    )


def _lifecycle_fingerprint(work_id: str, *, root: Path) -> tuple[object, ...]:
    events, queue_eof = read_events(work_id, 0, root=root)
    if not events:
        return (0, queue_eof, None, None)
    last = events[-1]
    return (len(events), queue_eof, last.type, last.ts.isoformat())


def _queue_cursor(meta: WorkMeta, *, root: Path) -> int:
    from cascade.workspace.kickoff import _queue_offset

    feature_id = meta.parent if meta.tier == "task" else None
    return _queue_offset(meta.id, meta.tier, root=root, feature_id=feature_id)


def _backlog_candidate(meta: WorkMeta) -> bool:
    from cascade.boss.view import _backlog_open

    return meta.parent is not None and _backlog_open(meta)


def _feature_blocker(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    dispatchable: bool,
) -> str | None:
    if dispatchable:
        return None
    from cascade.feature.readiness import (
        compute_feature_readiness,
        dispatch_refusal_from_readiness,
    )

    readiness = compute_feature_readiness(meta.id, root=root, board=board)
    if readiness is None:
        return "missing"
    return dispatch_refusal_from_readiness(readiness)


def _task_blocker(
    meta: WorkMeta,
    board: BoardIndex,
    *,
    root: Path,
    dispatchable: bool,
    slots_free: int,
) -> str | None:
    if dispatchable:
        return None
    from cascade.boss.view import _backlog_open, _deps_met

    if not _backlog_open(meta):
        return "not_in_backlog"
    if not meta.parent:
        return "orphan"
    if not _deps_met(board, meta, root=root):
        return "unmet_deps"
    if slots_free <= 0:
        return "at_cap"
    return "not_dispatchable"


def _stall_threshold_seconds(root: Path) -> float:
    from cascade.watchdog.config import convergence_stall_threshold_seconds

    return convergence_stall_threshold_seconds(root)


def _clear_episode(work_id: str) -> None:
    _episodes.pop(work_id, None)


def _drop_stale_episodes(active: set[str]) -> None:
    for work_id in list(_episodes):
        if work_id not in active:
            _episodes.pop(work_id, None)
            _prev_state.pop(work_id, None)
