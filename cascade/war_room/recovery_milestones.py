"""Deterministic transcript milestones for committed recovery receipts."""

from __future__ import annotations

import re
import sqlite3
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from cascade.board.errors import NotFound, SchemaError
from cascade.recovery_progress.publisher import _entry_id, _safe_text
from cascade.war_room.chat_store import (
    TranscriptPendingError,
    append_transcript_message,
    fenced_transcript_source_acknowledgement,
)
from cascade.watchdog.incidents import transition_receipt_v1
from cascade.workspace.doc_root import read_doc_resolved

_SAFE_REFERENCE = re.compile(r"[A-Za-z0-9 _./:@+\-=#]{1,240}\Z", re.ASCII)
_WORK_ID = re.compile(r"(?:task|feat|epic)_[A-Za-z0-9_.-]+\Z")


def _pending(
    receipt: Mapping[str, Any], snapshot: Mapping[str, Any], code: str
) -> dict[str, object]:
    receipt_id = receipt.get("receipt_id")
    result: dict[str, object] = {
        "status": "pending",
        "code": code,
        "receipt_id": receipt_id if isinstance(receipt_id, str) else None,
    }
    try:
        result["entry_id"] = _entry_id(receipt, snapshot)
    except Exception:
        result["entry_id"] = None
    return result


def _owning_graph(work_id: str, *, root: Path) -> str | None:
    if not _WORK_ID.fullmatch(work_id):
        return None
    try:
        doc = read_doc_resolved(work_id, root=root)
    except (NotFound, SchemaError, OSError, ValueError):
        return None
    if doc.meta.tier in {"epic", "feature"}:
        return doc.meta.id
    if doc.meta.tier == "task" and isinstance(doc.meta.parent, str):
        try:
            parent = read_doc_resolved(doc.meta.parent, root=root)
        except (NotFound, SchemaError, OSError, ValueError):
            return None
        if parent.meta.tier == "feature":
            return parent.meta.id
    return None


def _resolve_graph(receipt: Mapping[str, Any], *, root: Path) -> str | None:
    candidates: list[str] = []
    graph_id = receipt.get("graph_id")
    if isinstance(graph_id, str):
        candidates.append(graph_id)
    affected = receipt.get("affected_work_ids")
    if isinstance(affected, list):
        candidates.extend(item for item in affected if isinstance(item, str))
    owners = {
        owner
        for candidate in candidates
        if (owner := _owning_graph(candidate, root=root)) is not None
    }
    return next(iter(owners)) if len(owners) == 1 else None


def _safe_receipt(
    receipt: Mapping[str, Any], snapshot: Mapping[str, Any]
) -> tuple[str, str, str | None] | None:
    receipt_id = receipt.get("receipt_id")
    action = receipt.get("action")
    transition = receipt.get("transition_kind")
    generation = receipt.get("generation")
    sequence = receipt.get("transition_sequence")
    source_reference = receipt.get("source_reference")
    occurred_at = receipt.get("occurred_at")
    if not (
        receipt.get("schema_version") in {None, 1}
        and isinstance(receipt_id, str)
        and receipt_id.startswith("sha256:")
        and isinstance(action, str)
        and action.strip()
        and isinstance(transition, str)
        and transition.strip()
        and isinstance(generation, str)
        and generation.strip()
        and isinstance(sequence, int)
        and sequence > 0
        and isinstance(source_reference, str)
        and _SAFE_REFERENCE.fullmatch(source_reference)
        and (occurred_at is None or isinstance(occurred_at, str))
    ):
        return None
    if receipt.get("schema_version") == 1:
        try:
            rebuilt = transition_receipt_v1(
                source_kind=str(receipt["source_kind"]),
                source_key=str(receipt["source_key"]),
                action=action,
                action_id=str(receipt["action_id"]),
                original_incident_id=(
                    str(receipt["original_incident_id"])
                    if receipt.get("original_incident_id") is not None
                    else None
                ),
                generation=generation,
                graph_id=(
                    str(receipt["graph_id"])
                    if receipt.get("graph_id") is not None
                    else None
                ),
                affected_work_ids=tuple(receipt.get("affected_work_ids") or ()),
                attempt_number=(
                    int(receipt["attempt_number"])
                    if receipt.get("attempt_number") is not None
                    else None
                ),
                claim_id=(
                    str(receipt["claim_id"])
                    if receipt.get("claim_id") is not None
                    else None
                ),
                sequence=sequence,
                transition_kind=transition,
                occurred_at=occurred_at if isinstance(occurred_at, str) else None,
                source_reference=source_reference,
                safe_payload=(
                    receipt["safe_payload"]
                    if isinstance(receipt.get("safe_payload"), Mapping)
                    else {}
                ),
            )
        except (KeyError, TypeError, ValueError):
            return None
        if rebuilt["receipt_id"] != receipt_id:
            return None
    safe_payload = receipt.get("safe_payload")
    target = safe_payload.get("target") if isinstance(safe_payload, Mapping) else None
    safe_target = _safe_text(target, target=True)
    if target is not None and safe_target is None:
        return None
    return action.strip()[:80], transition.strip()[:80], safe_target


