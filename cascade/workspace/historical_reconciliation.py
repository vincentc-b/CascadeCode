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
_CLOSEOUT_OUTCOMES = {
    "missing_evidence", "material_mismatch", "stale_baseline", "acceptance_pending"
}


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


def build_acceptance_summary(
    *,
    owner_work_id: str,
    baseline_pair: Mapping[str, object],
    expected_target_revision: str,
    expected_tracking_revision: str,
    artifacts: Sequence[Mapping[str, object]],
    required_artifacts: Sequence[str],
    expected_artifacts: Mapping[str, Mapping[str, str]],
    architecture_reviews: Sequence[Mapping[str, object]],
    receipt_validations: Sequence[Mapping[str, object]],
    coverage_accounting: Mapping[str, object],
    accepted_deltas: Sequence[Mapping[str, object]] = (),
    historical_missing_receipts: Sequence[Mapping[str, object]] = (),
) -> dict[str, object]:
    """Build an exact-revision, fail-closed architecture acceptance summary.

    This is deliberately a pure verifier.  It consumes results from the existing
    review/promotion and reconciliation-receipt services; it never advances
    lifecycle state or treats repository reachability as architecture acceptance.
    """

    if not owner_work_id.strip():
        raise WorkspaceError("acceptance summary owner is required")
    for field, value in (
        ("expected target revision", expected_target_revision),
        ("expected tracking revision", expected_tracking_revision),
    ):
        if not _REVISION.fullmatch(value):
            raise WorkspaceError(f"{field} is invalid")

    blockers: list[dict[str, str]] = []

    def block(outcome: str, owner: str, prerequisite: str) -> None:
        if outcome not in _CLOSEOUT_OUTCOMES:
            raise WorkspaceError(f"unsupported acceptance outcome: {outcome}")
        if not owner.strip() or not prerequisite.strip():
            raise WorkspaceError("acceptance blockers require an owner and prerequisite")
        row = {"outcome": outcome, "owner": owner, "prerequisite": prerequisite}
        if row not in blockers:
            blockers.append(row)

    target_revision = baseline_pair.get("target_revision")
    tracking_revision = baseline_pair.get("tracking_revision")
    if target_revision != expected_target_revision or tracking_revision != expected_tracking_revision:
        block(
            "stale_baseline",
            "epic_034",
            "refresh the accepted Epic target/tracking pair and rerun exact-revision verification",
        )

    artifact_rows: list[dict[str, str]] = []
    artifact_names: set[str] = set()
    for artifact in artifacts:
        name = artifact.get("name")
        revision = artifact.get("revision")
        digest = artifact.get("sha256")
        if not isinstance(name, str) or not name.strip() or name in artifact_names:
            raise WorkspaceError("acceptance artifacts must have unique non-blank names")
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise WorkspaceError(f"acceptance artifact revision is invalid: {name}")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise WorkspaceError(f"acceptance artifact digest is invalid: {name}")
        artifact_names.add(name)
        artifact_rows.append({"name": name, "revision": revision, "sha256": digest})
        expected = expected_artifacts.get(name)
        if expected is not None and (
            revision != expected.get("revision") or digest != expected.get("sha256")
        ):
            block(
                "stale_baseline", owner_work_id,
                f"refresh changed acceptance artifact {name} and repeat its bound review",
            )
    for name in required_artifacts:
        if name not in artifact_names:
            block(
                "missing_evidence", owner_work_id,
                f"provide the exact revision and content digest for required artifact {name}",
            )

    review_rows: list[dict[str, object]] = []
    if not architecture_reviews:
        block(
            "missing_evidence", owner_work_id,
            "stage and obtain exact-revision architecture review evidence",
        )
    for review in architecture_reviews:
        unit_id = review.get("review_unit_id")
        artifact_revision = review.get("artifact_revision")
        status = review.get("status")
        owner = review.get("owner")
        accepted_revision_id = review.get("accepted_revision_id")
        if not isinstance(unit_id, str) or not unit_id.strip():
            raise WorkspaceError("architecture review unit ID is required")
        if not isinstance(artifact_revision, str) or not _REVISION.fullmatch(artifact_revision):
            raise WorkspaceError(f"architecture review revision is invalid: {unit_id}")
        if not isinstance(owner, str) or not owner.strip():
            raise WorkspaceError(f"architecture review owner is invalid: {unit_id}")
        if status == "accepted":
            if not isinstance(accepted_revision_id, str) or not accepted_revision_id.strip():
                block(
                    "missing_evidence", owner,
                    f"record the accepted revision ID for architecture review unit {unit_id}",
                )
        elif status in {"staged", "approved"}:
            block(
                "acceptance_pending", owner,
                f"approve and promote architecture review unit {unit_id} at {artifact_revision}",
            )
        else:
            block(
                "stale_baseline", owner,
                f"restage and re-review changed architecture review unit {unit_id}",
            )
        review_rows.append(dict(review))

    receipt_rows: list[dict[str, object]] = []
    tiers_seen: set[str] = set()
    for validation in receipt_validations:
        tier = validation.get("tier")
        work_id = validation.get("work_id")
        status = validation.get("status")
        code = validation.get("code")
        owner = validation.get("owner")
        receipt_id = validation.get("receipt_id")
        if tier not in {"task", "feature", "epic"} or tier in tiers_seen:
            raise WorkspaceError("receipt validations require each unique closeout tier")
        if not isinstance(work_id, str) or not work_id.strip():
            raise WorkspaceError(f"receipt validation work ID is invalid: {tier}")
        if not isinstance(owner, str) or not owner.strip():
            raise WorkspaceError(f"receipt validation owner is invalid: {tier}")
        tiers_seen.add(str(tier))
        if status == "passed" and isinstance(receipt_id, str) and receipt_id.strip():
            pass
        else:
            outcome = (
                "acceptance_pending" if code == "acceptance_pending" else
                "material_mismatch" if code == "material_mismatch" else
                "stale_baseline" if isinstance(code, str) and code.startswith("stale") else
                "missing_evidence"
            )
            block(
                outcome, owner,
                f"record and validate a current {tier} reconciliation receipt for {work_id}",
            )
        receipt_rows.append(dict(validation))
    for tier in ("task", "feature", "epic"):
        if tier not in tiers_seen:
            block(
                "missing_evidence", owner_work_id,
                f"run validate_reconciliation_closeout for the current {tier} revision",
            )

    material = coverage_accounting.get("material_unresolved")
    if not isinstance(material, int) or isinstance(material, bool) or material < 0:
        raise WorkspaceError("material unresolved count is invalid")
    if material:
        block(
            "material_mismatch", owner_work_id,
            f"resolve or obtain a human scope decision for {material} material replay rows",
        )

    delta_rows: list[dict[str, object]] = []
    delta_revisions: set[str] = set()
    for delta in accepted_deltas:
        revision = delta.get("revision")
        disposition = delta.get("disposition")
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise WorkspaceError("accepted delta revision is invalid")
        if disposition not in _DISPOSITIONS:
            raise WorkspaceError(f"accepted delta disposition is invalid: {revision}")
        if revision in delta_revisions:
            raise WorkspaceError(f"duplicate accepted delta revision: {revision}")
        delta_revisions.add(revision)
        if disposition == "unresolved":
            owner = delta.get("owner")
            prerequisite = delta.get("prerequisite")
            block(
                "material_mismatch",
                str(owner or owner_work_id),
                str(prerequisite or f"reconcile accepted delta {revision}"),
            )
        delta_rows.append(dict(delta))

    return {
        "version": 1,
        "owner_work_id": owner_work_id,
        "baseline_pair": dict(baseline_pair),
        "coverage_accounting": dict(coverage_accounting),
        "artifact_revisions": artifact_rows,
        "architecture_reviews": review_rows,
        "receipt_validations": receipt_rows,
        "historical_missing_receipts": [dict(row) for row in historical_missing_receipts],
        "accepted_deltas_after_reconciliation": delta_rows,
        "blockers": blockers,
        "clean_closeout": not blockers,
    }


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
    "build_acceptance_summary",
    "reconcile_replay_coverage",
    "write_reconciled_replay_ledger",
]
