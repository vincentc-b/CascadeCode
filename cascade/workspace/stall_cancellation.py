"""Targeted stall turn cancellation via feat_018_002 live-turn registry (task_012_004_002)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from cascade.workspace.turn_progress import (
    TurnProgressObservation,
    checkpoint_content_fingerprint,
    drop_turn_progress,
    task_worktree_content_fingerprint,
)

CancellationTermination = Literal["graceful", "forced", "not_required", "turn_not_live"]

_handled_episodes: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class StallEpisode:
    turn_id: str
    episode_signature: str
    stalled_for_seconds: float | None
    last_progress_kind: str | None


@dataclass(frozen=True)
class PreservedWorkState:
    task_id: str
    checkpoint_fingerprint: tuple[int, int] | None
    worktree_fingerprint: str | None
    checkpoint_present: bool
    worktree_present: bool


@dataclass(frozen=True)
class CancellationOutcome:
    turn_id: str
    episode_signature: str
    termination: CancellationTermination
    process_tree_pid: int | None
    force_kill_applied: bool
    preserved: PreservedWorkState


def stall_episode_from_observation(
    observation: TurnProgressObservation,
) -> StallEpisode | None:
    if observation.state != "no_progress_deadline_exceeded":
        return None
    return StallEpisode(
        turn_id=observation.turn_id,
        episode_signature=observation.episode_signature,
        stalled_for_seconds=observation.stalled_for_seconds,
        last_progress_kind=observation.last_progress_kind,
    )


def stall_cancellation_seam_available() -> bool:
    """True when feat_018_002 live-turn cancellation is importable."""

    try:
        from cascade.agent.turn_registry import cancel_live_turn
        from cascade.workspace.drain import is_draining
    except ImportError:
        return False
    return callable(cancel_live_turn) and callable(is_draining)


def reset_stall_cancellation_for_tests() -> None:
    _handled_episodes.clear()


def capture_preserved_work_state(task_id: str, *, root: Path) -> PreservedWorkState:
    from cascade.task.checkpoint import checkpoint_path
    from cascade.workspace.integration_worktree import get_integration_worktree

    checkpoint_fp = checkpoint_content_fingerprint(task_id, root=root)
    worktree_fp = task_worktree_content_fingerprint(task_id, root=root)
    cp = checkpoint_path(task_id, root=root)
    wt = get_integration_worktree(root, "task", task_id)
    return PreservedWorkState(
        task_id=task_id,
        checkpoint_fingerprint=checkpoint_fp,
        worktree_fingerprint=worktree_fp,
        checkpoint_present=cp.is_file(),
        worktree_present=wt is not None and wt.path.is_dir(),
    )


def cancel_stalled_turn(
    observation: TurnProgressObservation,
    *,
    task_id: str,
    root: Path,
    grace_seconds: float | None = None,
) -> CancellationOutcome | None:
    """Cancel one expired stall episode and preserve checkpoint/worktree evidence."""

    if not stall_cancellation_seam_available():
        raise RuntimeError(
            "feat_018_002 cancellation seam unavailable; cannot cancel stalled turn"
        )

    episode = stall_episode_from_observation(observation)
    if episode is None:
        return None

    episode_key = (episode.turn_id, episode.episode_signature)
    if episode_key in _handled_episodes:
        return None

    preserved = capture_preserved_work_state(task_id, root=root)

    from cascade.agent.turn_registry import CANCEL_GRACE_S, cancel_live_turn, get_live_turn

    grace = CANCEL_GRACE_S if grace_seconds is None else grace_seconds
    live_before = get_live_turn(episode.turn_id)
    process_pid = live_before.pid if live_before is not None else None

    if live_before is None:
        termination: CancellationTermination = "turn_not_live"
        force_kill = False
    else:
        _, force_kill = cancel_live_turn(
            episode.turn_id,
            grace_seconds=grace,
            escalate_to_sigkill=True,
        )
        termination = "forced" if force_kill else "graceful"

    _handled_episodes.add(episode_key)
    drop_turn_progress(episode.turn_id)

    return CancellationOutcome(
        turn_id=episode.turn_id,
        episode_signature=episode.episode_signature,
        termination=termination,
        process_tree_pid=process_pid,
        force_kill_applied=force_kill,
        preserved=preserved,
    )
