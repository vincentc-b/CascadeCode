"""Fresh provider checks and durable, safe execution-boundary blockers.

This is deliberately separate from :mod:`cascade.agent.preflight`: that module
classifies an inventory without side effects, while this module is the narrow
execution boundary that refreshes that inventory and records a failed start.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cascade.agent.discovery.inventory import refresh_provider_inventory
from cascade.agent.preflight import ProviderCapabilityPreflight, preflight_provider_capability
from cascade.board.context import resolve_root
from cascade.provider_recovery_state import safe_provider_reason
from cascade.watchdog.lock import process_lock

BlockerClassification = Literal["deterministic", "transient"]


@dataclass(frozen=True)
class ProviderSelection:
    """The non-secret backend selection for one role about to start."""

    role: str
    provider: str
    model_id: str
    reasoning_level: str | None = None
    flex_mode: bool | None = None


@dataclass(frozen=True)
class ExecutionPreflightResult:
    """Result of checking all affected roles immediately before a turn."""

    supported: bool
    checks: tuple[ProviderCapabilityPreflight, ...]
    affected_roles: tuple[str, ...]
    classification: BlockerClassification | None = None


def recheck_provider_capability(
    work_id: str,
    *,
    tier: str,
    selections: tuple[ProviderSelection, ...],
    root: Path,
) -> ExecutionPreflightResult:
    """Refresh capability immediately before execution and upsert its blocker.

    Discovery failures are represented by the existing safe capability contract;
    provider exception text and raw payloads never reach persistence.
    """

    inventory = refresh_provider_inventory()
    checks = tuple(
        preflight_provider_capability(
            provider=selection.provider,  # validated when the selection was seeded
            model_id=selection.model_id,
            tier=tier,
            inventory=inventory,
            reasoning_level=selection.reasoning_level,
            flex_mode=selection.flex_mode,
        )
        for selection in selections
    )
    failed = tuple(
        (selection, check)
        for selection, check in zip(selections, checks, strict=True)
        if not check.supported
    )
    if not failed:
        clear_provider_blocker(work_id, root=root)
        return ExecutionPreflightResult(True, checks, ())

    # A bad requested configuration is deterministic.  A discovery/setup
    # failure is transient unless there is also a deterministic rejection.
    classification: BlockerClassification = (
        "deterministic" if any(check.outcome == "unsupported" for _, check in failed) else "transient"
    )
    affected_roles = tuple(selection.role for selection, _ in failed)
    upsert_provider_blocker(
        work_id,
        tier=tier,
        failed=failed,
        classification=classification,
        root=root,
    )
    return ExecutionPreflightResult(False, checks, affected_roles, classification)


def provider_blocker(work_id: str, *, root: Path) -> dict[str, object] | None:
    """Read the active durable blocker for one work item after restart."""

    repo = resolve_root(root)
    with process_lock:
        row = _read(repo).get(work_id)
    if not isinstance(row, dict) or not row.get("active"):
        return None
    return dict(row)


def upsert_provider_blocker(
    work_id: str,
    *,
    tier: str,
    failed: tuple[tuple[ProviderSelection, ProviderCapabilityPreflight], ...],
    classification: BlockerClassification,
    root: Path,
) -> dict[str, object]:
    """Refresh one safe blocker per work ID rather than appending incidents."""

    repo = resolve_root(root)
    now = datetime.now(timezone.utc).isoformat()
    first_selection, first_check = failed[0]
    row: dict[str, object] = {
        "work_id": work_id,
        "tier": tier,
        "affected_roles": sorted(selection.role for selection, _ in failed),
        "provider": first_selection.provider,
        "reason_code": first_check.reason,
        # Never retain provider-provided exception text.  This stable message
        # is safe to render after restart and shared by board/War Room.
        "reason": safe_provider_reason(first_check.reason),
        "classification": classification,
        "recommended_remedy": _recommended_remedy(first_check),
        "last_attempt": now,
        "active": True,
    }
    with process_lock:
        records = _read(repo)
        previous = records.get(work_id)
        # Keep the original observation for operator context while maintaining a
        # single mutable incident identity for this work item.
        if isinstance(previous, dict) and isinstance(previous.get("first_attempt"), str):
            row["first_attempt"] = previous["first_attempt"]
        else:
            row["first_attempt"] = now
        records[work_id] = row
        _write(repo, records)
    return dict(row)


def clear_provider_blocker(work_id: str, *, root: Path) -> None:
    """Mark the one incident resolved while retaining its small audit record."""

    repo = resolve_root(root)
    with process_lock:
        records = _read(repo)
        row = records.get(work_id)
        if not isinstance(row, dict) or not row.get("active"):
            return
        row = dict(row)
        row["active"] = False
        row["resolved_at"] = datetime.now(timezone.utc).isoformat()
        records[work_id] = row
        _write(repo, records)


def _recommended_remedy(check: ProviderCapabilityPreflight) -> str:
    if check.reason == "flex_mode_not_supported":
        return "disable_flex"
    if check.outcome == "unsupported":
        return "choose_provider_or_model"
    return "retry_provider_setup"


def _path(root: Path) -> Path:
    return root / ".cascade" / "provider_blockers.json"


def _read(root: Path) -> dict[str, dict[str, object]]:
    path = _path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {}
    blockers = payload.get("blockers") if isinstance(payload, dict) else None
    return {
        str(work_id): dict(row)
        for work_id, row in blockers.items()
        if isinstance(row, dict)
    } if isinstance(blockers, dict) else {}


def _write(root: Path, records: dict[str, dict[str, object]]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "blockers": records}
    temp = path.with_suffix(".tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(path)
    finally:
        temp.unlink(missing_ok=True)
