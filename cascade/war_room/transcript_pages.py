"""Writer-published bounded transcript pages and read-only API projection reader."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import quote

from cascade.board.context import resolve_tracking_root
from cascade.workspace.integration_worktree import locate_trunk

MAX_SOURCE_BYTES = 1024 * 1024
MAX_RESPONSE_BYTES = 256 * 1024
MAX_LIMIT = 100
DEFAULT_LIMIT = 50
DETAIL_CHUNK_BYTES = 64 * 1024
_PAGE_ROWS = 100
_PREVIEW_BYTES = 1024
_MAX_ITEM_BYTES = 4 * 1024
_PROJECTION_DIR = Path(".cascade") / "transcript_pages"


class TranscriptReadError(RuntimeError):
    """Base class for typed transcript read failures."""


class TranscriptInvalidRequest(TranscriptReadError):
    pass


class TranscriptHistoryPending(TranscriptReadError):
    pass


class TranscriptCursorRestart(TranscriptReadError):
    def __init__(self, incarnation: str, restart_url: str) -> None:
        self.incarnation = incarnation
        self.restart_url = restart_url
        super().__init__("the transcript cursor no longer names current history")


@dataclass(frozen=True)
class TranscriptPageResult:
    payload: dict[str, Any]
    serialized: bytes


def _runtime_root(root: Path) -> Path:
    return locate_trunk(resolve_tracking_root(root)).resolve()


def _store_key(graph_id: str) -> str:
    return hashlib.sha256(graph_id.encode("utf-8")).hexdigest()


def _projection_root(graph_id: str, *, root: Path) -> Path:
    return _runtime_root(root) / _PROJECTION_DIR / _store_key(graph_id)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def _write_immutable(path: Path, data: bytes) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            pass
        descriptor = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    finally:
        temporary.unlink(missing_ok=True)


def invalidate_transcript_projection(graph_id: str, *, root: Path) -> None:
    """Remove only the direct pointer; immutable evidence remains available to writers."""

    pointer = _projection_root(graph_id, root=root) / "current.json"
    if pointer.exists():
        pointer.unlink()
        descriptor = os.open(pointer.parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _utf8_prefix(raw: bytes, limit: int) -> str:
    candidate = raw[:limit]
    while candidate:
        try:
            return candidate.decode("utf-8")
        except UnicodeDecodeError as exc:
            candidate = candidate[: exc.start]
    return ""


_ITEM_FIELDS = {
    "id", "graph_id", "author", "body", "ts", "event_schema_version", "kind",
    "source_key", "occurred_at", "appended_at", "provenance", "receipt_id",
    "entry_id", "action_id", "generation", "attempt_number", "target",
    "source_reference", "checkpoint_lineage", "message_ordinal",
}


def _project_item(row: Mapping[str, Any], detail_root: Path) -> dict[str, Any]:
    item = dict(row)
    body = item.get("body")
    if not isinstance(body, str):
        body = str(body or "")
        item["body"] = body
    raw_body = body.encode("utf-8")
    if len(raw_body) > _PREVIEW_BYTES:
        digest = hashlib.sha256(raw_body).hexdigest()
        _write_immutable(detail_root / f"{digest}.txt", raw_body)
        preview = _utf8_prefix(raw_body, _PREVIEW_BYTES)
        item["body"] = preview + "\n\n[Transcript preview; open detail for complete message.]"
        item["detail_truncated"] = True
        item["detail_digest"] = digest
    if len(_json_bytes(item)) <= _MAX_ITEM_BYTES:
        return item
    # Legacy extension fields can be arbitrarily large. Preserve the public
    # transcript contract and the exact body through detail, while keeping a
    # single projected item bounded.
    item = {key: value for key, value in item.items() if key in _ITEM_FIELDS or key.startswith("detail_")}
    for key, value in tuple(item.items()):
        if isinstance(value, str) and key not in {"body", "detail_digest"}:
            encoded = value.encode("utf-8")
            if len(encoded) > 128:
                item[key] = _utf8_prefix(encoded, 128) + " [truncated]"
    if len(_json_bytes(item)) > _MAX_ITEM_BYTES:
        item = {
            key: value
            for key, value in item.items()
            if key
            in {
                "id", "graph_id", "author", "body", "ts", "kind", "source_key",
                "occurred_at", "appended_at", "provenance", "detail_truncated",
                "detail_digest",
            }
        }
    return item


def _read_event(source_path: Path, offset: int, length: int) -> dict[str, Any]:
    descriptor = os.open(source_path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise RuntimeError("transcript source is not a regular file")
        raw = os.pread(descriptor, length, offset)
    finally:
        os.close(descriptor)
    if len(raw) != length:
        raise RuntimeError("committed transcript bytes are unavailable")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise RuntimeError("committed transcript row is invalid")
    return value


def _read_prior_manifest(home: Path, incarnation: str) -> dict[str, Any] | None:
    try:
        pointer = json.loads((home / "current.json").read_bytes())
        name = pointer["manifest"]
        if not isinstance(name, str) or "/" in name or "\\" in name:
            return None
        manifest = json.loads((home / "manifests" / name).read_bytes())
    except (OSError, KeyError, json.JSONDecodeError, TypeError):
        return None
    if manifest.get("incarnation") != incarnation:
        return None
    return manifest


def publish_transcript_projection(
    graph_id: str,
    *,
    source_path: Path,
    connection: Any,
    root: Path,
) -> None:
    """Publish committed index rows without exposing the writer database to GET."""

    state = connection.execute(
        "SELECT incarnation, indexed_end FROM state WHERE singleton = 1"
    ).fetchone()
    if state is None:
        raise RuntimeError("transcript index state is unavailable")
    incarnation = str(state["incarnation"])
    indexed_end = int(state["indexed_end"])
    source_size = source_path.stat().st_size if source_path.is_file() else 0
    pending = connection.execute("SELECT 1 FROM pending_intent LIMIT 1").fetchone() is not None
    buffered = connection.execute("SELECT 1 FROM legacy_import_buffer LIMIT 1").fetchone() is not None
    completeness = "complete" if indexed_end == source_size and not pending and not buffered else "incomplete"
    summary = connection.execute(
        "SELECT COUNT(*) AS count, MIN(append_sequence) AS first_seq, "
        "MAX(append_sequence) AS last_seq FROM events"
    ).fetchone()
    count = int(summary["count"])
    high_water = int(summary["last_seq"] or 0)
    first_sequence = int(summary["first_seq"] or 0)
    home = _projection_root(graph_id, root=root)
    page_root = home / "pages"
    detail_root = home / "details"
    prior = _read_prior_manifest(home, incarnation)
    pages: list[dict[str, Any]] = []
    details: dict[str, str] = {}
    rebuild_sequence = first_sequence
    if prior is not None:
        prior_details = prior.get("details")
        if isinstance(prior_details, dict):
            details = {
                str(message_id): str(digest)
                for message_id, digest in prior_details.items()
                if isinstance(message_id, str) and isinstance(digest, str)
            }
        prior_pages = prior.get("pages")
        if isinstance(prior_pages, list):
            pages = [dict(page) for page in prior_pages if isinstance(page, dict)]
            if pages and int(pages[-1].get("count", 0)) < _PAGE_ROWS:
                rebuild_sequence = int(pages[-1]["first_sequence"])
                pages.pop()
            elif pages:
                rebuild_sequence = int(pages[-1]["last_sequence"]) + 1
    if count == 0:
        pages = []
        details = {}
    elif not pages and rebuild_sequence == 0:
        rebuild_sequence = first_sequence
    while rebuild_sequence and rebuild_sequence <= high_water:
        events = connection.execute(
            "SELECT append_sequence, byte_offset, byte_length FROM events "
            "WHERE append_sequence >= ? ORDER BY append_sequence LIMIT ?",
            (rebuild_sequence, _PAGE_ROWS),
        ).fetchall()
        if not events:
            break
        items: list[dict[str, Any]] = []
        for event in events:
            row = _read_event(source_path, int(event["byte_offset"]), int(event["byte_length"]))
            item = _project_item(row, detail_root)
            item["append_sequence"] = int(event["append_sequence"])
            if isinstance(item.get("id"), str) and isinstance(item.get("detail_digest"), str):
                details[item["id"]] = item["detail_digest"]
            items.append(item)
        page_value = {"schema_version": 1, "graph_id": graph_id, "incarnation": incarnation, "items": items}
        page_bytes = _json_bytes(page_value)
        if len(page_bytes) > MAX_SOURCE_BYTES:
            raise RuntimeError("projected transcript page exceeds its source budget")
        digest = hashlib.sha256(page_bytes).hexdigest()
        name = f"{digest}.json"
        _write_immutable(page_root / name, page_bytes)
        pages.append(
            {
                "first_sequence": int(events[0]["append_sequence"]),
                "last_sequence": int(events[-1]["append_sequence"]),
                "count": len(events),
                "file": name,
                "bytes": len(page_bytes),
            }
        )
        rebuild_sequence = int(events[-1]["append_sequence"]) + 1
    manifest = {
        "schema_version": 1,
        "graph_id": graph_id,
        "incarnation": incarnation,
        "high_water_mark": high_water,
        "first_sequence": first_sequence,
        "completeness": completeness,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "details": details,
    }
    manifest_bytes = _json_bytes(manifest)
    manifest_name = f"{hashlib.sha256(manifest_bytes).hexdigest()}.json"
    _write_immutable(home / "manifests" / manifest_name, manifest_bytes)
    _atomic_write(home / "current.json", _json_bytes({"schema_version": 1, "graph_id": graph_id, "manifest": manifest_name}))


class _SourceBudget:
    def __init__(self) -> None:
        self.used = 0

    def read_json(self, path: Path) -> Any:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_BYTES - self.used:
                raise TranscriptHistoryPending("transcript projection exceeds its source budget")
            chunks: list[bytes] = []
            remaining = info.st_size
            while remaining:
                chunk = os.read(descriptor, min(remaining, 64 * 1024))
                if not chunk:
                    raise TranscriptHistoryPending("transcript projection changed while reading")
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
        finally:
            os.close(descriptor)
        self.used += len(data)
        try:
            return json.loads(data)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise TranscriptHistoryPending("transcript projection is corrupt") from exc


def _load_projection(graph_id: str, *, root: Path, budget: _SourceBudget) -> tuple[Path, dict[str, Any]]:
    home = _projection_root(graph_id, root=root)
    try:
        pointer = budget.read_json(home / "current.json")
        name = pointer["manifest"]
        if pointer.get("graph_id") != graph_id or not isinstance(name, str):
            raise TranscriptHistoryPending("transcript projection identity does not match")
        if "/" in name or "\\" in name or not name.endswith(".json"):
            raise TranscriptHistoryPending("transcript manifest reference is unsafe")
        manifest = budget.read_json(home / "manifests" / name)
    except OSError as exc:
        raise TranscriptHistoryPending("transcript history is not published yet") from exc
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != 1
        or manifest.get("graph_id") != graph_id
        or not isinstance(manifest.get("incarnation"), str)
        or not isinstance(manifest.get("pages"), list)
    ):
        raise TranscriptHistoryPending("transcript manifest is incompatible")
    return home, manifest


def _encode_cursor(value: Mapping[str, Any]) -> str:
    return base64.urlsafe_b64encode(_json_bytes(value)).decode("ascii").rstrip("=")


def _decode_cursor(value: str) -> dict[str, Any]:
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
        decoded = json.loads(raw)
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranscriptInvalidRequest("invalid cursor") from exc
    if not isinstance(decoded, dict) or decoded.get("v") != 1:
        raise TranscriptInvalidRequest("invalid cursor")
    return decoded


def _page_cursor(graph_id: str, incarnation: str, direction: str, position: int, high_water: int) -> str:
    return _encode_cursor(
        {"v": 1, "kind": "page", "graph": graph_id, "incarnation": incarnation,
         "direction": direction, "sequence": position, "high_water": high_water}
    )


def _restart(graph_id: str, incarnation: str) -> TranscriptCursorRestart:
    return TranscriptCursorRestart(incarnation, f"/api/transcript/v1/{quote(graph_id, safe='')}")


def _read_items(
    home: Path,
    manifest: Mapping[str, Any],
    *,
    direction: str,
    position: int,
    limit: int,
    budget: _SourceBudget,
) -> list[dict[str, Any]]:
    page_specs = manifest["pages"]
    ordered = reversed(page_specs) if direction == "older" else iter(page_specs)
    selected: list[dict[str, Any]] = []
    for spec in ordered:
        if not isinstance(spec, dict):
            raise TranscriptHistoryPending("transcript page metadata is invalid")
        first = int(spec.get("first_sequence", -1))
        last = int(spec.get("last_sequence", -1))
        if direction == "older" and first > position:
            continue
        if direction == "after" and last <= position:
            continue
        name = spec.get("file")
        if not isinstance(name, str) or "/" in name or "\\" in name:
            raise TranscriptHistoryPending("transcript page reference is unsafe")
        try:
            page = budget.read_json(home / "pages" / name)
        except OSError as exc:
            raise TranscriptHistoryPending("a transcript page is unavailable") from exc
        if page.get("graph_id") != manifest["graph_id"] or page.get("incarnation") != manifest["incarnation"]:
            raise TranscriptHistoryPending("transcript page identity does not match")
        rows = page.get("items")
        if not isinstance(rows, list):
            raise TranscriptHistoryPending("transcript page rows are invalid")
        candidates = [dict(row) for row in rows if isinstance(row, dict)]
        if direction == "older":
            candidates = [row for row in candidates if int(row.get("append_sequence", -1)) <= position]
            selected = candidates + selected
            if len(selected) >= limit:
                return selected[-limit:]
        else:
            candidates = [row for row in candidates if int(row.get("append_sequence", -1)) > position]
            selected.extend(candidates)
            if len(selected) >= limit:
                return selected[:limit]
    return selected


def _public_item(graph_id: str, incarnation: str, item: dict[str, Any]) -> dict[str, Any]:
    digest = item.pop("detail_digest", None)
    if item.get("detail_truncated") is True and isinstance(digest, str):
        message_id = item.get("id")
        if not isinstance(message_id, str):
            raise TranscriptHistoryPending("truncated transcript item has no identity")
        cursor = _encode_cursor(
            {"v": 1, "kind": "detail", "graph": graph_id, "incarnation": incarnation,
             "message": message_id, "digest": digest, "offset": 0}
        )
        item["detail_cursor"] = cursor
        item["detail_url"] = (
            f"/api/transcript/v1/{quote(graph_id, safe='')}/items/"
            f"{quote(message_id, safe='')}/detail?cursor={quote(cursor, safe='')}"
        )
    return item


def read_transcript_page(
    graph_id: str,
    *,
    root: Path,
    direction: str = "older",
    cursor: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> TranscriptPageResult:
    if direction not in {"older", "after"}:
        raise TranscriptInvalidRequest("direction must be older or after")
    if isinstance(limit, bool) or limit < 1 or limit > MAX_LIMIT:
        raise TranscriptInvalidRequest("limit must be between 1 and 100")
    decoded: dict[str, Any] | None = None
    if cursor is not None:
        decoded = _decode_cursor(cursor)
        if decoded.get("kind") != "page" or decoded.get("graph") != graph_id:
            raise TranscriptInvalidRequest("cursor does not belong to this graph")
        if decoded.get("direction") != direction:
            raise TranscriptInvalidRequest("cursor direction does not match the request")
    budget = _SourceBudget()
    home, manifest = _load_projection(graph_id, root=root, budget=budget)
    incarnation = manifest["incarnation"]
    current_high = int(manifest.get("high_water_mark", 0))
    first_sequence = int(manifest.get("first_sequence", 0))
    requested_direction = direction
    if cursor is None:
        effective_direction = "older"
        position = current_high
        high_water = current_high
    else:
        assert decoded is not None
        if decoded.get("incarnation") != incarnation:
            raise _restart(graph_id, incarnation)
        try:
            position = int(decoded["sequence"])
            high_water = int(decoded["high_water"])
        except (KeyError, TypeError, ValueError) as exc:
            raise TranscriptInvalidRequest("invalid cursor") from exc
        if position < 0 or high_water < 0 or high_water > current_high or position > high_water:
            raise _restart(graph_id, incarnation)
        effective_direction = direction
    items = _read_items(
        home, manifest, direction=effective_direction, position=position, limit=limit, budget=budget
    )
    items = [_public_item(graph_id, incarnation, item) for item in items]

    def build(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
        start = int(rows[0]["append_sequence"]) if rows else position
        end = int(rows[-1]["append_sequence"]) if rows else position
        older_position = start - 1
        older_more = bool(rows) and first_sequence > 0 and start > first_sequence
        after_position = end if effective_direction == "after" else high_water
        after_more = current_high > after_position
        return {
            "schema_version": 1,
            "graph_id": graph_id,
            "incarnation": incarnation,
            "high_water_mark": current_high if effective_direction == "after" else high_water,
            "completeness": manifest.get("completeness", "pending"),
            "observed_at": manifest.get("observed_at"),
            "items": list(rows),
            "older_cursor": _page_cursor(graph_id, incarnation, "older", older_position, high_water) if older_more else None,
            "after_cursor": _page_cursor(graph_id, incarnation, "after", after_position, current_high),
            "has_more": after_more if requested_direction == "after" and cursor is not None else older_more,
        }

    payload = build(items)
    serialized = _json_bytes(payload)
    while items and len(serialized) > MAX_RESPONSE_BYTES:
        if effective_direction == "older":
            items.pop(0)
        else:
            items.pop()
        payload = build(items)
        serialized = _json_bytes(payload)
    if len(serialized) > MAX_RESPONSE_BYTES:
        raise TranscriptHistoryPending("transcript response metadata exceeds its budget")
    return TranscriptPageResult(payload, serialized)


def read_transcript_detail(
    graph_id: str,
    message_id: str,
    *,
    root: Path,
    cursor: str,
) -> TranscriptPageResult:
    decoded = _decode_cursor(cursor)
    if (
        decoded.get("kind") != "detail"
        or decoded.get("graph") != graph_id
        or decoded.get("message") != message_id
    ):
        raise TranscriptInvalidRequest("detail cursor does not belong to this message")
    budget = _SourceBudget()
    home, manifest = _load_projection(graph_id, root=root, budget=budget)
    incarnation = manifest["incarnation"]
    if decoded.get("incarnation") != incarnation:
        raise _restart(graph_id, incarnation)
    digest = decoded.get("digest")
    try:
        offset = int(decoded["offset"])
    except (KeyError, TypeError, ValueError) as exc:
        raise TranscriptInvalidRequest("invalid detail cursor") from exc
    if (
        not isinstance(digest, str)
        or len(digest) != 64
        or any(char not in "0123456789abcdef" for char in digest)
        or offset < 0
    ):
        raise TranscriptInvalidRequest("invalid detail cursor")
    details = manifest.get("details")
    if not isinstance(details, dict) or details.get(message_id) != digest:
        raise _restart(graph_id, incarnation)
    path = home / "details" / f"{digest}.txt"
    try:
        descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise TranscriptHistoryPending("transcript detail is unavailable") from exc
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or offset > info.st_size:
            raise TranscriptHistoryPending("transcript detail is unavailable")
        remaining_budget = MAX_SOURCE_BYTES - budget.used
        if remaining_budget <= 0:
            raise TranscriptHistoryPending("transcript detail exceeds its source budget")
        raw = os.pread(descriptor, min(DETAIL_CHUNK_BYTES, remaining_budget), offset)
        budget.used += len(raw)
    finally:
        os.close(descriptor)
    if raw and raw[0] & 0xC0 == 0x80:
        raise TranscriptInvalidRequest("detail cursor offset is not a UTF-8 boundary")
    while raw:
        try:
            chunk = raw.decode("utf-8")
            break
        except UnicodeDecodeError as exc:
            raw = raw[: exc.start]
    else:
        chunk = ""
    next_offset = offset + len(raw)
    complete = next_offset >= info.st_size
    next_cursor = None
    if not complete:
        next_cursor = _encode_cursor(
            {"v": 1, "kind": "detail", "graph": graph_id, "incarnation": incarnation,
             "message": message_id, "digest": digest, "offset": next_offset}
        )
    payload = {
        "schema_version": 1,
        "graph_id": graph_id,
        "message_id": message_id,
        "incarnation": incarnation,
        "encoding": "utf-8",
        "chunk": chunk,
        "next_cursor": next_cursor,
        "complete": complete,
    }
    serialized = _json_bytes(payload)
    if len(serialized) > MAX_RESPONSE_BYTES:
        raise TranscriptHistoryPending("transcript detail response exceeds its budget")
    return TranscriptPageResult(payload, serialized)


__all__ = [
    "DEFAULT_LIMIT", "MAX_LIMIT", "TranscriptCursorRestart", "TranscriptHistoryPending",
    "TranscriptInvalidRequest", "TranscriptPageResult", "invalidate_transcript_projection",
    "publish_transcript_projection", "read_transcript_detail", "read_transcript_page",
]
