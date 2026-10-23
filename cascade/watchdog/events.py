"""Append-only JSONL queues under docs/_queue/{dest}.jsonl."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO

from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event


def append_event(dest: str, event: Event, *, root: Path | None = None) -> None:
    """Append one event line. Prior lines are not rewritten."""

    repo = resolve_root(root)
    queue_dest = _safe_dest(dest)
    if event.ts.tzinfo is None or event.ts.utcoffset() is None:
        raise ValueError("event.ts must be timezone-aware")
    stored = Event(
        type=event.type,
        ts=event.ts.astimezone(timezone.utc),
        payload=dict(event.payload),
        dest=queue_dest,
    )
    line = (_encode(stored) + "\n").encode("utf-8")
    path = _queue_path(repo, queue_dest)
    with process_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(line)


def read_events(
    dest: str,
    after_offset: int,
    *,
    root: Path | None = None,
) -> tuple[list[Event], int]:
    """Return events after a byte offset, and the offset after the lines consumed.

    Malformed lines are skipped. A trailing partial line is left for the next read.
    The returned offset advances past skipped lines so they are not read again.
    """

    repo = resolve_root(root)
    queue_dest = _safe_dest(dest)
    path = _queue_path(repo, queue_dest)
    with process_lock:
        try:
            with path.open("rb") as handle:
                return _decode_stream(handle, after_offset)
        except FileNotFoundError:
            return [], 0


def remove_queue_if_unchanged(
    dest: str,
    *,
    expected_size: int,
    root: Path | None = None,
) -> bool:
    """Remove a fully acknowledged queue without racing a concurrent append.

    Callers first read and process through ``expected_size``.  The shared lock
    makes the size check and unlink atomic with respect to ``append_event``.
    A queue that gained another event is deliberately left intact.
    """

    repo = resolve_root(root)
    queue_dest = _safe_dest(dest)
    path = _queue_path(repo, queue_dest)
    with process_lock:
        try:
            if path.stat().st_size != expected_size:
                return False
        except FileNotFoundError:
            return True
        path.unlink()
    return True


def prune_completed_work_queues(*, root: Path | None = None) -> list[str]:
    """Remove queues whose work graph has reached its durable terminal state.

    Active and blocked work queues double as dispatch-authorization evidence,
    so they must not be removed merely because their current events were read.
    A completed Feature also remains live while its merge request is pending.
    Special feeds (``boss`` and ``war_room``) have their own lifecycle.
    """

    repo = resolve_root(root)
    queue_dir = repo / "docs" / "_queue"
    if not queue_dir.is_dir():
        return []

    from cascade.board.errors import SchemaError
    from cascade.board.work_ids import tier_of_work_id
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(repo)
    removable: list[str] = []
    for path in sorted(queue_dir.glob("*.jsonl")):
        work_id = path.stem
        try:
            tier_of_work_id(work_id)
        except SchemaError:
            continue
        meta = board.by_id.get(work_id)
        if (
            meta is None
            or meta.status != "completed"
            or meta.path.parent.name != "3_completed"
        ):
            continue
        if meta.tier == "feature":
            from cascade.review import feature_review_pending

            if feature_review_pending(work_id, root=repo):
                continue
        removable.append(work_id)

    removed: list[str] = []
    with process_lock:
        for work_id in removable:
            path = _queue_path(repo, work_id)
            try:
                path.unlink()
            except FileNotFoundError:
                continue
            removed.append(work_id)
    return removed


def _queue_path(root: Path, dest: str) -> Path:
    return root / "docs" / "_queue" / f"{dest}.jsonl"


def _safe_dest(dest: str) -> str:
    if not isinstance(dest, str) or not dest or dest in {".", ".."}:
        raise ValueError(f"invalid queue dest: {dest!r}")
    if any(sep in dest for sep in ("/", "\\", "\x00")):
        raise ValueError(f"invalid queue dest: {dest!r}")
    if Path(dest).name != dest:
        raise ValueError(f"invalid queue dest: {dest!r}")
    return dest


def _encode(event: Event) -> str:
    payload = {
        "type": event.type,
        "ts": event.ts.astimezone(timezone.utc).isoformat(),
        "payload": event.payload,
        "dest": event.dest,
    }
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _decode_stream(handle: BinaryIO, after_offset: int) -> tuple[list[Event], int]:
    """Read complete lines from a byte cursor without loading its acknowledged prefix."""

    handle.seek(0, 2)
    size = handle.tell()
    if after_offset < 0:
        after_offset = 0
    if after_offset > size:
        after_offset = 0
    start = after_offset
    if start > 0:
        handle.seek(start - 1)
        if handle.read(1) != b"\n":
            handle.seek(start)
            skipped = handle.readline(size - start)
            if not skipped.endswith(b"\n"):
                return [], start
            start = handle.tell()
    handle.seek(start)
    events: list[Event] = []
    position = start
    while position < size:
        raw = handle.readline(size - position)
        if not raw.endswith(b"\n"):
            break
        position = handle.tell()
        raw = raw[:-1]
        if not raw.strip():
            continue
        try:
            events.append(_decode_line(raw))
        except (ValueError, TypeError, json.JSONDecodeError, UnicodeError):
            continue
    return events, position


def _decode_line(raw: bytes) -> Event:
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError("event must be an object")
    event_type = loaded.get("type")
    dest = loaded.get("dest")
    payload = loaded.get("payload")
    stamp = loaded.get("ts")
    if not isinstance(event_type, str) or not isinstance(dest, str) or not isinstance(stamp, str):
        raise ValueError("event fields missing")
    if not isinstance(payload, dict):
        raise ValueError("payload must be an object")
    ts = datetime.fromisoformat(stamp)
    if ts.tzinfo is None or ts.utcoffset() is None:
        raise ValueError("event.ts must be timezone-aware")
    return Event(type=event_type, ts=ts, payload=payload, dest=dest)
