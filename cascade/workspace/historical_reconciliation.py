"""Fail-closed reconciliation of pinned historical replay evidence.

This module deliberately does not discover evidence.  It reconciles the immutable
inventory produced by :mod:`historical_inventory` with G's existing replay ledger
and rejects any coverage claim that cannot cite that inventory and an exact
current-code or current-test revision.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Sequence

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.historical_inventory import HistoricalEvidenceInventory


Disposition = Literal["durable", "superseded", "no-impact", "unresolved"]
_REVISION = re.compile(r"^[0-9a-f]{40}$")
_DISPOSITIONS = {"durable", "superseded", "no-impact", "unresolved"}


@dataclass(frozen=True)
class ExactRevisionReference:
    """A current implementation, test, design, or model reference."""

    revision: str
    repository_path: str
    claim: str

    def to_dict(self) -> dict[str, str]:
        return {
            "revision": self.revision,
            "repository_path": self.repository_path,
            "claim": self.claim,
        }


@dataclass(frozen=True)
class MaterialGap:
    """An unresolved limitation with an accountable next prerequisite."""

    material: bool
    reason: str
    owner: str
    prerequisite: str

    def to_dict(self) -> dict[str, object]:
        return {
            "material": self.material,
            "reason": self.reason,
            "owner": self.owner,
            "prerequisite": self.prerequisite,
        }


@dataclass(frozen=True)
class ReplayDisposition:
    """One accountable disposition for one original row or accepted delta."""

    row_id: str
    disposition: Disposition
    rationale: str
    evidence_keys: tuple[str, ...]
    current_code_references: tuple[ExactRevisionReference, ...]
    current_test_references: tuple[ExactRevisionReference, ...]
    affected_requirement_ids: tuple[str, ...]
    affected_design_ids: tuple[str, ...]
    affected_model_ids: tuple[str, ...]
    review_references: tuple[str, ...] = ()
    material_gap: MaterialGap | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "row_id": self.row_id,
            "disposition": self.disposition,
            "rationale": self.rationale,
            "evidence_keys": list(self.evidence_keys),
            "review_references": list(self.review_references),
            "current_code_references": [
                reference.to_dict() for reference in self.current_code_references
            ],
            "current_test_references": [
                reference.to_dict() for reference in self.current_test_references
            ],
            "affected_requirement_ids": list(self.affected_requirement_ids),
            "affected_design_ids": list(self.affected_design_ids),
            "affected_model_ids": list(self.affected_model_ids),
            "material_gap": (
                self.material_gap.to_dict() if self.material_gap is not None else None
            ),
        }


def accepted_delta_rows(
    inventory: HistoricalEvidenceInventory,
) -> tuple[dict[str, object], ...]:
    """Return each accepted integration/delta revision exactly once."""

    if inventory.baseline_pair is None:
        raise WorkspaceError("historical reconciliation requires a baseline pair")
    rows: list[dict[str, object]] = []
    seen: set[str] = set()
    for source, values in (
        ("integration", inventory.baseline_pair.integrations),
        ("accepted_delta", inventory.baseline_pair.accepted_deltas),
    ):
        for value in values:
            revision = value.get("merge_revision") if source == "integration" else value.get("revision")
            if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
                raise WorkspaceError("accepted delta has an invalid revision")
            if revision in seen:
                raise WorkspaceError(f"duplicate accepted delta revision: {revision}")
            seen.add(revision)
            rows.append({
                "row_id": f"delta:{revision}",
                "kind": str(value.get("kind") or source),
                "revision": revision,
                "source": source,
                "work_id": value.get("work_id"),
                "review_id": value.get("review_id"),
            })
    return tuple(rows)


def reconcile_replay_coverage(
    inventory: HistoricalEvidenceInventory,
    existing_ledger: Mapping[str, object],
    dispositions: Sequence[ReplayDisposition],
) -> dict[str, object]:
    """Reconcile G's rows plus accepted deltas or reject incomplete claims."""

    raw_rows = existing_ledger.get("rows")
    if not isinstance(raw_rows, list) or not all(isinstance(row, dict) for row in raw_rows):
        raise WorkspaceError("replay ledger rows are invalid")
    original_rows = tuple(raw_rows)
    original_ids = _unique_ids(original_rows, "existing replay ledger")
    inventory_ids = _unique_ids(inventory.ledger, "historical inventory")
    if original_ids != inventory_ids:
        missing = sorted(inventory_ids - original_ids)
        extra = sorted(original_ids - inventory_ids)
        raise WorkspaceError(
            f"replay ledger differs from pinned inventory; missing={missing} extra={extra}"
        )

    deltas = accepted_delta_rows(inventory)
    expected_ids = original_ids | {str(row["row_id"]) for row in deltas}
    supplied = {row.row_id: row for row in dispositions}
    if len(supplied) != len(dispositions):
        raise WorkspaceError("duplicate replay disposition row")
    if set(supplied) != expected_ids:
        missing = sorted(expected_ids - set(supplied))
        extra = sorted(set(supplied) - expected_ids)
        raise WorkspaceError(
            f"replay coverage does not balance; missing={missing} extra={extra}"
        )

    reviews = {str(row.get("review_id")) for row in inventory.reviews}
    review_evidence = {
        key
        for row in inventory.reviews
        for key in (
            f"review:{row.get('review_id')}",
            f"review:{row.get('forge')}:{row.get('review_id')}",
        )
    }
    evidence = (
        {f"work:{row.get('work_id')}" for row in inventory.work_items}
        | {f"commit:{row.get('commit_id')}" for row in inventory.commits}
        | review_evidence
        | {str(row["row_id"]) for row in deltas}
    )
    no_impact_rationales: set[str] = set()
    for disposition in dispositions:
        _validate_disposition(disposition, evidence=evidence, reviews=reviews)
        if disposition.disposition == "no-impact":
            if disposition.rationale in no_impact_rationales:
                raise WorkspaceError("blanket no-impact rationale is not allowed")
            no_impact_rationales.add(disposition.rationale)

    source_by_id = {str(row["row_id"]): row for row in original_rows}
    source_by_id.update({str(row["row_id"]): row for row in deltas})
    rows: list[dict[str, object]] = []
    for row_id in sorted(expected_ids):
        row = dict(source_by_id[row_id])
        row.update(supplied[row_id].to_dict())
        rows.append(row)

    counts = {
        disposition: sum(row.disposition == disposition for row in dispositions)
        for disposition in sorted(_DISPOSITIONS)
    }
    material = sum(
        row.material_gap is not None and row.material_gap.material
        for row in dispositions
    )
    return {
        "version": 2,
        "target_repository_key": inventory.target_repository_key,
        "owner_work_id": inventory.owner_work_id,
        "inventory_sha256": existing_ledger.get("inventory_sha256"),
        "original_target_baseline": existing_ledger.get("original_target_baseline"),
        "evidence_index": existing_ledger.get("evidence_index"),
        "coverage_limits": existing_ledger.get("coverage_limits", []),
        "coverage_accounting": {
            "original_expected": len(original_ids),
            "original_covered": len(original_ids),
            "accepted_delta_expected": len(deltas),
            "accepted_delta_covered": len(deltas),
            "total_expected": len(expected_ids),
            "total_covered": len(rows),
            "duplicate_rows": 0,
            "missing_rows": 0,
            "dispositions": counts,
            "material_unresolved": material,
        },
        "rows": rows,
    }


