"""Watchdog maintenance for in-flight SWE turn progress stalls (feat_012_004)."""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from cascade.agent.turn_registry import LiveTurn, get_live_turn
from cascade.task.execution import (
    clear_in_flight_turn,
    patch_in_flight_turn,
    read_in_flight_turn,
    running_tasks_with_in_flight_turns,
)
from cascade.workspace.stall_recovery import handle_expired_stall_episode
from cascade.workspace.turn_progress import (
    TurnTransportLiveness,
    UsefulProgressEvidence,
    checkpoint_content_fingerprint,
    observe_turn_progress,
    task_worktree_content_fingerprint,
)

_current_swe_task: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_swe_task",
    default=None,
)
_current_swe_task_root: contextvars.ContextVar[Path | None] = contextvars.ContextVar(
    "_current_swe_task_root",
    default=None,
)


def reset_in_flight_turn_watchdog_for_tests() -> None:
    """Clear task binding context (tests only)."""

    _current_swe_task.set(None)
    _current_swe_task_root.set(None)


def _active_repo(root: Path | None = None) -> Path:
    from cascade.board.context import resolve_root

    if root is not None:
        return Path(root).resolve()
    bound = _current_swe_task_root.get()
    if bound is not None:
        return bound
    return resolve_root(None)


@contextmanager
def swe_task_turn_context(
    task_id: str,
    *,
    provider: str,
    model_id: str,
    root: Path,
) -> Iterator[None]:
    """Mark the current asyncio SWE invoke as belonging to ``task_id``."""

    token = _current_swe_task.set(task_id)
    root_token = _current_swe_task_root.set(Path(root).resolve())
    patch_in_flight_turn(
        task_id,
        {
            "provider": provider,
            "model_id": model_id,
            "provider_events": 0,
            "completed_tool_calls": 0,
            "transport_connected": False,
            "pending_provider_await": False,
        },
        root=root,
    )
    try:
        yield
    finally:
        _current_swe_task.reset(token)
        _current_swe_task_root.reset(root_token)
        clear_in_flight_turn(task_id, root=root)


def notify_turn_registered(live: LiveTurn) -> None:
    """Bind a newly registered live turn to the active SWE task, when set."""

    task_id = _current_swe_task.get()
    if task_id is None or live.role != "swe":
        return
    repo = _active_repo()
    row = read_in_flight_turn(task_id, root=repo) or {}
    patch_in_flight_turn(
        task_id,
        {
            "turn_id": live.turn_id,
            "provider": row.get("provider"),
            "model_id": row.get("model_id"),
        },
        root=repo,
    )


def mark_provider_transport_active(*, root: Path | None = None) -> None:
    """Record connected provider transport with a pending await (not useful progress)."""

    repo = _active_repo(root)
    task_id = _current_swe_task.get()
    if task_id is None:
        return
    patch_in_flight_turn(
        task_id,
        {
            "transport_connected": True,
            "pending_provider_await": True,
        },
        root=repo,
    )


def clear_provider_transport(*, root: Path | None = None) -> None:
    repo = _active_repo(root)
    task_id = _current_swe_task.get()
    if task_id is None:
        return
    patch_in_flight_turn(
        task_id,
        {
            "transport_connected": False,
            "pending_provider_await": False,
        },
        root=repo,
    )


def record_provider_event(task_id: str, *, root: Path) -> None:
    row = read_in_flight_turn(task_id, root=root) or {}
    patch_in_flight_turn(
        task_id,
        {"provider_events": int(row.get("provider_events") or 0) + 1},
        root=root,
    )


def record_completed_tool_call(task_id: str, *, root: Path) -> None:
    row = read_in_flight_turn(task_id, root=root) or {}
    patch_in_flight_turn(
        task_id,
        {"completed_tool_calls": int(row.get("completed_tool_calls") or 0) + 1},
        root=root,
    )


def maintain_in_flight_turn_progress(root: Path) -> None:
    """Observe running SWE turns and handle bounded no-progress expiry."""

    repo = Path(root).resolve()
    for task_id, row in running_tasks_with_in_flight_turns(repo):
        turn_id = str(row.get("turn_id") or "")
        if not turn_id:
            continue
        provider = str(row.get("provider") or "cursor")
        model_id = row.get("model_id")
        model_text = str(model_id) if model_id is not None else None

        evidence = UsefulProgressEvidence(
            provider_events=int(row.get("provider_events") or 0),
            completed_tool_calls=int(row.get("completed_tool_calls") or 0),
            checkpoint_fingerprint=checkpoint_content_fingerprint(task_id, root=repo),
            worktree_fingerprint=task_worktree_content_fingerprint(task_id, root=repo),
        )
        live = get_live_turn(turn_id)
        transport = TurnTransportLiveness(
            transport_connected=bool(row.get("transport_connected")),
            pending_provider_await=bool(row.get("pending_provider_await")),
            process_alive=live is not None,
            lease_renewed=False,
        )
        observation = observe_turn_progress(
            turn_id,
            evidence=evidence,
            transport=transport,
            root=repo,
        )
        if observation.state != "no_progress_deadline_exceeded":
            continue
        handle_expired_stall_episode(
            observation,
            task_id=task_id,
            provider=provider,
            model_id=model_text,
            root=repo,
        )
