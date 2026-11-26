"""Bounded, evidence-based materialization of current recovery progress.

The action and incident ledgers are authoritative.  This module maintains a
disposable writer-only index so committed receipts can be replayed fairly and
publishes immutable, work-addressed JSON pages for later read-only consumers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import stat
import tempfile
import threading
import time
import uuid
from collections.abc import Iterable, Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from cascade.board.context import (
    get_project_context,
    resolve_root,
    resolve_tracking_root,
)
from cascade.recovery_progress.live import (
    refresh_live_observation,
    registered_live_observations,
)
from cascade.task.lifecycle_lock import lifecycle_root, task_lifecycle_read_lock
from cascade.watchdog.audit_lane import canonical_audit_root

SCHEMA_VERSION = 1
MAX_RECEIPTS_PER_PASS = 100
MAX_OWNERS_PER_PASS = 100
MAX_PASS_SECONDS = 1.0
FAST_PATH_SECONDS = 0.250
PAGE_ROWS = 50
MAX_SAFE_TEXT = 240

_STATE_PRIORITY = {
    "waiting_blocked": 0,
    "exhausted": 0,
    "retryable_failed": 1,
    "executing": 1,
    "investigating": 1,
    "acknowledged": 1,
    "requested_queued": 1,
    "verification_pending": 1,
    "stale_unavailable": 1,
    "verified_complete": 2,
}
_SAFE_TEXT = re.compile(r"[^A-Za-z0-9 _./:@+\-=#]", re.ASCII)
_SOURCE_SPECS = (
    ("action_recovery", "executions.json", "actions"),
    ("orphan_delivery", "orphan_delivery_recoveries.json", "recoveries"),
    ("remediation_dispositions", "remediation_dispositions.json", "dispositions"),
)
_writer_lock = threading.RLock()
_installed_roots: set[Path] = set()
_PRODUCER_RUNTIME = {
    "process_token": uuid.uuid4().hex,
    "pid": os.getpid(),
    "started_at": datetime.now(timezone.utc).isoformat(),
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_time(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _safe_text(value: object, *, target: bool = False) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())[:MAX_SAFE_TEXT]
    cleaned = _SAFE_TEXT.sub("?", cleaned)
    if not cleaned:
        return None
    if target:
        if cleaned in {"main", "master", "product_trunk", "human", "watchdog"}:
            return cleaned
        if ".." in cleaned or not re.fullmatch(
            r"(?:task|feat|epic)[_/][A-Za-z0-9_.-]+", cleaned
        ):
            return None
    return cleaned


def _work_hash(work_id: str) -> str:
    return hashlib.sha256(work_id.encode()).hexdigest()


def _base(root: Path) -> Path:
    return (
        canonical_audit_root(resolve_root(root))
        / ".cascade"
        / "recovery_progress"
        / "v1"
    )


def _repository_identities(root: Path) -> tuple[str, str]:
    product = canonical_audit_root(root)
    project = get_project_context()
    if project is not None and product == project.target.root.resolve():
        return str(project.target.repository_key), str(project.tracking.repository_key)
    tracking = resolve_tracking_root(product)
    return (
        "repository-" + hashlib.sha256(product.as_uri().encode()).hexdigest()[:24],
        "repository-" + hashlib.sha256(tracking.as_uri().encode()).hexdigest()[:24],
    )


def _connect(root: Path) -> sqlite3.Connection:
    base = _base(root)
    base.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(base / "writer-index.sqlite3", timeout=0.1)
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        PRAGMA journal_mode=WAL;
        PRAGMA synchronous=NORMAL;
        CREATE TABLE IF NOT EXISTS receipts (
            receipt_id TEXT PRIMARY KEY,
            source_kind TEXT NOT NULL,
            source_key TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            imported_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS entries (
            entry_id TEXT PRIMARY KEY,
            entry_revision TEXT NOT NULL,
            action_id TEXT NOT NULL,
            generation TEXT NOT NULL,
            attempt_number INTEGER,
            state TEXT NOT NULL,
            blocker_priority INTEGER NOT NULL,
            material_at TEXT,
            payload TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS aliases (
            work_id TEXT NOT NULL,
            entry_id TEXT NOT NULL,
            PRIMARY KEY (work_id, entry_id)
        );
        CREATE TABLE IF NOT EXISTS dirty (work_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS transcript_milestones (
            receipt_id TEXT PRIMARY KEY,
            entry_id TEXT NOT NULL,
            graph_id TEXT NOT NULL,
            message_id TEXT NOT NULL,
            incarnation TEXT NOT NULL,
            append_sequence INTEGER NOT NULL,
            recorded_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        """
    )
    return connection


