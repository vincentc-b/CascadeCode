"""Append-only JSONL queues under docs/_queue/{dest}.jsonl."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

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
        if not path.exists():
            return [], 0
        data = path.read_bytes()
    return _decode_buffer(data, after_offset)


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


def _decode_buffer(data: bytes, after_offset: int) -> tuple[list[Event], int]:
    if after_offset < 0:
        after_offset = 0
    if after_offset > len(data):
        after_offset = 0
    start = after_offset
    if start > 0 and data[start - 1 : start] != b"\n":
        newline = data.find(b"\n", start)
        if newline < 0:
            return [], start
        start = newline + 1
    events: list[Event] = []
    position = start
    while position < len(data):
        newline = data.find(b"\n", position)
        if newline < 0:
            break
        raw = data[position:newline]
        position = newline + 1
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
