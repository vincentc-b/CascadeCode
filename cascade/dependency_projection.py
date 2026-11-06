"""Safe planning projection of authoritative dependency lifecycle status."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from cascade.board.types import BoardIndex, WorkMeta, WorkStatus, WorkTier
from cascade.dependency_evaluation import (
    DependencyEvaluation,
    DependencyOutcome,
    DependencyReason,
    DependencyStatus,
    evaluate_dependencies,
)

CompletionEvidence = Literal["canonical_completed_in_3_completed"]


@dataclass(frozen=True)
class DependencyStatusRow:
    """Allowlisted lifecycle facts for one declared dependency."""

    work_id: str
    tier: WorkTier | None
    status: WorkStatus | None
    column: str | None
    outcome: DependencyOutcome
    completion_evidence: CompletionEvidence | None
    unavailable_reason: DependencyReason | None

    def to_dict(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "tier": self.tier,
            "status": self.status,
            "column": self.column,
            "outcome": self.outcome,
            "completion_evidence": self.completion_evidence,
            "unavailable_reason": self.unavailable_reason,
        }


@dataclass(frozen=True)
class DependencyStatusProjection:
    """One timestamped view of an owning work item's declared dependencies.

    ``snapshot_fingerprint`` identifies only the allowlisted authoritative facts
    in this response. It is opaque evidence of the observed snapshot, not an
    authorization token. It is absent when no authoritative source was read.
    """

    owner_work_id: str
    observed_at: datetime
    snapshot_fingerprint: str | None
    outcome: DependencyOutcome
    dependencies: tuple[DependencyStatusRow, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "owner_work_id": self.owner_work_id,
            "observed_at": self.observed_at.astimezone(timezone.utc).isoformat(),
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "outcome": self.outcome,
            "dependencies": [row.to_dict() for row in self.dependencies],
        }


def project_dependency_status(
    meta: WorkMeta,
    *,
    root: Path,
    board: BoardIndex | None = None,
    observed_at: datetime | None = None,
) -> DependencyStatusProjection:
    """Project every declared dependency without exposing document content.

    A supplied board pins the projection to that caller-owned authoritative
    snapshot. Otherwise the shared evaluator resolves and reads the canonical
    merged board. Completion evidence comes only from its lifecycle result.
    """

    evaluation = evaluate_dependencies(meta, root=root, board=board)
    return project_dependency_evaluation(
        meta.id,
        evaluation,
        observed_at=observed_at,
    )


def project_dependency_evaluation(
    owner_work_id: str,
    evaluation: DependencyEvaluation,
    *,
    observed_at: datetime | None = None,
) -> DependencyStatusProjection:
    """Project an already-refreshed evaluation without rereading board state."""

    rows = tuple(_project_row(row) for row in evaluation.dependencies)
    source_available = not (
        evaluation.outcome == "dependency_status_unavailable" and not rows
    ) and not any(
        row.unavailable_reason == "dependency_source_unavailable" for row in rows
    )
    return DependencyStatusProjection(
        owner_work_id=owner_work_id,
        observed_at=(observed_at or datetime.now(timezone.utc)).astimezone(timezone.utc),
        snapshot_fingerprint=(
            _snapshot_fingerprint(owner_work_id, evaluation.outcome, rows)
            if source_available
            else None
        ),
        outcome=evaluation.outcome,
        dependencies=rows,
    )


def _project_row(row: DependencyStatus) -> DependencyStatusRow:
    return DependencyStatusRow(
        work_id=row.work_id,
        tier=row.tier,
        status=row.status,
        column=row.column,
        outcome=row.outcome,
        completion_evidence=(
            "canonical_completed_in_3_completed" if row.complete else None
        ),
        unavailable_reason=(
            row.reason if row.outcome == "dependency_status_unavailable" else None
        ),
    )


def _snapshot_fingerprint(
    owner_work_id: str,
    outcome: DependencyOutcome,
    rows: tuple[DependencyStatusRow, ...],
) -> str:
    safe_snapshot = {
        "owner_work_id": owner_work_id,
        "outcome": outcome,
        "dependencies": [row.to_dict() for row in rows],
    }
    encoded = json.dumps(
        safe_snapshot,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
