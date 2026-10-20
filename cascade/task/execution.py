"""Durable operational health for Task executions.

Board frontmatter remains lifecycle truth.  This sidecar only records whether the
local worker that owns an active Task is queued, alive, or finished.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock

ExecutionPhase = Literal["queued", "running", "terminal"]
ExecutionOutcome = Literal["succeeded", "failed"]
DEFAULT_STALE_AFTER = timedelta(minutes=2)
# A validation miss gets two corrective turns before the third miss fails.
MAX_VALIDATION_FAILURES = 3


def _path(root: Path) -> Path:
    return root / ".cascade" / "executions.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _process_start_token(pid: int) -> str | None:
    """Return Linux's stable process start tick, when available.

    Pairing this with the PID prevents PID reuse from inheriting a live lease.
    Non-Linux hosts safely fall back to PID liveness plus heartbeat age.
    """

    try:
        # `/proc/<pid>/stat` field 22.  The command name may contain spaces and
        # parentheses, so split only after its final closing parenthesis.
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        tail = stat.rsplit(")", 1)[1].strip().split()
        return tail[19]
    except (OSError, IndexError):
        return None


def _pid_is_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _read(root: Path) -> dict[str, dict[str, Any]]:
    path = _path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    records = raw.get("executions") if isinstance(raw, dict) else None
    if not isinstance(records, dict):
        return {}
    return {str(key): dict(value) for key, value in records.items() if isinstance(value, dict)}


def _write(root: Path, records: dict[str, dict[str, Any]]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(
        json.dumps({"version": 1, "executions": records}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temp.replace(path)


def mark_queued(task_id: str, *, root: Path, now: datetime | None = None) -> dict[str, Any]:
    repo = resolve_root(root)
    current = now or _now()
    with process_lock:
        records = _read(repo)
        previous = records.get(task_id, {})
        record = {
            "task_id": task_id,
            "attempt": int(previous.get("attempt") or 0) + 1,
            "phase": "queued",
            "outcome": None,
            "queued_at": _iso(current),
            "started_at": None,
            "heartbeat_at": _iso(current),
            "finished_at": None,
            "last_error": None,
            "validation_failures": 0,
            "owner_pid": None,
            "owner_start_token": None,
        }
        records[task_id] = record
        _write(repo, records)
        return dict(record)


def mark_running(task_id: str, *, root: Path, now: datetime | None = None) -> dict[str, Any]:
    repo = resolve_root(root)
    current = now or _now()
    with process_lock:
        records = _read(repo)
        record = dict(records.get(task_id, {}))
        record.update(
            {
                "task_id": task_id,
                "attempt": int(record.get("attempt") or 1),
                "phase": "running",
                "outcome": None,
                "queued_at": record.get("queued_at") or _iso(current),
                "started_at": record.get("started_at") or _iso(current),
                "heartbeat_at": _iso(current),
                "finished_at": None,
                "last_error": None,
                "validation_failures": int(record.get("validation_failures") or 0),
                "owner_pid": os.getpid(),
                "owner_start_token": _process_start_token(os.getpid()),
            }
        )
        records[task_id] = record
        _write(repo, records)
        return dict(record)


def heartbeat(task_id: str, *, root: Path, now: datetime | None = None) -> None:
    repo = resolve_root(root)
    current = now or _now()
    with process_lock:
        records = _read(repo)
        record = records.get(task_id)
        if record is None or record.get("phase") == "terminal":
            return
        record["heartbeat_at"] = _iso(current)
        records[task_id] = record
        _write(repo, records)


def record_running_error(
    task_id: str, error: str | None, *, root: Path, now: datetime | None = None
) -> None:
    """Record recoverable in-turn feedback without terminalizing the Task."""

    repo = resolve_root(root)
    current = now or _now()
    with process_lock:
        records = _read(repo)
        record = records.get(task_id)
        if record is None:
            record = mark_running(task_id, root=repo, now=current)
            records = _read(repo)
        if record.get("phase") == "terminal":
            return
        record["heartbeat_at"] = _iso(current)
        record["last_error"] = error
        records[task_id] = record
        _write(repo, records)


def clear_validation_failures(task_id: str, *, root: Path) -> None:
    repo = resolve_root(root)
    with process_lock:
        records = _read(repo)
        record = records.get(task_id)
        if record is None:
            return
        record["validation_failures"] = 0
        record["last_error"] = None
        records[task_id] = record
        _write(repo, records)


def mark_validation_retry(task_id: str, error: str, *, root: Path) -> int:
    """Persist one failed/no-signal validation turn and requeue the same attempt."""

    repo = resolve_root(root)
    current = _now()
    with process_lock:
        records = _read(repo)
        record = dict(records.get(task_id, {}))
        failures = int(record.get("validation_failures") or 0) + 1
        record.update(
            {
                "task_id": task_id,
                "attempt": int(record.get("attempt") or 1),
                "phase": "queued",
                "outcome": None,
                "queued_at": _iso(current),
                "heartbeat_at": _iso(current),
                "finished_at": None,
                "last_error": error,
                "validation_failures": failures,
                "owner_pid": None,
                "owner_start_token": None,
            }
        )
        records[task_id] = record
        _write(repo, records)
        return failures


def mark_terminal(
    task_id: str,
    outcome: ExecutionOutcome,
    *,
    root: Path,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    repo = resolve_root(root)
    current = now or _now()
    with process_lock:
        records = _read(repo)
        record = dict(records.get(task_id, {}))
        record.update(
            {
                "task_id": task_id,
                "attempt": int(record.get("attempt") or 1),
                "phase": "terminal",
                "outcome": outcome,
                "queued_at": record.get("queued_at") or _iso(current),
                "started_at": record.get("started_at"),
                "heartbeat_at": _iso(current),
                "finished_at": _iso(current),
                "last_error": error,
                "validation_failures": int(record.get("validation_failures") or 0),
                "owner_pid": None,
                "owner_start_token": None,
            }
        )
        records[task_id] = record
        _write(repo, records)
        return dict(record)


def execution_view(
    task_id: str,
    *,
    root: Path,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> dict[str, Any] | None:
    repo = resolve_root(root)
    with process_lock:
        record = _read(repo).get(task_id)
    if record is None:
        return None
    current = now or _now()
    health: str
    age_seconds: float | None = None
    if record.get("phase") == "terminal":
        health = str(record.get("outcome") or "failed")
    else:
        try:
            heartbeat_at = datetime.fromisoformat(str(record["heartbeat_at"]))
            if heartbeat_at.tzinfo is None:
                heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
            age_seconds = max(0.0, (current - heartbeat_at).total_seconds())
        except (KeyError, TypeError, ValueError):
            age_seconds = None
        if age_seconds is None or age_seconds > stale_after.total_seconds():
            health = "stale"
        elif record.get("phase") == "queued":
            health = "queued"
        else:
            health = "healthy"
    return {**record, "health": health, "heartbeat_age_seconds": age_seconds}


def execution_lease_is_live(
    task_id: str,
    *,
    root: Path,
    now: datetime | None = None,
    stale_after: timedelta = DEFAULT_STALE_AFTER,
) -> bool:
    """Whether a running Task lease is fresh enough to fence a restart.

    A provider bridge may survive its supervisor parent.  Therefore a fresh
    heartbeat fences recovery even when ``owner_pid`` has exited; stale age is
    the safe reclaim boundary.  PID/start-token remain diagnostic identity and
    protect future targeted cancellation work.
    """

    view = execution_view(task_id, root=root, now=now, stale_after=stale_after)
    if view is None or view.get("phase") != "running" or view.get("health") != "healthy":
        return False
    return True
