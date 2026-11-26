"""Append-only human chat sidecars per persisting graph id."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, Mapping

from cascade.board.context import resolve_root, resolve_tracking_root
from cascade.board.errors import NotFound, SchemaError
from cascade.board.parse import parse_doc
from cascade.board.types import WorkMeta
from cascade.workspace.doc_root import read_doc_resolved, resolve_doc_worktree
from cascade.workspace.integration_worktree import load_registry, locate_trunk
from cascade.watchdog.lock import process_lock

_CHAT_DIR = Path("docs") / "_war_room" / "chat"
_INDEX_DIR = Path(".cascade") / "transcript_index"
_IMPORT_BYTES = 1024 * 1024
_IMPORT_ROWS = 100
_thread_locks_guard = threading.Lock()
_thread_locks: dict[Path, threading.RLock] = {}


class TranscriptPendingError(RuntimeError):
    """The authoritative JSONL cannot be changed without guessing."""


def _runtime_root(root: Path) -> Path:
    return locate_trunk(resolve_tracking_root(root)).resolve()


def _store_key(graph_id: str) -> str:
    return hashlib.sha256(graph_id.encode("utf-8")).hexdigest()


def _index_path(graph_id: str, *, root: Path) -> Path:
    return _runtime_root(root) / _INDEX_DIR / f"{_store_key(graph_id)}.sqlite"


@contextmanager
def graph_transcript_fence(graph_id: str, *, root: Path) -> Iterator[None]:
    """Take the stable tracking-root OS fence for one graph transcript."""

    if not graph_id_is_valid(graph_id):
        raise ValueError(f"invalid graph_id: {graph_id!r}")
    home = _runtime_root(root) / _INDEX_DIR
    home.mkdir(parents=True, exist_ok=True)
    lock_path = home / f"{_store_key(graph_id)}.lock"
    with _thread_locks_guard:
        thread_lock = _thread_locks.setdefault(lock_path, threading.RLock())
    with thread_lock:
        with lock_path.open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _connect_index(graph_id: str, *, root: Path) -> sqlite3.Connection:
    path = _index_path(graph_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS state (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            incarnation TEXT NOT NULL,
            room_path TEXT,
            indexed_end INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS events (
            append_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id TEXT NOT NULL UNIQUE,
            source_key TEXT UNIQUE,
            byte_offset INTEGER NOT NULL,
            byte_length INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS events_offset
            ON events(byte_offset);
        CREATE TABLE IF NOT EXISTS pending_intent (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            room_path TEXT NOT NULL,
            expected_offset INTEGER NOT NULL,
            line BLOB NOT NULL,
            digest TEXT NOT NULL,
            message_id TEXT NOT NULL,
            source_key TEXT
        );
        CREATE TABLE IF NOT EXISTS legacy_import_buffer (
            singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
            start_offset INTEGER NOT NULL,
            data BLOB NOT NULL
        );
        """
    )
    connection.execute(
        "INSERT OR IGNORE INTO state(singleton, incarnation) VALUES (1, ?)",
        (uuid.uuid4().hex,),
    )
    connection.commit()
    return connection


