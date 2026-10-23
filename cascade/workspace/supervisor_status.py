"""Atomic read/write of ``.cascade/supervisor_status.json`` (stdlib-only)."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, TypedDict

SupervisorState = Literal[
    "serving", "draining", "restarting", "update_blocked", "degraded"
]

_STATUS_FILENAME = "supervisor_status.json"


class LastError(TypedDict, total=False):
    exit_code: int | None
    stderr_tail: str | None
    message: str | None


class SupervisorStatus(TypedDict):
    state: SupervisorState
    worker_pid: int | None
    restart_count: int
    last_error: LastError | None
    next_action: str | None
    trunk_lock_warning: str | None
    since: str
    updated_at: str


def status_path(workspace_root: Path) -> Path:
    return Path(workspace_root).resolve() / ".cascade" / _STATUS_FILENAME


def read_supervisor_status(workspace_root: Path) -> SupervisorStatus | None:
    path = status_path(workspace_root)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed  # type: ignore[return-value]


def write_supervisor_status(workspace_root: Path, status: SupervisorStatus) -> None:
    path = status_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(status, indent=2, sort_keys=True) + "\n"
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temp_name = handle.name
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    finally:
        if temp_name is not None:
            Path(temp_name).unlink(missing_ok=True)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
