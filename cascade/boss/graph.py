"""Boss queue consumer: process human orders without idle board scanning."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.boss.orders import process_boss_event
from cascade.watchdog.events import read_events
from cascade.watchdog.lock import process_lock

_consumer_root: Path | None = None
_consumer_offset: int = 0
# (st_dev, st_ino) for docs/_queue/boss.jsonl — avoids replay when offset > size after truncate.
_consumer_file_id: tuple[int, int] | None = None


def _cursor_path(repo: Path) -> Path:
    return repo / ".cascade" / "boss_queue_cursor.json"


def _read_cursor(repo: Path) -> tuple[int, tuple[int, int] | None, str | None]:
    path = _cursor_path(repo)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        offset = max(0, int(value.get("offset") or 0))
        file_id = (int(value["device"]), int(value["inode"]))
        digest = str(value["prefix_sha256"])
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError):
        return 0, None, None
    return offset, file_id, digest


def _write_cursor(
    repo: Path, offset: int, file_id: tuple[int, int], prefix_sha256: str
) -> None:
    path = _cursor_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps(
            {
                "version": 1,
                "offset": max(0, offset),
                "device": file_id[0],
                "inode": file_id[1],
                "prefix_sha256": prefix_sha256,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def _prefix_sha256(path: Path, size: int) -> str:
    with process_lock:
        data = path.read_bytes()[:size]
    return hashlib.sha256(data).hexdigest()


def _boss_queue_path(repo: Path) -> Path:
    return repo / "docs" / "_queue" / "boss.jsonl"


def process_boss_queue(*, root: Path | None = None, offset: int = 0) -> int:
    """Read new ``boss`` queue lines after ``offset``, handle orders, return new offset.

    When no new events exist, returns the same offset and performs zero dispatches.

    The acknowledged offset and file identity are persisted under ``.cascade``
    before a fully consumed file is removed.  Therefore a supervisor restart
    cannot replay a stale dispatch file, while an event appended during handling
    keeps the queue in place for the next tick.
    """

    global _consumer_file_id

    repo = resolve_root(root)
    path = _boss_queue_path(repo)
    with process_lock:
        if not path.exists():
            _consumer_file_id = None
            return 0
        stat = path.stat()
        current_id = (stat.st_dev, stat.st_ino)
        size = stat.st_size

    durable_offset, durable_file_id, durable_digest = _read_cursor(repo)
    durable_prefix_matches = (
        durable_file_id == current_id
        and durable_digest is not None
        and durable_offset <= size
        and _prefix_sha256(path, durable_offset) == durable_digest
    )
    if durable_prefix_matches:
        offset = max(offset, durable_offset)
    elif durable_file_id is not None:
        offset = 0

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
    _write_cursor(repo, new_offset, current_id, _prefix_sha256(path, new_offset))

    # Only unlink when the exact snapshot just acknowledged is still the whole
    # file.  If a producer appended meanwhile, its suffix remains available and
    # the durable offset points to its first unread byte.
    from cascade.watchdog.events import remove_queue_if_unchanged

    if remove_queue_if_unchanged("boss", expected_size=new_offset, root=repo):
        _consumer_file_id = None
        return 0
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
