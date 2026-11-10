"""Dispatch and queue types locked by feat_002."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from cascade.agent.capability_contract import EffectiveSelectionBatch
    from cascade.agent.preflight import ProviderCapabilityBatchPreflight

Principal = Literal["human", "boss"]
DispatchKind = Literal["epic", "feature", "task"]
DispatchReason = Literal[
    "unauthorized",
    "unmet_deps",
    "dependency_unmet",
    "dependency_status_unavailable",
    "cap",
    "not_found",
    "bad_state",
    "provider_preflight_blocked",
    "provider_preflight_unavailable",
]


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
    preflight: ProviderCapabilityBatchPreflight | None = None
    selections: EffectiveSelectionBatch | None = None
    detail: str | None = None
