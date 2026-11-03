"""Detect and durably hand off accepted reviews stranded on a stacked base."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path

from cascade.task.action_recovery import create_or_load_action, record_owner_decision
from cascade.workspace.integration_worktree import integration_branch, locate_trunk, merged_board


_ACTION_KIND = "stacked_review_integration_gap"
_ATTEMPT_BOUND = 1


@dataclass(frozen=True)
class StackedReviewIntegrationGap:
    """An accepted child review whose merge cannot reach its intended epic."""

    feature_id: str
    epic_id: str
    predecessor_id: str
    expected_target_branch: str
    accepted_review: dict[str, object]

    @property
    def action_id(self) -> str:
        return f"{self.feature_id}:stacked_review_integration_gap"


def classify_stacked_review_integration_gap(
    feature_id: str, record: dict[str, object], *, root: Path, accepted: bool
) -> StackedReviewIntegrationGap | None:
    """Classify an accepted PR merged into an already-integrated predecessor.

    The predecessor's closed review is the durable evidence that its feature
    has already crossed into the epic line.  A subsequently accepted PR still
    targeting that predecessor cannot be completed as though it reached the
    epic branch.
    """

    if not accepted:
        return None
    trunk = locate_trunk(root)
    target_branch = str(record.get("target_branch") or "").strip()
    prefix = "feat/"
    if not target_branch.startswith(prefix):
        return None
    predecessor_id = target_branch.removeprefix(prefix)
    if not predecessor_id:
        return None

    feature = merged_board(trunk).by_id.get(feature_id)
    if (
        feature is None
        or feature.tier != "feature"
        or not feature.parent
        or predecessor_id not in feature.depends_on
    ):
        return None

    # Import lazily so review's reconciliation loop can use this classifier.
    from cascade.review import review_record_for_feature

    predecessor_review = review_record_for_feature(predecessor_id, root=trunk)
    if predecessor_review is None or not predecessor_review.get("closed"):
        return None

    accepted_review = {
        field: record.get(field)
        for field in ("url", "number", "forge", "source_branch", "target_branch")
    }
    return StackedReviewIntegrationGap(
        feature_id=feature_id,
        epic_id=feature.parent,
        predecessor_id=predecessor_id,
        expected_target_branch=integration_branch("epic", feature.parent),
        accepted_review=accepted_review,
    )


def persist_stacked_review_integration_gap(
    gap: StackedReviewIntegrationGap, *, root: Path
) -> dict[str, object]:
    """Store one Epic Team decision request for the accepted review gap."""

    provenance = {
        "feature_id": gap.feature_id,
        "epic_id": gap.epic_id,
        "predecessor_id": gap.predecessor_id,
        "expected_target_branch": gap.expected_target_branch,
        "accepted_review": gap.accepted_review,
    }
    action = create_or_load_action(
        gap.action_id,
        _ACTION_KIND,
        root=locate_trunk(root),
        attempt_bound=_ATTEMPT_BOUND,
        metadata=provenance,
    )
    encoded = json.dumps(provenance, sort_keys=True, separators=(",", ":")).encode("utf-8")
    decision_id = f"stacked-review-integration-gap:{sha256(encoded).hexdigest()}"
    return record_owner_decision(
        str(action["action_id"]),
        decision_id,
        root=locate_trunk(root),
        owner="epic_team",
        metadata=provenance,
    )


def persist_if_stacked_review_integration_gap(
    feature_id: str, record: dict[str, object], *, root: Path, accepted: bool
) -> bool:
    """Persist the gap when present, returning whether feature completion is blocked."""

    gap = classify_stacked_review_integration_gap(
        feature_id, record, root=root, accepted=accepted
    )
    if gap is None:
        return False
    persist_stacked_review_integration_gap(gap, root=root)
    return True


__all__ = [
    "StackedReviewIntegrationGap",
    "classify_stacked_review_integration_gap",
    "persist_if_stacked_review_integration_gap",
    "persist_stacked_review_integration_gap",
]
