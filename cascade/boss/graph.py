"""Boss queue consumer: process human orders without idle board scanning."""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import resolve_root
from cascade.boss.orders import process_boss_event
from cascade.watchdog.events import read_events
from cascade.watchdog.lock import process_lock

_consumer_root: Path | None = None
_consumer_offset: int = 0
# (st_dev, st_ino) for docs/_queue/boss.jsonl — avoids replay when offset > size after truncate.
_consumer_file_id: tuple[int, int] | None = None


def _boss_queue_path(repo: Path) -> Path:
    return repo / "docs" / "_queue" / "boss.jsonl"


def process_boss_queue(*, root: Path | None = None, offset: int = 0) -> int:
    """Read new ``boss`` queue lines after ``offset``, handle orders, return new offset.

    When no new events exist, returns the same offset and performs zero dispatches.

    Persists queue file identity (device + inode) in module state so a truncated file
    with the same inode does not reset the read cursor and re-dispatch old events.
    """

    global _consumer_file_id

    repo = resolve_root(root)
    path = _boss_queue_path(repo)
    with process_lock:
        if not path.exists():
            _consumer_file_id = None
            events, new_offset = read_events("boss", offset, root=repo)
            for event in events:
                process_boss_event(event, root=repo)
            return new_offset
        stat = path.stat()
        current_id = (stat.st_dev, stat.st_ino)
        size = stat.st_size

    if _consumer_file_id is not None and _consumer_file_id != current_id:
        read_offset = 0
    elif offset > size:
        _consumer_file_id = current_id
        return size
    else:
        read_offset = offset

    events, new_offset = read_events("boss", read_offset, root=repo)
    _consumer_file_id = current_id
    for event in events:
        process_boss_event(event, root=repo)
    return new_offset


def install_boss_consumer(root: Path | None = None) -> None:
    """Remember repo root and queue offset for watchdog ticks (idempotent)."""

    global _consumer_root, _consumer_offset, _consumer_file_id
    repo = resolve_root(root)
    if _consumer_root != repo:
        _consumer_offset = 0
        _consumer_file_id = None
    _consumer_root = repo


def tick_boss_consumer() -> int:
    """Advance the installed consumer one queue read. Safe on idle ticks."""

    if _consumer_root is None:
        raise RuntimeError("install_boss_consumer(root) must run before tick_boss_consumer")
    global _consumer_offset
    _consumer_offset = process_boss_queue(root=_consumer_root, offset=_consumer_offset)
    return _consumer_offset


def boss_consumer_offset() -> int:
    """Return the persisted read offset for tests and integration."""

    return _consumer_offset


def reset_boss_consumer_offset(offset: int = 0) -> None:
    """Reset persisted offset (tests only)."""

    global _consumer_offset, _consumer_file_id
    _consumer_offset = max(0, offset)
    _consumer_file_id = None
