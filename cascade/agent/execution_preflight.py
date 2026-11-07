"""Fresh provider checks and durable, safe execution-boundary blockers.

This is deliberately separate from :mod:`cascade.agent.preflight`: that module
classifies an inventory without side effects, while this module is the narrow
execution boundary that refreshes that inventory and records a failed start.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cascade.agent.discovery.inventory import refresh_provider_inventory
from cascade.agent.preflight import (
    ProviderCapabilityBatchPreflight,
    ProviderCapabilityPreflight,
)
from cascade.agent.capability_contract import role_scope
from cascade.agent.flex_continuation_contract import (
    ActionKind,
    OriginalActionIdentity,
    contract_projection as continuation_contract_projection,
)
from cascade.agent.selection_preflight import RuntimeSelection, evaluate_work_selection
from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.watchdog.lock import process_lock

# Compatibility name for callers constructing non-secret launch arguments.
ProviderSelection = RuntimeSelection


def recheck_provider_capability(
    work_id: str,
    *,
    tier: str,
    selections: tuple[ProviderSelection, ...],
    root: Path,
) -> ProviderCapabilityBatchPreflight:
    """Refresh capability immediately before execution and upsert its blocker.

    Discovery failures are represented by the existing safe capability contract;
    provider exception text and raw payloads never reach persistence.
    """

    repo = resolve_root(root)
    doc = read_doc(work_id, root=repo)
    if doc.meta.tier != tier:
        raise ValueError(f"work tier mismatch for {work_id}")
    result = evaluate_work_selection(
        doc,
        root=repo,
        inventory=refresh_provider_inventory(),
        action="execution",
        runtime_selections=selections,
    ).result
    failed = tuple(check for check in result.checks if not check.result.supported)
    if not failed:
        clear_provider_blocker(work_id, result=result, root=repo)
        return result

    upsert_provider_blocker(
        work_id,
        tier=tier,
        result=result,
        root=repo,
    )
    return result


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
    result: ProviderCapabilityBatchPreflight,
    root: Path,
    failed_action: OriginalActionIdentity | None = None,
) -> dict[str, object]:
    """Refresh one complete safe blocker per work ID instead of appending."""

    repo = resolve_root(root)
    now = datetime.now(timezone.utc).isoformat()
    failed = tuple(check for check in result.checks if not check.result.supported)
    if not failed or result.classification is None:
        raise ValueError("provider blocker requires a failed batch")
    primary = next(
        (check for check in failed if check.result.reason == result.reason_code),
        failed[0],
    )
    primary_check = primary.result
    row: dict[str, object] = {
        "work_id": work_id,
        "tier": tier,
        "action": result.action,
        "selection_fingerprint": result.selection_fingerprint,
        # Persist the complete scope, including successful sibling roles.  A
        # later start must prove this same whole scope healthy before the
        # incident can be resolved.
        "checks": [check.to_dict() for check in result.checks],
        "inventory_freshness": result.to_dict()["inventory_freshness"],
        "affected_roles": sorted(check.role for check in failed),
        "provider": primary_check.provider,
        "reason_code": primary_check.reason,
        # Never retain provider-provided exception text.  This stable message
        # is safe to render after restart and shared by board/War Room.
        "reason": primary_check.message,
        "classification": result.classification,
        "recommended_remedy": _recommended_remedy(primary_check),
        "last_attempt": now,
        "active": True,
    }
    if failed_action is not None:
        row["failed_action"] = continuation_contract_projection(failed_action)
        row["failed_preflight"] = result.to_dict()
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


def record_failed_provider_action(
    work_id: str,
    *,
    tier: str,
    action_kind: ActionKind,
    result: ProviderCapabilityBatchPreflight,
    root: Path,
    trigger_id: str | None = None,
    original_actor: str = "system",
    document_path: str | None = None,
    replay_arguments: dict[str, object] | None = None,
) -> dict[str, object]:
    """Persist one concrete canonical action failure for read-only recovery.

    A new canonical attempt receives a new opaque identity even when it targets
    the same work item.  The mutable per-work blocker remains only the current
    presentation projection.
    """

    revisions = {
        check.result.document_revision
        for check in result.checks
        if check.result.document_revision is not None
    }
    if (
        result.action != action_kind
        or result.work_id != work_id
        or result.selection_fingerprint is None
        or len(revisions) != 1
        or tier not in ("epic", "feature", "task")
    ):
        raise ValueError("failed action requires one complete reviewed selection")
    identity = OriginalActionIdentity(
        action_id=uuid.uuid4().hex,
        action_kind=action_kind,
        work_id=work_id,
        target_tier=tier,  # type: ignore[arg-type]
        document_revision=next(iter(revisions)),
        selection_fingerprint=result.selection_fingerprint,
        trigger_id=trigger_id,
    )
    from cascade.provider_recovery_receipt import persist_failed_action_attempt

    primary = result.checks[0].result
    persist_failed_action_attempt(
        identity,
        failed_preflight=result.to_dict(),
        original_actor=original_actor,
        document_path=document_path or primary.document_path or "unavailable",
        replay_arguments=replay_arguments or {},
        root=root,
    )
    return upsert_provider_blocker(
        work_id,
        tier=tier,
        result=result,
        root=root,
        failed_action=identity,
    )


def clear_provider_blocker(
    work_id: str,
    *,
    result: ProviderCapabilityBatchPreflight | None = None,
    root: Path,
) -> bool:
    """Resolve only after a fresh successful check of the blocked full scope.

    ``result`` is deliberately mandatory in practice.  Keeping the optional
    default makes older recovery callers fail safe: configuration mutation or
    cached readiness alone cannot erase an execution incident.
    """

    repo = resolve_root(root)
    with process_lock:
        records = _read(repo)
        row = records.get(work_id)
        if not isinstance(row, dict) or not row.get("active"):
            return False
        if result is None or not _successful_fresh_scope(row, result):
            return False
        row = dict(row)
        row["active"] = False
        row["resolved_at"] = datetime.now(timezone.utc).isoformat()
        row["resolution_fingerprint"] = result.selection_fingerprint
        row["resolution_inventory_freshness"] = result.to_dict()["inventory_freshness"]
        records[work_id] = row
        _write(repo, records)
        return True


def _successful_fresh_scope(
    row: dict[str, object], result: ProviderCapabilityBatchPreflight
) -> bool:
    if (
        not result.supported
        or result.action != "execution"
        or result.work_id != row.get("work_id")
    ):
        return False
    freshness = result.inventory_freshness
    if freshness is None or freshness.from_cache:
        return False
    previous_checks = row.get("checks")
    previous_roles = (
        {
            str(check.get("role"))
            for check in previous_checks
            if isinstance(check, dict) and isinstance(check.get("role"), str)
        }
        if isinstance(previous_checks, list)
        else set()
    )
    if not previous_roles:
        tier = row.get("tier")
        if tier not in ("epic", "feature", "task"):
            return False
        previous_roles = set(role_scope(tier))
    current_roles = {check.role for check in result.checks}
    return current_roles == previous_roles and all(
        check.result.supported for check in result.checks
    )


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
    payload = {"version": 2, "blockers": records}
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