def _fsync_parent(path: Path) -> None:
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _append_and_fsync(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    created = not path.exists()
    with path.open("ab", buffering=0) as handle:
        remaining = memoryview(payload)
        while remaining:
            written = handle.write(remaining)
            if written is None or written <= 0:
                raise OSError("transcript append made no progress")
            remaining = remaining[written:]
        os.fsync(handle.fileno())
    if created:
        _fsync_parent(path)


def _copy_and_fsync(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        with source.open("rb") as reader, temporary.open("wb") as writer:
            shutil.copyfileobj(reader, writer, length=1024 * 1024)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(temporary, destination)
        _fsync_parent(destination)
    finally:
        temporary.unlink(missing_ok=True)


def _reset_room_index(
    connection: sqlite3.Connection, path: Path, *, change_incarnation: bool
) -> None:
    connection.execute("DELETE FROM events")
    connection.execute("DELETE FROM pending_intent")
    connection.execute("DELETE FROM legacy_import_buffer")
    if change_incarnation:
        connection.execute(
            """UPDATE state SET incarnation = ?, indexed_end = 0, room_path = ?
               WHERE singleton = 1""",
            (uuid.uuid4().hex, str(path.resolve())),
        )
    else:
        connection.execute(
            "UPDATE state SET indexed_end = 0, room_path = ? WHERE singleton = 1",
            (str(path.resolve()),),
        )
    connection.commit()


def _same_file_bytes(left: Path, right: Path) -> bool:
    if left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as first, right.open("rb") as second:
        while True:
            a = first.read(1024 * 1024)
            b = second.read(1024 * 1024)
            if a != b:
                return False
            if not a:
                return True


def move_transcript_room(
    graph_id: str,
    *,
    source_root: Path,
    destination_root: Path,
    root: Path,
    switch_owner: Callable[[], None] | None = None,
) -> None:
    """Copy committed history and switch its room incarnation under the fence.

    ``switch_owner`` lets lifecycle routing publish its registry change inside
    the same graph critical section. A matching destination is retry-safe;
    conflicting bytes remain untouched and fail pending.
    """

    source = _sidecar_path(source_root.resolve(), graph_id)
    destination = _sidecar_path(destination_root.resolve(), graph_id)
    with graph_transcript_fence(graph_id, root=root):
        connection = _connect_index(graph_id, root=root)
        try:
            _repair_pending(connection, source)
            if source.is_file():
                if destination.is_file():
                    if not _same_file_bytes(source, destination):
                        raise TranscriptPendingError(
                            "destination room contains unrelated transcript bytes"
                        )
                else:
                    _copy_and_fsync(source, destination)
            elif destination.is_file():
                state = connection.execute(
                    "SELECT room_path FROM state WHERE singleton = 1"
                ).fetchone()
                if state["room_path"] not in (None, str(destination.resolve())):
                    raise TranscriptPendingError("room movement has an uncertain source")
            state = connection.execute(
                "SELECT room_path FROM state WHERE singleton = 1"
            ).fetchone()
            changing_room = state["room_path"] != str(destination.resolve())
            source_removed = False
            if source != destination and source.is_file():
                source.unlink()
                _fsync_parent(source)
                source_removed = True
            try:
                if switch_owner is not None:
                    switch_owner()
            except BaseException:
                if source_removed and source.parent.is_dir() and destination.is_file():
                    _copy_and_fsync(destination, source)
                raise
            if changing_room:
                _reset_room_index(connection, destination, change_incarnation=True)
                _import_legacy(connection, destination)
        finally:
            connection.close()


def _commit_intent(connection: sqlite3.Connection, intent: sqlite3.Row) -> None:
    connection.execute(
        """INSERT INTO events
           (message_id, source_key, byte_offset, byte_length)
           VALUES (?, ?, ?, ?)""",
        (
            intent["message_id"],
            intent["source_key"],
            intent["expected_offset"],
            len(intent["line"]),
        ),
    )
    connection.execute(
        "UPDATE state SET indexed_end = ? WHERE singleton = 1",
        (intent["expected_offset"] + len(intent["line"]),),
    )
    connection.execute("DELETE FROM pending_intent WHERE singleton = 1")
    connection.commit()


def _read_indexed_message(path: Path, event: sqlite3.Row) -> dict:
    with path.open("rb") as handle:
        handle.seek(int(event["byte_offset"]))
        raw = handle.read(int(event["byte_length"]))
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TranscriptPendingError("indexed transcript bytes are unreadable") from exc
    if not isinstance(value, dict) or value.get("id") != event["message_id"]:
        raise TranscriptPendingError("indexed transcript message identity does not match")
    return value


def _repair_pending(connection: sqlite3.Connection, path: Path) -> None:
    intent = connection.execute(
        "SELECT * FROM pending_intent WHERE singleton = 1"
    ).fetchone()
    if intent is None:
        return
    if intent["room_path"] != str(path.resolve()):
        raise TranscriptPendingError("pending transcript intent has an uncertain owner")
    expected = int(intent["expected_offset"])
    line = bytes(intent["line"])
    size = path.stat().st_size if path.is_file() else 0
    if size < expected or size > expected + len(line):
        raise TranscriptPendingError("unexpected bytes follow the pending transcript intent")
    present = b""
    if size > expected:
        with path.open("rb") as handle:
            handle.seek(expected)
            present = handle.read(size - expected)
        if not line.startswith(present):
            raise TranscriptPendingError("the pending transcript tail does not match its intent")
    if hashlib.sha256(line).hexdigest() != intent["digest"]:
        raise TranscriptPendingError("the pending transcript intent digest is invalid")
    if size < expected + len(line):
        _append_and_fsync(path, line[len(present) :])
    _commit_intent(connection, intent)


def _import_legacy(
    connection: sqlite3.Connection, path: Path, *, byte_limit: int = _IMPORT_BYTES,
    row_limit: int = _IMPORT_ROWS,
) -> bool:
    """Index a bounded complete-line prefix without changing authoritative JSONL."""

    state = connection.execute("SELECT indexed_end FROM state WHERE singleton = 1").fetchone()
    offset = int(state["indexed_end"])
    size = path.stat().st_size if path.is_file() else 0
    if offset > size:
        raise TranscriptPendingError("transcript JSONL is shorter than its committed index")
    if offset == size:
        return True
    source_read = 0
    rows = 0
    buffered = connection.execute(
        "SELECT start_offset, data FROM legacy_import_buffer WHERE singleton = 1"
    ).fetchone()
    if buffered is not None and int(buffered["start_offset"]) != offset:
        raise TranscriptPendingError("legacy import buffer does not match indexed end")
    line_prefix = bytes(buffered["data"]) if buffered is not None else b""
    with path.open("rb") as handle:
        while source_read < byte_limit and rows < row_limit:
            start = offset
            position = start + len(line_prefix)
            if position > size:
                raise TranscriptPendingError("legacy transcript changed during import")
            handle.seek(position)
            chunk = handle.readline(min(byte_limit - source_read, size - position))
            if not chunk:
                break
            newline = chunk.find(b"\n")
            if newline < 0:
                line_prefix += chunk
                source_read += len(chunk)
                connection.execute(
                    """INSERT INTO legacy_import_buffer(singleton, start_offset, data)
                       VALUES (1, ?, ?)
                       ON CONFLICT(singleton) DO UPDATE SET data = excluded.data""",
                    (start, line_prefix),
                )
                connection.commit()
                return False
            fragment = chunk[: newline + 1]
            line = line_prefix + fragment
            source_read += len(fragment)
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise TranscriptPendingError("legacy transcript contains an invalid line") from exc
            if not isinstance(value, dict) or not isinstance(value.get("id"), str):
                raise TranscriptPendingError("legacy transcript line has no durable message id")
            try:
                connection.execute(
                    """INSERT INTO events
                       (message_id, source_key, byte_offset, byte_length)
                       VALUES (?, NULL, ?, ?)""",
                    (value["id"], start, len(line)),
                )
            except sqlite3.IntegrityError as exc:
                raise TranscriptPendingError("legacy transcript repeats a message id") from exc
            offset += len(line)
            rows += 1
            line_prefix = b""
            connection.execute("DELETE FROM legacy_import_buffer WHERE singleton = 1")
            connection.execute(
                "UPDATE state SET indexed_end = ? WHERE singleton = 1", (offset,)
            )
            connection.commit()
    return offset == size and not line_prefix


def graph_id_is_valid(graph_id: str) -> bool:
    if not graph_id or "/" in graph_id or "\\" in graph_id or graph_id in {".", ".."}:
        return False
    return True


def _sidecar_path(root: Path, graph_id: str) -> Path:
    if not graph_id_is_valid(graph_id):
        raise ValueError(f"invalid graph_id: {graph_id!r}")
    return root / _CHAT_DIR / f"{graph_id}.jsonl"


def read_messages(graph_id: str, *, root: Path) -> list[dict]:
    """Return all messages for ``graph_id`` (empty if sidecar missing)."""

    path = _chat_read_path(graph_id, root=root)
    with process_lock:
        if not path.is_file():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
    out: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def append_transcript_message(
    graph_id: str,
    *,
    author: str,
    body: str,
    root: Path,
    message_id: str | None = None,
    source_key: str | None = None,
    occurred_at: str | None = None,
    provenance: str = "direct",
    metadata: Mapping[str, object] | None = None,
) -> dict:
    """Durably append one deduplicated line to the authoritative JSONL.

    The return happens after the graph fence is released, so callers may treat
    it as acknowledgement that the exact line and its index record are durable.
    """

    if _is_task_tier(graph_id, root=root):
        raise TaskTierChatError(graph_id)
    text = body.strip()
    if not text:
        raise ValueError("empty body")
    durable_id = message_id or uuid.uuid4().hex
    now = datetime.now(timezone.utc).isoformat()
    message: dict[str, object] = {
        "id": durable_id,
        "graph_id": graph_id,
        "author": author,
        "body": text,
        "ts": now,
    }
    if source_key is not None or occurred_at is not None or metadata:
        message.update(
            {
                "event_schema_version": 1,
                "source_key": source_key,
                "occurred_at": occurred_at,
                "appended_at": now,
                "provenance": provenance,
            }
        )
        if metadata:
            reserved = set(message).intersection(metadata)
            if reserved:
                raise ValueError(
                    f"metadata cannot replace transcript fields: {', '.join(sorted(reserved))}"
                )
            message.update(metadata)
    line = (json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    with graph_transcript_fence(graph_id, root=root):
        repo = _chat_repo(graph_id, root=root)
        path = _sidecar_path(repo, graph_id)
        connection = _connect_index(graph_id, root=root)
        try:
            _repair_pending(connection, path)
            state = connection.execute(
                "SELECT room_path FROM state WHERE singleton = 1"
            ).fetchone()
            current_room = str(path.resolve())
            if state["room_path"] not in (None, current_room):
                raise TranscriptPendingError("transcript index belongs to another room incarnation")
            connection.execute(
                "UPDATE state SET room_path = ? WHERE singleton = 1", (current_room,)
            )
            connection.commit()
            if not _import_legacy(connection, path):
                raise TranscriptPendingError("legacy transcript import is incomplete; retry")
            existing = connection.execute(
                """SELECT message_id, byte_offset, byte_length FROM events
                   WHERE message_id = ? OR (? IS NOT NULL AND source_key = ?)""",
                (durable_id, source_key, source_key),
            ).fetchone()
            if existing is not None:
                return _read_indexed_message(path, existing)
            expected = path.stat().st_size if path.is_file() else 0
            digest = hashlib.sha256(line).hexdigest()
            connection.execute(
                """INSERT INTO pending_intent
                   (singleton, room_path, expected_offset, line, digest, message_id, source_key)
                   VALUES (1, ?, ?, ?, ?, ?, ?)""",
                (current_room, expected, line, digest, durable_id, source_key),
            )
            connection.commit()
            _append_and_fsync(path, line)
            intent = connection.execute(
                "SELECT * FROM pending_intent WHERE singleton = 1"
            ).fetchone()
            _commit_intent(connection, intent)
        finally:
            connection.close()
    return message


def append_message(graph_id: str, body: str, *, root: Path) -> dict:
    """Append one human message; return the stored message dict."""

    if _is_task_tier(graph_id, root=root):
        raise TaskTierChatError(graph_id)
    text = body.strip()
    if not text:
        raise ValueError("empty body")
    return append_transcript_message(graph_id, author="human", body=text, root=root)


def remove_message(graph_id: str, message_id: str, *, root: Path) -> None:
    """Drop one message from the sidecar by id (e.g. rollback after failed graph ingest)."""

    with graph_transcript_fence(graph_id, root=root):
        repo = _chat_repo(graph_id, root=root)
        path = _sidecar_path(repo, graph_id)
        connection = _connect_index(graph_id, root=root)
        try:
            _repair_pending(connection, path)
            if not _import_legacy(connection, path):
                raise TranscriptPendingError("legacy transcript import is incomplete; retry")
        finally:
            connection.close()
        if not path.is_file():
            return
        kept: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            try:
                row = json.loads(stripped)
            except json.JSONDecodeError:
                kept.append(stripped)
                continue
            if isinstance(row, dict) and row.get("id") == message_id:
                continue
            kept.append(stripped)
        if kept:
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            with temporary.open("w", encoding="utf-8") as handle:
                handle.write("\n".join(kept) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            _fsync_parent(path)
        else:
            path.unlink(missing_ok=True)
            _fsync_parent(path)
        connection = _connect_index(graph_id, root=root)
        try:
            connection.execute("DELETE FROM events")
            connection.execute("DELETE FROM pending_intent")
            connection.execute("DELETE FROM legacy_import_buffer")
            connection.execute(
                """UPDATE state SET incarnation = ?, indexed_end = 0, room_path = ?
                   WHERE singleton = 1""",
                (uuid.uuid4().hex, str(path.resolve())),
            )
            connection.commit()
            _import_legacy(connection, path)
        finally:
            connection.close()


class TaskTierChatError(Exception):
    def __init__(self, graph_id: str) -> None:
        self.graph_id = graph_id
        super().__init__(graph_id)


def _chat_repo(graph_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_root(root))
    try:
        repo = resolve_doc_worktree(graph_id, root=trunk)
    except NotFound:
        return trunk
    # The remote backlog snapshot is a read-only view. Chat sidecars belong
    # to the local workspace so refreshes cannot overwrite operator history.
    from cascade.workspace.backlog_snapshot import snapshot_root

    if repo.resolve().is_relative_to(snapshot_root(trunk).resolve()):
        return trunk
    return repo


def _chat_read_path(graph_id: str, *, root: Path) -> Path:
    """Resolve an existing chat sidecar without constructing the merged board.

    Chat GET is a frequent poll.  ``resolve_doc_worktree`` is appropriate for
    mutations, where the current plan owner must be established authoritatively,
    but it used to make every poll parse every plan in every registered checkout.
    The registry and one ID-specific plan lookup contain enough routing
    information for a read.
    """

    trunk = locate_trunk(resolve_root(root))
    trunk_meta = _direct_doc_meta(graph_id, root=trunk)

    # A closed epic's trunk copy is authoritative even while conservative
    # worktree cleanup leaves the old registration in place.
    if (
        trunk_meta is not None
        and trunk_meta.tier == "epic"
        and trunk_meta.status == "completed"
        and trunk_meta.path.parent.name == "3_completed"
    ):
        return _sidecar_path(trunk, graph_id)

    entries = load_registry(trunk)
    expected_kind = "epic" if graph_id.startswith("epic_") else "feature"
    for entry in entries:
        if entry.kind == expected_kind and entry.work_id == graph_id:
            # Match resolve_doc_worktree: a registered epic/feature owns its
            # room even before the first message creates a sidecar.
            return _sidecar_path(entry.path, graph_id)

    if graph_id.startswith("feat_"):
        # Before feature dispatch, its room belongs to the parent epic. Prefer
        # the epic checkout that actually contains the feature plan.
        for entry in entries:
            if entry.kind != "epic" or not entry.path.is_dir():
                continue
            if _direct_doc_meta(graph_id, root=entry.path) is not None:
                return _sidecar_path(entry.path, graph_id)

        # A newly drafted feature can still be trunk-only while its parent epic
        # is active. Its parent field routes the room without a board-wide scan.
        if trunk_meta is not None and trunk_meta.parent:
            for entry in entries:
                if entry.kind == "epic" and entry.work_id == trunk_meta.parent:
                    return _sidecar_path(entry.path, graph_id)

    if graph_id.startswith("task_"):
        # Task chat is rejected by the API, but preserve historical read routing.
        # Normally the task plan itself is already in its feature checkout.
        for entry in entries:
            if entry.kind != "feature" or not entry.path.is_dir():
                continue
            if _direct_doc_meta(graph_id, root=entry.path) is not None:
                return _sidecar_path(entry.path, graph_id)
        # A trunk-only task follows its parent feature's registered checkout.
        if trunk_meta is not None and trunk_meta.parent:
            for entry in entries:
                if entry.kind == "feature" and entry.work_id == trunk_meta.parent:
                    return _sidecar_path(entry.path, graph_id)

    return _sidecar_path(trunk, graph_id)


def _direct_doc_meta(work_id: str, *, root: Path) -> WorkMeta | None:
    """Read only the plan whose filename encodes ``work_id`` in one checkout."""

    if work_id.startswith("epic_"):
        tier_dir = "epics"
    elif work_id.startswith("feat_"):
        tier_dir = "features"
    elif work_id.startswith("task_"):
        tier_dir = "tasks"
    else:
        return None
    for column in ("2_active", "3_completed", "1_backlog"):
        directory = root / "docs" / tier_dir / column
        candidates = [directory / f"{work_id}.md"]
        candidates.extend(sorted(directory.glob(f"{work_id}_*.md")))
        for path in candidates:
            if not path.is_file() or path.is_symlink():
                continue
            try:
                meta = parse_doc(path).meta
            except (OSError, UnicodeDecodeError, SchemaError):
                continue
            if meta.id == work_id:
                return meta
    return None


def _is_task_tier(graph_id: str, *, root: Path) -> bool:
    trunk = locate_trunk(resolve_root(root))
    try:
        doc = read_doc_resolved(graph_id, root=trunk)
    except NotFound:
        return False
    return doc.meta.tier == "task"