def _canonical_action_id(
    receipt: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> str:
    authoritative = (
        snapshot.get("incident")
        if isinstance(snapshot.get("incident"), Mapping)
        else snapshot
    )
    request = (
        authoritative.get("request") if isinstance(authoritative, Mapping) else None
    )
    original = request.get("original_action") if isinstance(request, Mapping) else None
    action_id = original.get("action_id") if isinstance(original, Mapping) else None
    return str(
        action_id or receipt.get("action_id") or receipt.get("source_key") or "unknown"
    )


def _entry_id(receipt: Mapping[str, Any], snapshot: Mapping[str, Any]) -> str:
    identity = {
        "action_id": _canonical_action_id(receipt, snapshot),
        "generation": receipt.get("generation"),
        "attempt_number": receipt.get("attempt_number"),
    }
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _matching_live(
    receipt: Mapping[str, Any], *, action_id: str, now: datetime
) -> tuple[str, Any | None]:
    matches = []
    conflicts = False
    for observation in registered_live_observations():
        identity = observation.identity
        if identity.action_id != action_id:
            continue
        exact = (
            identity.action_generation == receipt.get("generation")
            and identity.attempt_number == receipt.get("attempt_number")
            and identity.claim_id == receipt.get("claim_id")
        )
        if not exact:
            conflicts = True
            continue
        result = refresh_live_observation(identity, now=now)
        if result.state == "live":
            matches.append(result.observation)
        elif result.state == "unknown":
            return "unknown", result.observation
    if matches:
        matches.sort(
            key=lambda item: (
                item.identity.kind == "executor",
                item.observed_at,
            ),
            reverse=True,
        )
        return "live", matches[0]
    return ("conflicting" if conflicts else "absent"), None


def _postcheck_verified(
    snapshot: Mapping[str, Any], generation: object
) -> tuple[bool, str | None]:
    result = snapshot.get("result")
    postcheck = result.get("postcheck") if isinstance(result, Mapping) else None
    if not isinstance(postcheck, Mapping):
        return False, None
    same_generation = postcheck.get("generation") == generation
    verified = postcheck.get("verified") is True and same_generation
    reference = postcheck.get("verification_reference") or postcheck.get("reference")
    if reference is None and verified:
        reference = generation
    return verified, _safe_text(reference)


def _attempts(snapshot: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    value = snapshot.get("attempts")
    return (
        [item for item in value if isinstance(item, Mapping)]
        if isinstance(value, list)
        else []
    )


def _has_timestamped_acknowledgement(
    receipt: Mapping[str, Any], authoritative: Mapping[str, Any]
) -> bool:
    if (
        receipt.get("transition_kind") == "acknowledged"
        and _parse_time(receipt.get("occurred_at")) is not None
    ):
        return True
    acknowledgement = authoritative.get("acknowledgement")
    if not isinstance(acknowledgement, Mapping):
        return False
    candidates = [
        acknowledgement.get(key)
        for key in ("acknowledged_at", "claimed_at", "observed_at", "at")
    ]
    execution_claim = acknowledgement.get("execution_claim")
    if isinstance(execution_claim, Mapping):
        candidates.extend(
            execution_claim.get(key)
            for key in ("acknowledged_at", "claimed_at", "observed_at", "at")
        )
    return any(_parse_time(value) is not None for value in candidates)


def _derive_entry(
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    now: datetime,
) -> dict[str, Any]:
    transition = str(receipt.get("transition_kind") or "")
    generation = receipt.get("generation")
    action_id = _canonical_action_id(receipt, snapshot)
    authoritative = (
        snapshot.get("incident")
        if isinstance(snapshot.get("incident"), Mapping)
        else snapshot
    )
    attempts = _attempts(snapshot) or _attempts(authoritative)
    latest_attempt = attempts[-1] if attempts else {}
    safe_payload = (
        receipt.get("safe_payload")
        if isinstance(receipt.get("safe_payload"), Mapping)
        else {}
    )
    recovery = (
        snapshot.get("recovery")
        if isinstance(snapshot.get("recovery"), Mapping)
        else {}
    )
    evidence = (
        snapshot.get("evidence")
        if isinstance(snapshot.get("evidence"), Mapping)
        else {}
    )
    if not evidence and isinstance(recovery.get("evidence"), Mapping):
        evidence = recovery["evidence"]
    if not evidence and isinstance(authoritative.get("evidence"), Mapping):
        evidence = authoritative["evidence"]
    owning_team = recovery.get("owning_team")
    owner = snapshot.get("accountable_owner") or authoritative.get("accountable_owner")
    if owner is None and isinstance(owning_team, Mapping):
        owner = owning_team.get("work_id")
    owner = _safe_text(owner) or "unknown"
    live_state, live = _matching_live(receipt, action_id=action_id, now=now)
    verified, verification_ref = _postcheck_verified(authoritative, generation)
    outcome = (
        authoritative.get("outcome")
        or snapshot.get("outcome")
        or latest_attempt.get("outcome")
    )
    recovery_state = snapshot.get("recovery_state") or safe_payload.get(
        "recovery_state"
    )
    policy = (
        authoritative.get("retry_policy")
        if isinstance(authoritative.get("retry_policy"), Mapping)
        else {}
    )
    attempt_bound = int(
        policy.get("attempt_bound") or snapshot.get("attempt_bound") or 0
    )
    prerequisite = (
        evidence.get("prerequisite")
        or evidence.get("gate")
        or evidence.get("reason")
        or safe_payload.get("prerequisite")
    )
    safe_reason = _safe_text(
        prerequisite
        or snapshot.get("failure_class")
        or latest_attempt.get("classification")
        or safe_payload.get("reason")
    )

    if verified:
        state = "verified_complete"
    elif (
        outcome == "success"
        or latest_attempt.get("outcome") == "succeeded"
        or recovery_state in {"completed", "repaired"}
    ):
        state = "verification_pending"
    elif (
        prerequisite is not None
        and owner != "unknown"
        and (
            transition == "waiting"
            or recovery_state
            in {"awaiting_owner_decision", "awaiting_human_gate", "blocked"}
        )
    ):
        state = "waiting_blocked"
    elif outcome in {"error", "refused", "unsafe"} or latest_attempt.get("outcome") in {
        "failed",
        "cancelled",
    }:
        exhausted = bool(attempt_bound and len(attempts) >= attempt_bound)
        state = "exhausted" if exhausted else "retryable_failed"
    elif (
        live_state == "live"
        and getattr(live, "identity", None).kind == "executor"
        and receipt.get("attempt_number") is not None
        and receipt.get("claim_id") is not None
    ):
        state = "executing"
    elif transition in {"execution_started", "executing"} or recovery_state in {
        "running",
        "repairing",
        "resuming",
    }:
        state = (
            "executing"
            if live_state == "live"
            and getattr(live, "identity", None).kind == "executor"
            else "stale_unavailable"
        )
    elif transition in {"admitted", "assigned", "investigating"} or recovery_state in {
        "investigating",
        "routing",
    }:
        state = (
            "investigating"
            if live_state == "live"
            and getattr(live, "identity", None).kind == "invocation"
            else "stale_unavailable"
        )
    elif _has_timestamped_acknowledgement(receipt, authoritative):
        state = "acknowledged"
    else:
        state = "requested_queued"
    if receipt.get("schema_version") != SCHEMA_VERSION:
        state = "stale_unavailable"

    material_time = _parse_time(receipt.get("occurred_at"))
    occurred_at = _iso(material_time) if material_time is not None else None
    observed_at = _iso(now)
    valid_until = (
        _iso(live.valid_until)
        if live is not None and state in {"executing", "investigating"}
        else None
    )
    prior_priority = _STATE_PRIORITY[state]
    next_step = {
        "requested_queued": "await owner acknowledgement",
        "acknowledged": "await admitted investigation",
        "investigating": "await matching repair execution",
        "executing": "await executor result",
        "waiting_blocked": "satisfy prerequisite and retry",
        "retryable_failed": "retry within the remaining attempt budget",
        "exhausted": "owner must review the exhausted attempt budget",
        "verification_pending": "await fresh same-generation watchdog postcheck",
        "verified_complete": "no recovery action required",
        "stale_unavailable": "restore matching owner evidence or reassess",
    }[state]
    entry = {
        "schema_version": SCHEMA_VERSION,
        "entry_id": _entry_id(receipt, snapshot),
        "action_id": action_id,
        "original_incident_id": receipt.get("original_incident_id"),
        "generation": generation,
        "graph_id": receipt.get("graph_id"),
        "affected_work_id": None,
        "owner": owner,
        "attempt_number": receipt.get("attempt_number"),
        "claim_id": receipt.get("claim_id"),
        "state": state,
        "stage": transition or None,
        "occurred_at": occurred_at,
        "observed_at": observed_at,
        "valid_until": valid_until,
        "freshness": "fresh" if state not in {"stale_unavailable"} else "unavailable",
        "provenance": "modern"
        if receipt.get("schema_version") == 1
        else "legacy_unknown",
        "safe_reason": safe_reason,
        "prerequisite": safe_reason if state == "waiting_blocked" else None,
        "next_step": next_step,
        "target": _safe_text(safe_payload.get("target"), target=True),
        "verification_ref": verification_ref,
        "receipt_refs": [str(receipt.get("receipt_id"))],
        "milestone_refs": [],
        "blocker_priority": prior_priority,
    }
    return entry


def _valid_receipt(receipt: Mapping[str, Any]) -> bool:
    return all(
        isinstance(receipt.get(key), expected)
        for key, expected in (
            ("receipt_id", str),
            ("source_kind", str),
            ("source_key", str),
            ("action_id", str),
            ("generation", str),
            ("transition_sequence", int),
        )
    )


def _upsert(
    connection: sqlite3.Connection,
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    now: datetime,
) -> set[str]:
    if not _valid_receipt(receipt):
        return set()
    receipt_id = str(receipt["receipt_id"])
    known = connection.execute(
        "SELECT 1 FROM receipts WHERE receipt_id = ?", (receipt_id,)
    ).fetchone()
    entry = _derive_entry(receipt, snapshot, now=now)
    entry_id = str(entry["entry_id"])
    prior = connection.execute(
        "SELECT payload, blocker_priority FROM entries WHERE entry_id = ?", (entry_id,)
    ).fetchone()
    if prior is not None:
        previous = json.loads(str(prior["payload"]))
        refs = list(dict.fromkeys([*previous.get("receipt_refs", []), receipt_id]))
        entry["receipt_refs"] = refs
        if entry["state"] == "stale_unavailable":
            entry["blocker_priority"] = int(prior["blocker_priority"])
    milestones = {
        str(row["receipt_id"]): str(row["message_id"])
        for row in connection.execute(
            "SELECT receipt_id, message_id FROM transcript_milestones WHERE entry_id = ?",
            (entry_id,),
        )
    }
    entry["milestone_refs"] = [
        milestones[ref]
        for ref in entry["receipt_refs"]
        if ref in milestones
    ]
    entry_bytes = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    entry_revision = "sha256:" + hashlib.sha256(entry_bytes.encode()).hexdigest()
    connection.execute(
        "INSERT OR REPLACE INTO entries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            entry_id,
            entry_revision,
            entry["action_id"],
            entry["generation"],
            entry["attempt_number"],
            entry["state"],
            entry["blocker_priority"],
            entry["occurred_at"],
            entry_bytes,
        ),
    )
    work_ids = tuple(
        dict.fromkeys(
            value
            for value in [
                receipt.get("graph_id"),
                *(receipt.get("affected_work_ids") or []),
            ]
            if isinstance(value, str) and value
        )
    )
    for work_id in work_ids:
        connection.execute(
            "INSERT OR IGNORE INTO aliases VALUES (?, ?)", (work_id, entry_id)
        )
        connection.execute("INSERT OR IGNORE INTO dirty VALUES (?)", (work_id,))
    if known is None:
        connection.execute(
            "INSERT INTO receipts VALUES (?, ?, ?, ?, ?)",
            (
                receipt_id,
                receipt["source_kind"],
                receipt["source_key"],
                receipt["transition_sequence"],
                _iso(now),
            ),
        )
    return set(work_ids)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _lag(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute("SELECT COUNT(*) AS count FROM dirty").fetchone()
    return {"backlog_count": int(row["count"]), "oldest_pending_at": None}


def _publish_dirty(
    connection: sqlite3.Connection,
    root: Path,
    *,
    now: datetime,
    deadline: float,
    owner_limit: int,
    completeness: str,
) -> int:
    owners = [
        str(row["work_id"])
        for row in connection.execute(
            "SELECT work_id FROM dirty ORDER BY work_id LIMIT ?", (owner_limit,)
        )
    ]
    if not owners:
        return 0
    batch_revision = (
        "revision-" + now.strftime("%Y%m%dT%H%M%S%fZ") + "-" + uuid.uuid4().hex[:12]
    )
    product_identity, tracking_identity = _repository_identities(root)
    published = 0
    for work_id in owners:
        if time.monotonic() >= deadline:
            break
        rows = connection.execute(
            """SELECT e.payload, e.entry_revision FROM entries e
               JOIN aliases a ON a.entry_id = e.entry_id WHERE a.work_id = ?
               ORDER BY e.blocker_priority, COALESCE(e.material_at, '') DESC, e.entry_id""",
            (work_id,),
        ).fetchall()
        items = []
        for row in rows:
            item = json.loads(str(row["payload"]))
            item["affected_work_id"] = work_id
            item["entry_revision"] = row["entry_revision"]
            items.append(item)
        pages = [
            items[index : index + PAGE_ROWS]
            for index in range(0, len(items), PAGE_ROWS)
        ] or [[]]
        work_root = _base(root) / "work" / _work_hash(work_id)
        revision_root = work_root / "revisions" / batch_revision
        for index, page in enumerate(pages):
            _write_json(
                revision_root / "pages" / f"{index:06d}.json",
                {
                    "schema_version": SCHEMA_VERSION,
                    "work_id": work_id,
                    "revision": batch_revision,
                    "items": page,
                    "next_page": f"pages/{index + 1:06d}.json"
                    if index + 1 < len(pages)
                    else None,
                },
            )
        lag = _lag(connection)
        lag = {**lag, "backlog_count": max(0, lag["backlog_count"] - 1)}
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "work_id": work_id,
            "repository_identity": {
                "product": product_identity,
                "tracking": tracking_identity,
            },
            "revision": batch_revision,
            "producer_runtime_identity": dict(_PRODUCER_RUNTIME),
            "observed_at": _iso(now),
            "expires_at": _iso(now + timedelta(seconds=30)),
            "completeness": completeness,
            "lag": lag,
            "entry_count": len(items),
            "page_count": len(pages),
            "continuation": "pages/000001.json" if len(pages) > 1 else None,
            "pages": [f"pages/{index:06d}.json" for index in range(len(pages))],
        }
        _write_json(revision_root / "manifest.json", manifest)
        _write_json(
            work_root / "current.json",
            {
                "schema_version": SCHEMA_VERSION,
                "work_id": work_id,
                "revision": batch_revision,
                "manifest": f"revisions/{batch_revision}/manifest.json",
            },
        )
        connection.execute("DELETE FROM dirty WHERE work_id = ?", (work_id,))
        published += 1
    return published


def publish_committed_transition(
    root: Path, receipt: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> None:
    """Append and project one transition after its authoritative source commit."""

    started = time.monotonic()
    repo = canonical_audit_root(root)
    from cascade.war_room.recovery_milestones import (
        append_committed_recovery_receipt,
    )

    ack = append_committed_recovery_receipt(repo, receipt, snapshot)
    with _writer_lock:
        connection = _connect(repo)
        try:
            connection.execute("BEGIN IMMEDIATE")
            if ack.get("status") == "committed":
                _record_transcript_milestone(connection, ack, now=_now())
            _upsert(connection, receipt, snapshot, now=_now())
            connection.commit()
            _publish_dirty(
                connection,
                repo,
                now=_now(),
                deadline=started + FAST_PATH_SECONDS,
                owner_limit=MAX_OWNERS_PER_PASS,
                completeness="pending",
            )
            connection.commit()
        finally:
            connection.close()


def _record_transcript_milestone(
    connection: sqlite3.Connection,
    ack: Mapping[str, Any],
    *,
    now: datetime,
) -> None:
    required = {
        "receipt_id": str,
        "entry_id": str,
        "graph_id": str,
        "message_id": str,
        "incarnation": str,
        "append_sequence": int,
    }
    if any(not isinstance(ack.get(key), kind) for key, kind in required.items()):
        raise ValueError("transcript milestone acknowledgement is incomplete")
    receipt_id = str(ack["receipt_id"])
    values = (
        str(ack["entry_id"]),
        str(ack["graph_id"]),
        str(ack["message_id"]),
        str(ack["incarnation"]),
        int(ack["append_sequence"]),
    )
    existing = connection.execute(
        """SELECT entry_id, graph_id, message_id, incarnation, append_sequence
           FROM transcript_milestones WHERE receipt_id = ?""",
        (receipt_id,),
    ).fetchone()
    if existing is not None:
        current = tuple(existing[key] for key in (
            "entry_id", "graph_id", "message_id", "incarnation", "append_sequence"
        ))
        if current != values:
            raise ValueError("receipt maps to a different transcript acknowledgement")
    else:
        connection.execute(
            "INSERT INTO transcript_milestones VALUES (?, ?, ?, ?, ?, ?, ?)",
            (receipt_id, *values, _iso(now)),
        )


def _refresh_entry_milestones(
    connection: sqlite3.Connection, entry_id: str
) -> set[str]:
    row = connection.execute(
        "SELECT payload, blocker_priority FROM entries WHERE entry_id = ?", (entry_id,)
    ).fetchone()
    if row is None:
        return set()
    entry = json.loads(str(row["payload"]))
    mappings = {
        str(item["receipt_id"]): str(item["message_id"])
        for item in connection.execute(
            "SELECT receipt_id, message_id FROM transcript_milestones WHERE entry_id = ?",
            (entry_id,),
        )
    }
    entry["milestone_refs"] = [
        mappings[receipt_id]
        for receipt_id in entry.get("receipt_refs", [])
        if receipt_id in mappings
    ]
    payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
    revision = "sha256:" + hashlib.sha256(payload.encode()).hexdigest()
    connection.execute(
        "UPDATE entries SET payload = ?, entry_revision = ? WHERE entry_id = ?",
        (payload, revision, entry_id),
    )
    aliases = {
        str(item["work_id"])
        for item in connection.execute(
            "SELECT work_id FROM aliases WHERE entry_id = ?", (entry_id,)
        )
    }
    for work_id in aliases:
        connection.execute("INSERT OR IGNORE INTO dirty VALUES (?)", (work_id,))
    return aliases


def record_transcript_milestone(root: Path, ack: Mapping[str, Any]) -> None:
    """Durably join a committed transcript message to its progress entry."""

    repo = canonical_audit_root(root)
    started = time.monotonic()
    with _writer_lock:
        connection = _connect(repo)
        try:
            connection.execute("BEGIN IMMEDIATE")
            _record_transcript_milestone(connection, ack, now=_now())
            _refresh_entry_milestones(connection, str(ack["entry_id"]))
            connection.commit()
            _publish_dirty(
                connection,
                repo,
                now=_now(),
                deadline=started + FAST_PATH_SECONDS,
                owner_limit=MAX_OWNERS_PER_PASS,
                completeness="pending",
            )
            connection.commit()
        finally:
            connection.close()


def _source_rows(
    root: Path, spec: tuple[str, str, str]
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    _name, filename, collection = spec
    path = lifecycle_root(root) / ".cascade" / filename
    if not path.exists():
        return ()
    if not stat.S_ISREG(path.stat().st_mode):
        raise OSError(f"recovery source is not a regular file: {filename}")
    loaded = json.loads(path.read_text(encoding="utf-8"))
    rows = loaded.get(collection, {}) if isinstance(loaded, Mapping) else {}
    return (
        tuple(
            (str(key), value)
            for key, value in rows.items()
            if isinstance(value, Mapping)
        )
        if isinstance(rows, Mapping)
        else ()
    )


def _legacy_receipt(
    spec: tuple[str, str, str], row_key: str, snapshot: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Give a receipt-less retained row a stable unavailable import identity."""

    incident = (
        snapshot.get("incident")
        if isinstance(snapshot.get("incident"), Mapping)
        else snapshot
    )
    action_id = str(snapshot.get("action_id") or incident.get("action_id") or row_key)
    work_id = incident.get("work_id")
    if not isinstance(work_id, str):
        prefix = action_id.split(":", 1)[0]
        work_id = prefix if prefix.startswith(("task_", "feat_", "epic_")) else None
    generation = incident.get("authoritative_generation")
    if not isinstance(generation, str):
        generation = (
            "legacy:unknown:"
            + hashlib.sha256(f"{spec[0]}\0{row_key}".encode()).hexdigest()
        )
    identity = f"{spec[0]}\0{row_key}\0{action_id}\0{generation}"
    return {
        "receipt_id": "sha256:" + hashlib.sha256(identity.encode()).hexdigest(),
        "source_kind": spec[0],
        "source_key": row_key,
        "action": str(snapshot.get("action_kind") or "legacy_recovery"),
        "action_id": action_id,
        "original_incident_id": incident.get("original_incident_id"),
        "generation": generation,
        "graph_id": work_id,
        "affected_work_ids": [work_id] if work_id is not None else [],
        "attempt_number": None,
        "claim_id": None,
        "transition_sequence": 1,
        "transition_kind": "legacy_import",
        "occurred_at": None,
        "source_reference": f"{spec[1]}#{spec[2]}/{row_key}",
        "safe_payload": {},
    }


def _snapshot_receipts(snapshot: Mapping[str, Any]) -> Iterable[Mapping[str, Any]]:
    direct = snapshot.get("transition_receipts")
    if isinstance(direct, list):
        yield from (item for item in direct if isinstance(item, Mapping))
        return
    incident = snapshot.get("incident")
    if isinstance(incident, Mapping):
        nested = incident.get("transition_receipts")
        if isinstance(nested, list):
            yield from (item for item in nested if isinstance(item, Mapping))


def drain_recovery_progress(
    root: Path,
    *,
    max_receipts: int = MAX_RECEIPTS_PER_PASS,
    max_owners: int = MAX_OWNERS_PER_PASS,
    max_seconds: float = MAX_PASS_SECONDS,
) -> dict[str, Any]:
    """Replay missed receipts and publish a bounded fair continuation pass."""

    if max_receipts < 1 or max_receipts > MAX_RECEIPTS_PER_PASS:
        raise ValueError("receipt limit must be between 1 and 100")
    if (
        max_owners < 1
        or max_owners > MAX_OWNERS_PER_PASS
        or max_seconds <= 0
        or max_seconds > MAX_PASS_SECONDS
    ):
        raise ValueError("drain bounds exceed the supervised pass limits")
    started = time.monotonic()
    deadline = started + max_seconds
    repo = canonical_audit_root(root)
    imported = 0
    source_load_seconds = 0.0
    source_complete = True
    with _writer_lock:
        connection = _connect(repo)
        try:
            cursor_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'source_cursor'"
            ).fetchone()
            cursor = int(cursor_row["value"]) if cursor_row else 0
            start_cursor = cursor
            new_rows: list[tuple[Mapping[str, Any], Mapping[str, Any], bool]] = []
            replay_rows: list[tuple[Mapping[str, Any], Mapping[str, Any], bool]] = []
            with task_lifecycle_read_lock(root=repo):
                for offset in range(len(_SOURCE_SPECS)):
                    spec_index = (start_cursor + offset) % len(_SOURCE_SPECS)
                    before = time.monotonic()
                    try:
                        snapshots = _source_rows(repo, _SOURCE_SPECS[spec_index])
                    except (OSError, json.JSONDecodeError):
                        source_complete = False
                        continue
                    source_load_seconds += time.monotonic() - before
                    for row_key, snapshot in snapshots:
                        receipts = tuple(_snapshot_receipts(snapshot))
                        if not receipts:
                            receipts = (
                                _legacy_receipt(
                                    _SOURCE_SPECS[spec_index], row_key, snapshot
                                ),
                            )
                        for receipt_index, receipt in enumerate(receipts):
                            if time.monotonic() >= deadline:
                                source_complete = False
                                break
                            if not _valid_receipt(receipt):
                                source_complete = False
                                continue
                            known = connection.execute(
                                "SELECT 1 FROM receipts WHERE receipt_id = ?",
                                (receipt["receipt_id"],),
                            ).fetchone()
                            if known is not None:
                                mapped = connection.execute(
                                    "SELECT 1 FROM transcript_milestones WHERE receipt_id = ?",
                                    (receipt["receipt_id"],),
                                ).fetchone()
                                if receipt_index + 1 == len(receipts):
                                    existing = connection.execute(
                                        "SELECT state FROM entries WHERE entry_id = ?",
                                        (_entry_id(receipt, snapshot),),
                                    ).fetchone()
                                    if existing is not None and existing["state"] in {
                                        "executing",
                                        "investigating",
                                    }:
                                        _upsert(
                                            connection, receipt, snapshot, now=_now()
                                        )
                                if mapped is not None:
                                    continue
                            detached = (
                                json.loads(json.dumps(dict(receipt))),
                                json.loads(json.dumps(dict(snapshot))),
                                known is not None,
                            )
                            (replay_rows if known is not None else new_rows).append(detached)
                        if time.monotonic() >= deadline:
                            source_complete = False
                            break
                    cursor = (spec_index + 1) % len(_SOURCE_SPECS)
                    if time.monotonic() >= deadline:
                        source_complete = False
                        break
            replay_turn_row = connection.execute(
                "SELECT value FROM meta WHERE key = 'milestone_replay_turn'"
            ).fetchone()
            replay_first = replay_turn_row is not None and replay_turn_row["value"] == "1"
            ordered_rows = (
                replay_rows + new_rows if replay_first else new_rows + replay_rows
            )
            queued = ordered_rows[:max_receipts]
            unprocessed = len(ordered_rows) - len(queued)
            if new_rows and replay_rows:
                connection.execute(
                    "INSERT OR REPLACE INTO meta VALUES ('milestone_replay_turn', ?)",
                    ("0" if replay_first else "1",),
                )
            if len(queued) >= max_receipts or unprocessed:
                source_complete = False
            from cascade.war_room.recovery_milestones import (
                append_committed_recovery_receipt,
            )

            milestone_pending = 0
            for receipt, snapshot, was_known in queued:
                if time.monotonic() >= deadline:
                    source_complete = False
                    milestone_pending += 1
                    continue
                ack = append_committed_recovery_receipt(
                    repo,
                    receipt,
                    snapshot,
                    provenance=(
                        "reconciled"
                        if receipt.get("schema_version") == 1
                        else "legacy_unknown"
                    ),
                )
                known = connection.execute(
                    "SELECT 1 FROM receipts WHERE receipt_id = ?",
                    (receipt["receipt_id"],),
                ).fetchone()
                if ack.get("status") == "committed":
                    _record_transcript_milestone(connection, ack, now=_now())
                else:
                    milestone_pending += 1
                if not was_known or ack.get("status") == "committed":
                    _upsert(connection, receipt, snapshot, now=_now())
                if known is None:
                    imported += 1
            if milestone_pending or unprocessed:
                cursor = start_cursor
            connection.execute(
                "INSERT OR REPLACE INTO meta VALUES ('source_cursor', ?)",
                (str(cursor),),
            )
            connection.execute(
                "INSERT OR REPLACE INTO meta VALUES ('legacy_import_complete', ?)",
                ("1" if source_complete else "0",),
            )
            connection.commit()
            published = _publish_dirty(
                connection,
                repo,
                now=_now(),
                deadline=deadline,
                owner_limit=max_owners,
                completeness="complete" if source_complete else "incomplete",
            )
            connection.commit()
            lag = _lag(connection)
            lag["milestone_backlog_count"] = milestone_pending + unprocessed
        finally:
            connection.close()
    return {
        "imported_receipts": imported,
        "published_owners": published,
        "complete": source_complete and lag["backlog_count"] == 0,
        "lag": lag,
        "source_load_seconds": source_load_seconds,
        "duration_seconds": time.monotonic() - started,
    }


def install_recovery_progress_publisher(root: Path) -> None:
    """Install the process callback and perform the same bounded startup replay."""

    from cascade.recovery_progress.notifications import register_transition_publisher

    repo = canonical_audit_root(root)
    register_transition_publisher(publish_committed_transition)
    with _writer_lock:
        first = repo not in _installed_roots
        _installed_roots.add(repo)
    if first:
        drain_recovery_progress(repo)


__all__ = [
    "drain_recovery_progress",
    "install_recovery_progress_publisher",
    "publish_committed_transition",
    "record_transcript_milestone",
]
