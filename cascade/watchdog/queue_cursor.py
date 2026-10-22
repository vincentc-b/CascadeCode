"""Monotonic guard for durable queue byte cursors on work graph checkpoints."""

from __future__ import annotations

import logging
from pathlib import Path

from cascade.board.context import resolve_root

_log = logging.getLogger(__name__)


def queue_byte_size(work_id: str, *, root: Path | None = None) -> int:
    """Return the current on-disk queue file size in bytes (0 if missing)."""

    repo = resolve_root(root)
    path = repo / "docs" / "_queue" / f"{work_id}.jsonl"
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def resolve_last_queue_offset(
    work_id: str,
    *,
    current: int,
    proposed: int,
    root: Path | None = None,
) -> int:
    """Return the cursor value to persist.

    Advances are always allowed. Lowering is refused unless the checkpoint
    cursor is ahead of the queue file (truncated, replaced, or missing file).
    """

    current = int(current or 0)
    proposed = int(proposed or 0)
    if proposed >= current:
        return proposed

    file_size = queue_byte_size(work_id, root=root)
    if current > file_size:
        _log.warning(
            "reset last_queue_offset after truncated or replaced queue "
            "work_id=%s current=%s proposed=%s file_size=%s",
            work_id,
            current,
            proposed,
            file_size,
        )
        return proposed

    _log.warning(
        "refused to lower last_queue_offset work_id=%s current=%s proposed=%s file_size=%s",
        work_id,
        current,
        proposed,
        file_size,
    )
    return current
