"""In-memory stall and duplicate-kickoff observability for graph queue delivery (feat_017_002)."""

from __future__ import annotations

import logging
from pathlib import Path

from cascade.watchdog.lock import process_lock
from cascade.watchdog.queue_cursor import queue_byte_size

_log = logging.getLogger(__name__)

# Dedupe warnings per (work_id, offset); in-memory only (repeat after restart is OK).
_warned: set[tuple[str, int]] = set()
# Batch end offsets already delivered this supervisor lifetime.
_delivered_batch_ends: set[tuple[str, int]] = set()
# Consecutive maintenance passes with queue ahead and no in-flight turn.
_stall_passes: dict[str, tuple[int, int]] = {}


def clear_queue_observability_memory() -> None:
    """Reset supervisor-local dedupe (tests only)."""

    with process_lock:
        _warned.clear()
        _delivered_batch_ends.clear()
        _stall_passes.clear()


def note_batch_delivered(work_id: str, batch_end_offset: int) -> None:
    """Record a committed queue batch end offset for duplicate-kickoff detection."""

    if batch_end_offset <= 0:
        return
    with process_lock:
        _delivered_batch_ends.add((work_id, batch_end_offset))


def warn_duplicate_kickoff_if_needed(work_id: str, batch_end_offset: int, *, root: Path) -> None:
    """Emit one warning when a delivery targets an already-delivered batch offset."""

    with process_lock:
        if (work_id, batch_end_offset) not in _delivered_batch_ends:
            return
    _emit_incident(
        kind="duplicate_kickoff",
        work_id=work_id,
        offset=batch_end_offset,
        root=root,
        detail=(
            f"delivery targets batch offset {batch_end_offset}, which was already committed"
        ),
    )


def scan_graph_queue_stalls(root: Path) -> None:
    """Flag graphs whose queue stays ahead of the cursor across consecutive maintenance passes."""

    from cascade.workspace.integration_worktree import merged_board
    from cascade.workspace.kickoff import _graph_has_inflight_turn, _queue_offset

    repo = Path(root).resolve()
    board = merged_board(repo)
    seen: set[str] = set()
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.path.parent.name != "2_active":
            continue
        if meta.tier not in ("epic", "feature", "task"):
            continue
        feature_id = meta.parent if meta.tier == "task" else None
        seen.add(work_id)
        cursor = _queue_offset(work_id, meta.tier, root=repo, feature_id=feature_id)
        queue_size = queue_byte_size(work_id, root=repo)
        inflight = _graph_has_inflight_turn(
            work_id, meta.tier, root=repo, feature_id=feature_id
        )
        if queue_size <= cursor or inflight:
            with process_lock:
                _stall_passes.pop(work_id, None)
            continue
        with process_lock:
            prev_cursor, streak = _stall_passes.get(work_id, (cursor, 0))
            if prev_cursor != cursor:
                streak = 0
            streak += 1
            _stall_passes[work_id] = (cursor, streak)
            should_warn = streak >= 2
        if should_warn:
            _emit_incident(
                kind="stall",
                work_id=work_id,
                offset=cursor,
                root=repo,
                detail=(
                    f"queue size {queue_size} is ahead of cursor {cursor} with no turn running "
                    f"for {streak} consecutive maintenance passes"
                ),
            )
    with process_lock:
        for work_id in list(_stall_passes):
            if work_id not in seen:
                _stall_passes.pop(work_id, None)


def _emit_incident(
    *,
    kind: str,
    work_id: str,
    offset: int,
    root: Path,
    detail: str,
) -> None:
    key = (work_id, offset)
    with process_lock:
        if key in _warned:
            return
        _warned.add(key)

    _log.warning(
        "graph queue %s work_id=%s offset=%s %s",
        kind,
        work_id,
        offset,
        detail,
        extra={"kind": kind, "work_id": work_id, "offset": offset},
    )
    try:
        from cascade.war_room.chat_store import append_transcript_message

        append_transcript_message(
            work_id,
            author="system",
            body=f"Queue {kind.replace('_', ' ')}: {detail}",
            root=root,
        )
    except Exception:
        _log.exception("could not append war room system note for %s", work_id)