def write_reconciled_replay_ledger(path: Path, ledger: Mapping[str, object]) -> None:
    """Atomically replace the existing replay ledger with reconciled rows."""

    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(ledger, indent=2, sort_keys=True) + "\n")
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _unique_ids(rows: Sequence[Mapping[str, object]], source: str) -> set[str]:
    identifiers = [row.get("row_id") for row in rows]
    if not all(isinstance(value, str) and value for value in identifiers):
        raise WorkspaceError(f"{source} contains an invalid row ID")
    result = {str(value) for value in identifiers}
    if len(result) != len(identifiers):
        raise WorkspaceError(f"{source} contains duplicate row IDs")
    return result


def _validate_disposition(
    row: ReplayDisposition, *, evidence: set[str], reviews: set[str]
) -> None:
    if row.disposition not in _DISPOSITIONS:
        raise WorkspaceError(f"invalid replay disposition: {row.row_id}")
    if row.row_id not in row.rationale:
        raise WorkspaceError(f"replay rationale is not row-specific: {row.row_id}")
    if not row.evidence_keys or not set(row.evidence_keys) <= evidence:
        raise WorkspaceError(f"unsupported evidence claim: {row.row_id}")
    if row.row_id not in row.evidence_keys:
        raise WorkspaceError(f"row does not cite its source identity: {row.row_id}")
    if not set(row.review_references) <= reviews:
        raise WorkspaceError(f"unknown review evidence: {row.row_id}")
    if not row.current_code_references and not row.current_test_references:
        raise WorkspaceError(f"current revision evidence is missing: {row.row_id}")
    for reference in (*row.current_code_references, *row.current_test_references):
        if (
            not _REVISION.fullmatch(reference.revision)
            or not reference.repository_path.strip()
            or not reference.claim.strip()
        ):
            raise WorkspaceError(f"invalid exact revision reference: {row.row_id}")
    affected = (
        row.affected_requirement_ids
        or row.affected_design_ids
        or row.affected_model_ids
    )
    if not affected:
        raise WorkspaceError(f"affected architecture IDs are missing: {row.row_id}")
    if row.disposition == "unresolved":
        if row.material_gap is None or not all((
            row.material_gap.reason.strip(),
            row.material_gap.owner.strip(),
            row.material_gap.prerequisite.strip(),
        )):
            raise WorkspaceError(f"unresolved materiality is missing: {row.row_id}")
    elif row.material_gap is not None:
        raise WorkspaceError(f"resolved row carries a material gap: {row.row_id}")


__all__ = [
    "ExactRevisionReference",
    "MaterialGap",
    "ReplayDisposition",
    "accepted_delta_rows",
    "reconcile_replay_coverage",
    "write_reconciled_replay_ledger",
]
