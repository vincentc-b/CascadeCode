"""Dispatch and queue types locked by feat_002."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

Principal = Literal["human", "boss"]
DispatchKind = Literal["epic", "feature", "task"]
DispatchReason = Literal["unauthorized", "unmet_deps", "cap", "not_found", "bad_state"]


@dataclass(frozen=True)
class Event:
    """One JSONL queue record. `ts` is timezone-aware UTC."""

    type: str
    ts: datetime
    payload: dict[str, Any]
    dest: str


@dataclass(frozen=True)
class DispatchRequest:
    kind: DispatchKind
    id: str
    by: Principal


@dataclass(frozen=True)
class DispatchResult:
    ok: bool
    reason: str | None
    event: Event | None