def append_committed_recovery_receipt(
    root: Path,
    receipt: Mapping[str, Any],
    snapshot: Mapping[str, Any],
    *,
    provenance: Literal["direct", "reconciled", "legacy_unknown"] = "direct",
    deadline: float | None = None,
) -> dict[str, object]:
    """Append one safe committed receipt, returning durable ack or typed pending.

    Callers invoke this only after releasing the authoritative source lock.  The
    transcript store releases its graph fence before this function returns.
    """

    effective_deadline = deadline if deadline is not None else time.monotonic() + 30.0
    if time.monotonic() >= effective_deadline:
        return _pending(receipt, snapshot, "transcript_pending")
    safe = _safe_receipt(receipt, snapshot)
    if safe is None:
        return _pending(receipt, snapshot, "unsafe_or_missing_evidence")
    graph_id = _resolve_graph(receipt, root=root)
    if graph_id is None or time.monotonic() >= effective_deadline:
        return _pending(receipt, snapshot, "ambiguous_or_unknown_graph")
    action, transition, target = safe
    receipt_id = str(receipt["receipt_id"])
    entry_id = _entry_id(receipt, snapshot)
    source_key = f"recovery:{receipt_id}"
    attempt = receipt.get("attempt_number")
    parts = [f"{action}: {transition}"]
    if isinstance(attempt, int):
        parts.append(f"attempt {attempt}")
    if target is not None:
        parts.append(f"target {target}")
    body = " · ".join(parts)
    event_provenance = (
        "legacy_unknown" if receipt.get("schema_version") != 1 else provenance
    )
    try:
        append_transcript_message(
            graph_id,
            author="System · Recovery",
            body=body,
            root=root,
            source_key=source_key,
            occurred_at=(
                str(receipt["occurred_at"])
                if isinstance(receipt.get("occurred_at"), str)
                else None
            ),
            provenance=event_provenance,
            metadata={
                "kind": "recovery_milestone",
                "receipt_id": receipt_id,
                "entry_id": entry_id,
                "action": action,
                "action_id": str(receipt.get("action_id")),
                "generation": str(receipt.get("generation")),
                "attempt_number": attempt if isinstance(attempt, int) else None,
                "transition_kind": transition,
                "transition_sequence": int(receipt["transition_sequence"]),
                "target": target,
                "source_reference": str(receipt["source_reference"]),
            },
            deadline=effective_deadline,
        )
        with fenced_transcript_source_acknowledgement(
            graph_id,
            source_key=source_key,
            root=root,
            deadline=effective_deadline,
        ) as ack:
            ack = dict(ack)
    except (OSError, RuntimeError, ValueError, sqlite3.Error, TranscriptPendingError):
        return _pending(receipt, snapshot, "transcript_pending")
    return {
        "status": "committed",
        "receipt_id": receipt_id,
        "entry_id": entry_id,
        **ack,
    }


__all__ = ["append_committed_recovery_receipt"]
