"""Durable, scoped runtime Flex waivers in the provider recovery ledger."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Mapping

from cascade.agent.capability_contract import EffectiveSelection, EffectiveSelectionBatch
from cascade.agent.flex_continuation_contract import (
    DescendantWaiverStamp,
    FlexWaiver,
    InventoryFreshnessAudit,
    WaiverCandidate,
    WaiverScopeMember,
    contract_projection,
    waiver_applies,
)
from cascade.board.context import resolve_root
from cascade.watchdog.lock import process_lock


def persist_flex_waiver(waiver: FlexWaiver, *, root: Path) -> FlexWaiver:
    """Atomically store one non-secret authorization without touching plans."""

    repo = resolve_root(root)
    row = contract_projection(waiver)
    with process_lock:
        ledger = _read(repo)
        existing_rows = ledger.get("flex_waivers")
        rows = dict(existing_rows) if isinstance(existing_rows, dict) else {}
        previous = rows.get(waiver.waiver_id)
        if previous is not None and previous != row:
            raise ValueError("waiver_id already names different authorization")
        rows[waiver.waiver_id] = row
        ledger["flex_waivers"] = rows
        _write(repo, ledger)
    return waiver


def read_flex_waiver(waiver_id: str, *, root: Path) -> FlexWaiver | None:
    repo = resolve_root(root)
    with process_lock:
        rows = _read(repo).get("flex_waivers")
        row = rows.get(waiver_id) if isinstance(rows, dict) else None
    return _decode_waiver(row)


def apply_persisted_flex_waivers(
    batch: EffectiveSelectionBatch, *, root: Path
) -> EffectiveSelectionBatch:
    """Apply exactly one matching direct or normally stamped waiver per role."""

    repo = resolve_root(root)
    with process_lock:
        ledger = _read(repo)
    waiver_rows = ledger.get("flex_waivers")
    if not isinstance(waiver_rows, dict):
        waiver_rows = {}
    waivers = tuple(
        waiver
        for row in waiver_rows.values()
        if (waiver := _decode_waiver(row)) is not None
    )
    stamps = ledger.get("flex_waiver_stamps")
    if not isinstance(stamps, dict):
        stamps = {}
    roles = []
    for item in batch.roles:
        if not isinstance(item, EffectiveSelection) or not item.reviewed_flex_mode:
            roles.append(item)
            continue
        matches: list[tuple[FlexWaiver, str]] = []
        member_fingerprint = _member_fingerprint(item)
        stamp_row = stamps.get(_stamp_key(item.work_id, item.role))
        for waiver in waivers:
            stamp = _decode_stamp(stamp_row, waiver_id=waiver.waiver_id)
            candidate = WaiverCandidate(
                waiver_id=waiver.waiver_id,
                work_id=item.work_id,
                role=item.role,
                document_revision=item.document_revision,
                selection_member_fingerprint=member_fingerprint,
                stamp=stamp,
            )
            if waiver_applies(waiver.scope, candidate):
                source = next(
                    member.work_id
                    for member in waiver.scope
                    if (
                        member.work_id == item.work_id
                        and member.role == item.role
                        and member.document_revision == item.document_revision
                        and member.selection_member_fingerprint == member_fingerprint
                    )
                    or (
                        stamp is not None
                        and stamp.source_work_id == member.work_id
                        and stamp.source_role == member.role
                        and stamp.source_document_revision == member.document_revision
                        and stamp.source_member_fingerprint
                        == member.selection_member_fingerprint
                    )
                )
                matches.append((waiver, source))
        # Ambiguous authorization fails closed instead of choosing by recency.
        if len(matches) != 1:
            roles.append(item)
            continue
        waiver, source_work_id = matches[0]
        roles.append(
            replace(
                item,
                effective_flex_mode=waiver.effective_flex,
                flex_waiver_id=waiver.waiver_id,
                flex_waiver_receipt_id=waiver.receipt_id,
                flex_waiver_source_work_id=source_work_id,
            )
        )
    return replace(batch, roles=tuple(roles))


def stamp_minted_descendant_waivers(
    parent: EffectiveSelectionBatch,
    descendant: EffectiveSelectionBatch,
    *,
    role_mapping: Mapping[str, str],
    root: Path,
) -> tuple[DescendantWaiverStamp, ...]:
    """Carry a waiver only across a proven normal selection stamp."""

    repo = resolve_root(root)
    parent_roles = {item.role: item for item in parent.selections}
    descendant_roles = {item.role: item for item in descendant.selections}
    created: list[tuple[str, str, DescendantWaiverStamp]] = []
    for source_role, descendant_role in role_mapping.items():
        source = parent_roles.get(source_role)
        child = descendant_roles.get(descendant_role)
        if (
            source is None
            or child is None
            or source.flex_waiver_id is None
            or source.provider != child.provider
            or source.model_id != child.model_id
            or source.reasoning_level != child.reasoning_level
            or source.reviewed_flex_mode != child.reviewed_flex_mode
        ):
            continue
        stamp = DescendantWaiverStamp(
            waiver_id=source.flex_waiver_id,
            source_work_id=source.work_id,
            source_role=source.role,
            source_document_revision=source.document_revision,
            source_member_fingerprint=_member_fingerprint(source),
            descendant_document_revision=child.document_revision,
            descendant_member_fingerprint=_member_fingerprint(child),
        )
        created.append((child.work_id, child.role, stamp))
    if not created:
        return ()
    with process_lock:
        ledger = _read(repo)
        existing_stamps = ledger.get("flex_waiver_stamps")
        stamps = dict(existing_stamps) if isinstance(existing_stamps, dict) else {}
        for work_id, role, stamp in created:
            stamps[_stamp_key(work_id, role)] = contract_projection(stamp)
        ledger["flex_waiver_stamps"] = stamps
        _write(repo, ledger)
    return tuple(stamp for _, _, stamp in created)


def _member_fingerprint(selection: EffectiveSelection) -> str:
    from cascade.watchdog.model_resolve import selection_member_fingerprint

    return selection_member_fingerprint(selection)


def _decode_waiver(row: object) -> FlexWaiver | None:
    if not isinstance(row, dict):
        return None
    try:
        freshness = InventoryFreshnessAudit(**row["inventory_freshness"])
        scope = tuple(WaiverScopeMember(**member) for member in row["scope"])
        return FlexWaiver(
            waiver_id=row["waiver_id"],
            receipt_id=row["receipt_id"],
            scope=scope,
            authorized_subject=row["authorized_subject"],
            authorized_at=row["authorized_at"],
            inventory_freshness=freshness,
            requested_flex=row.get("requested_flex", True),
            effective_flex=row.get("effective_flex", False),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _decode_stamp(row: object, *, waiver_id: str) -> DescendantWaiverStamp | None:
    if not isinstance(row, dict) or row.get("waiver_id") != waiver_id:
        return None
    try:
        return DescendantWaiverStamp(**row)
    except (TypeError, ValueError):
        return None


def _stamp_key(work_id: str, role: str) -> str:
    return f"{work_id}:{role}"


def _path(root: Path) -> Path:
    return root / ".cascade" / "provider_recoveries.json"


def _read(root: Path) -> dict[str, object]:
    path = _path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {"version": 2}
    if not isinstance(payload, dict):
        return {"version": 2}
    return {**payload, "version": 2}


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
    "apply_persisted_flex_waivers",
    "persist_flex_waiver",
    "read_flex_waiver",
    "stamp_minted_descendant_waivers",
]
