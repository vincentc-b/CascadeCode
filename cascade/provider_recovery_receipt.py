"""Durable failed actions and idempotent Flex continuation receipts.

The active provider blocker is a mutable presentation row.  This ledger keeps
the immutable action attempts and the one authorization/handoff receipt that
must survive blocker replacement and process restart.
"""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping

from cascade.agent.flex_continuation_contract import (
    FlexWaiver,
    OriginalActionIdentity,
    contract_projection,
)
from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock


@dataclass(frozen=True, slots=True)
class HandoffClaim:
    """Safe result of the authorized -> handoff_pending compare-and-set."""

    claimed: bool
    receipt_id: str
    state: str
    handoff_id: str | None = None


def persist_failed_action_attempt(
    identity: OriginalActionIdentity,
    *,
    failed_preflight: Mapping[str, object],
    original_actor: str,
    document_path: str,
    replay_arguments: Mapping[str, object],
    root: Path,
) -> dict[str, object]:
    """Append one immutable, non-secret canonical preflight attempt."""

    repo = resolve_root(root)
    row = {
        "failed_action": contract_projection(identity),
        "failed_preflight": dict(failed_preflight),
        "original_actor": original_actor,
        "document_path": document_path,
        "replay_arguments": dict(replay_arguments),
        "recorded_at": _now(),
    }
    with process_lock:
        ledger = _read(repo)
        existing = ledger.get("failed_actions")
        attempts = dict(existing) if isinstance(existing, dict) else {}
        previous = attempts.get(identity.action_id)
        if previous is not None and previous != row:
            raise ValueError("failed action ID already names another attempt")
        attempts[identity.action_id] = row
        ledger["failed_actions"] = attempts
        _write(repo, ledger)
    return dict(row)


def read_failed_action_attempt(action_id: str, *, root: Path) -> dict[str, object] | None:
    repo = resolve_root(root)
    with process_lock:
        rows = _read(repo).get("failed_actions")
        row = rows.get(action_id) if isinstance(rows, dict) else None
    return dict(row) if isinstance(row, dict) else None


def persist_authorized_continuation(
    identity: OriginalActionIdentity,
    waiver: FlexWaiver,
    *,
    root: Path,
) -> tuple[dict[str, object], bool]:
    """Atomically commit the authorization, scoped waiver, and receipt.

    Returns the durable receipt and whether this call created it.  A receipt
    key collision with different authorization data fails closed.
    """

    if waiver.receipt_id != identity.receipt_id:
        raise ValueError("waiver and failed action receipt IDs differ")
    repo = resolve_root(root)
    now = _now()
    receipt = {
        "receipt_id": identity.receipt_id,
        "waiver_id": waiver.waiver_id,
        **contract_projection(identity),
        "authorized_subject": waiver.authorized_subject,
        "authorized_at": waiver.authorized_at,
        "state": "authorized",
        "state_changed_at": now,
        "first_seen_at": now,
        "last_seen_at": now,
        "requested_flex": True,
        "effective_flex": False,
        "scope": [contract_projection(member) for member in waiver.scope],
        "inventory_freshness": contract_projection(waiver.inventory_freshness),
    }
    waiver_row = contract_projection(waiver)
    with process_lock:
        ledger = _read(repo)
        existing_receipts = ledger.get("continuation_receipts")
        receipts = (
            dict(existing_receipts) if isinstance(existing_receipts, dict) else {}
        )
        previous = receipts.get(identity.receipt_id)
        if previous is not None:
            if not isinstance(previous, dict) or not _same_authorization(
                previous, receipt
            ):
                raise ValueError("receipt ID already names another authorization")
            return dict(previous), False

        existing_waivers = ledger.get("flex_waivers")
        waivers = dict(existing_waivers) if isinstance(existing_waivers, dict) else {}
        prior_waiver = waivers.get(waiver.waiver_id)
        if prior_waiver is not None and prior_waiver != waiver_row:
            raise ValueError("waiver ID already names another authorization")
        waivers[waiver.waiver_id] = waiver_row
        receipts[identity.receipt_id] = receipt
        ledger["flex_waivers"] = waivers
        ledger["continuation_receipts"] = receipts
        _write(repo, ledger)
    return dict(receipt), True


def read_continuation_receipt(
    receipt_id: str, *, root: Path
) -> dict[str, object] | None:
    repo = resolve_root(root)
    with process_lock:
        rows = _read(repo).get("continuation_receipts")
        row = rows.get(receipt_id) if isinstance(rows, dict) else None
    return dict(row) if isinstance(row, dict) else None


def claim_continuation_handoff(receipt_id: str, *, root: Path) -> HandoffClaim:
    """Claim the original action once, durably, before any adapter call."""

    repo = resolve_root(root)
    with process_lock:
        ledger = _read(repo)
        existing = ledger.get("continuation_receipts")
        receipts = dict(existing) if isinstance(existing, dict) else {}
        current = receipts.get(receipt_id)
        if not isinstance(current, dict):
            return HandoffClaim(False, receipt_id, "missing")
        state = current.get("state")
        handoff_id = current.get("handoff_id")
        if state != "authorized":
            return HandoffClaim(
                False,
                receipt_id,
                str(state or "invalid"),
                handoff_id if isinstance(handoff_id, str) else None,
            )
        now = _now()
        handoff_id = uuid.uuid4().hex
        updated = {
            **current,
            "state": "handoff_pending",
            "state_changed_at": now,
            "last_seen_at": now,
            "handoff_id": handoff_id,
        }
        receipts[receipt_id] = updated
        ledger["continuation_receipts"] = receipts
        _write(repo, ledger)
    return HandoffClaim(True, receipt_id, "handoff_pending", handoff_id)


def _same_authorization(left: Mapping[str, object], right: Mapping[str, object]) -> bool:
    stable = (
        "receipt_id",
        "waiver_id",
        "action_id",
        "action_kind",
        "work_id",
        "target_tier",
        "trigger_id",
        "document_revision",
        "selection_fingerprint",
        "authorized_subject",
        "scope",
    )
    return all(left.get(key) == right.get(key) for key in stable)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path(root: Path) -> Path:
    return root / ".cascade" / "provider_recoveries.json"


def _read(root: Path) -> dict[str, object]:
    path = _path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {"version": 2}
    return {**payload, "version": 2} if isinstance(payload, dict) else {"version": 2}


def _write(root: Path, payload: Mapping[str, object]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(dict(payload), handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


__all__ = [
    "HandoffClaim",
    "claim_continuation_handoff",
    "persist_authorized_continuation",
    "persist_failed_action_attempt",
    "read_continuation_receipt",
    "read_failed_action_attempt",
]
