"""Owner-scoped, revision-pinned architecture context and historical replay."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Sequence

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.board.types import WorkDoc, WorkTier
from cascade.workspace.architecture import ArchitectureArtifactRef, read_architecture_artifact
from cascade.workspace.architecture_review import (
    ArchitectureReviewStore,
    ArchitectureReviewUnit,
)
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext

ContextRelation = Literal["owned", "ancestor"]
ArtifactKind = Literal["design", "model_contract", "model_fragment"]
ReplayScope = Literal["work_record", "git", "review"]
_REPLAY_SCOPES = frozenset({"work_record", "git", "review"})
_MAX_REPLAY_ROWS = 100


class ArchitectureContextDenied(PermissionError):
    """The requested context crosses a work-owner or evidence boundary."""


@dataclass(frozen=True)
class PlanningArtifact:
    kind: ArtifactKind
    relation: ContextRelation
    owner_work_id: str
    reference: ArchitectureArtifactRef
    content: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "relation": self.relation,
            "owner_work_id": self.owner_work_id,
            "reference": self.reference.to_dict(),
            "content": self.content,
        }


@dataclass(frozen=True)
class TierPlanningContext:
    work_id: str
    tier: WorkTier
    plan_revision: str
    ancestor_revisions: tuple[tuple[str, str], ...]
    artifacts: tuple[PlanningArtifact, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "work_id": self.work_id,
            "tier": self.tier,
            "plan_revision": self.plan_revision,
            "ancestor_revisions": dict(self.ancestor_revisions),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


@dataclass(frozen=True)
class HistoricalReplayEvidence:
    requester_work_id: str
    work_id: str
    evidence_scope: tuple[ReplayScope, ...]
    work_record: dict[str, object] | None
    git: dict[str, object] | None
    reviews: tuple[dict[str, object], ...]
    linked_reviews: tuple[dict[str, object], ...]
    unavailable: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "requester_work_id": self.requester_work_id,
            "work_id": self.work_id,
            "evidence_scope": list(self.evidence_scope),
            "work_record": self.work_record,
            "git": self.git,
            "reviews": list(self.reviews),
            "linked_reviews": list(self.linked_reviews),
            "unavailable": list(self.unavailable),
        }


def build_tier_planning_context(
    project: ProjectContext,
    work_id: str,
) -> TierPlanningContext:
    """Return only owner and pinned-ancestor architecture inputs for one team."""

    chain = _pinned_work_chain(project, work_id)
    current = chain[0]
    if current.sha is None:
        raise WorkspaceError("planning context requires a committed work revision")

    artifacts: list[PlanningArtifact] = []
    seen: set[tuple[str, str, str, str]] = set()
    store = ArchitectureReviewStore(project)
    for index, doc in enumerate(chain):
        relation: ContextRelation = "owned" if index == 0 else "ancestor"
        units = tuple(
            unit
            for unit in store.units_affecting(doc.meta.id)
            if unit.owner_work_id == doc.meta.id
        )
        latest_by_lineage: dict[str, ArchitectureReviewUnit] = {}
        for unit in reversed(units):
            latest_by_lineage.setdefault(unit.integration_lineage, unit)
        for unit in reversed(tuple(latest_by_lineage.values())):
            candidates: list[tuple[ArtifactKind, ArchitectureArtifactRef]] = [
                ("design", unit.design.reference)
            ]
            if unit.proposed_model is not None:
                candidates.append(("model_contract", unit.proposed_model.contract.reference))
                candidates.extend(
                    ("model_fragment", source.reference)
                    for source in unit.proposed_model.sources
                )
            for kind, reference in candidates:
                # A review closure can cite shared inputs. Planning context does not
                # turn that citation into permission to browse the shared owner's file.
                if reference.owning_work != doc.meta.id:
                    continue
                key = (
                    kind,
                    reference.destination_repository_key,
                    reference.revision,
                    reference.repository_path.as_posix(),
                )
                if key in seen:
                    continue
                seen.add(key)
                artifacts.append(
                    PlanningArtifact(
                        kind,
                        relation,
                        doc.meta.id,
                        reference,
                        read_architecture_artifact(project, reference),
                    )
                )

    ancestors = tuple(
        (doc.meta.id, _required_revision(doc)) for doc in chain[1:]
    )
    return TierPlanningContext(
        current.meta.id,
        current.meta.tier,
        current.sha,
        ancestors,
        tuple(artifacts),
    )


def read_historical_replay(
    project: ProjectContext,
    requester_work_id: str,
    work_id: str,
    evidence_scope: Sequence[str],
) -> HistoricalReplayEvidence:
    """Read a completed related record through an explicit, finite evidence scope."""

    requested = tuple(dict.fromkeys(evidence_scope))
    if not requested or any(scope not in _REPLAY_SCOPES for scope in requested):
        raise ArchitectureContextDenied(
            "historical replay requires work_record, git, and/or review evidence scope"
        )
    requester = _read_current(project, requester_work_id)
    target = _read_current(project, work_id)
    if not _related_for_replay(requester, target, project):
        raise ArchitectureContextDenied("historical replay target is outside the owner scope")
    if (
        target.meta.status != "completed"
        or target.meta.cancelled_at is not None
        or target.meta.cancellation_reason is not None
    ):
        raise ArchitectureContextDenied(
            "historical replay requires a completed, non-cancelled work record"
        )
    revision = _required_revision(target)
    store = ArchitectureReviewStore(project)
    all_owned_units = tuple(
        unit
        for unit in store.units_affecting(target.meta.id)
        if unit.owner_work_id == target.meta.id
    )
    owned_units = all_owned_units[-_MAX_REPLAY_ROWS:]

    work_record = None
    if "work_record" in requested:
        work_record = {
            "id": target.meta.id,
            "tier": target.meta.tier,
            "title": target.meta.title,
            "parent": target.meta.parent,
            "revision": revision,
            "body": target.body,
        }
    git = None
    unavailable: list[dict[str, str]] = []
    if (
        ("git" in requested or "review" in requested)
        and len(all_owned_units) > len(owned_units)
    ):
        unavailable.append(_unavailable("architecture", "review_units_truncated"))
    if "git" in requested:
        commits, commit_unavailable = _target_commit_evidence(project, target.meta.id)
        unavailable.extend(commit_unavailable)
        git = {
            "plan_revision": revision,
            "integration_branch": target.meta.integration_branch,
            "target_repository_key": project.target_repository_key,
            "commits": commits,
            "architecture_promotions": [
                _promotion_evidence(store, unit) for unit in owned_units
            ],
        }

    reviews: list[dict[str, object]] = []
    linked_reviews: tuple[dict[str, object], ...] = ()
    if "review" in requested:
        for unit in owned_units:
            review = store.get_review(unit.review_unit_id)
            reviews.append(
                {
                    "review_unit_id": unit.review_unit_id,
                    "status": unit.status,
                    "reviewed_tuple_digest": unit.reviewed_tuple_digest,
                    "plan_revision": unit.plan.revision,
                    "design_revision": unit.design.reference.revision,
                    "review": review.to_dict() if review is not None else None,
                }
            )
        linked_reviews, review_unavailable = _linked_review_evidence(
            project, target.meta.id
        )
        unavailable.extend(review_unavailable)
    return HistoricalReplayEvidence(
        requester.meta.id,
        target.meta.id,
        requested,  # type: ignore[arg-type]
        work_record,
        git,
        tuple(reviews),
        linked_reviews,
        tuple(unavailable),
    )


def _target_commit_evidence(
    project: ProjectContext, work_id: str
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Return only receipt-bound commits that are still reachable from target HEAD."""

    from cascade.workspace.reconciliation import ReconciliationReceiptStore

    try:
        receipts = ReconciliationReceiptStore(project).for_work(work_id)
    except WorkspaceError:
        return [], [_unavailable("git", "reconciliation_receipts_unreadable")]
    if not receipts:
        return [], [_unavailable("git", "reconciliation_receipt_missing")]
    rows: list[dict[str, object]] = []
    unavailable: list[dict[str, str]] = []
    seen: set[str] = set()
    for receipt in receipts:
        for revision in receipt.implementation_revisions:
            if revision in seen:
                continue
            seen.add(revision)
            if not _reachable_from_head(project.target.root, revision):
                unavailable.append(
                    _unavailable("git", "target_commit_unreachable", revision)
                )
                continue
            if len(rows) == _MAX_REPLAY_ROWS:
                unavailable.append(_unavailable("git", "target_commits_truncated"))
                return rows, unavailable
            rows.append(
                {
                    "commit_id": revision,
                    "provenance": "reconciliation_receipt",
                    "receipt_head": receipt.implementation_head,
                    "integration_lineage": receipt.integration_lineage,
                }
            )
    return rows, unavailable


def _linked_review_evidence(
    project: ProjectContext, work_id: str
) -> tuple[tuple[dict[str, object], ...], list[dict[str, str]]]:
    """Read the one durable forge link keyed to this exact work owner."""

    path = project.target.root / ".cascade" / "reviews.json"
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return (), [_unavailable("review", "linked_review_missing")]
    except (OSError, json.JSONDecodeError):
        return (), [_unavailable("review", "review_registry_unreadable")]
    record = state.get(work_id) if isinstance(state, dict) else None
    if not isinstance(record, dict):
        return (), [_unavailable("review", "linked_review_missing")]
    url = str(record.get("url") or record.get("review_url") or "").strip()
    if not url:
        return (), [_unavailable("review", "linked_review_missing")]

    description = record.get("description") or record.get("body")
    description = description if isinstance(description, str) and description.strip() else None
    source_revision = record.get("source_revision")
    source_revision = (
        str(source_revision).strip() if isinstance(source_revision, str) else ""
    )
    source_branch = record.get("source_branch")
    if not source_revision:
        if isinstance(source_branch, str) and source_branch.strip():
            source_revision = _resolve_commit(project.target.root, source_branch.strip()) or ""

    if description is None or not source_revision:
        remote = _authorized_review_evidence(
            project.target.root,
            record,
            url=url,
            source_branch=source_branch,
        )
        remote_description = remote.get("description")
        if (
            description is None
            and isinstance(remote_description, str)
            and remote_description.strip()
        ):
            description = remote_description
        if not source_revision and isinstance(remote.get("source_revision"), str):
            source_revision = remote["source_revision"].strip()

    unavailable: list[dict[str, str]] = []
    if description is None:
        unavailable.append(_unavailable("review", "review_description_unavailable", url))
    if not source_revision:
        unavailable.append(
            _unavailable("review", "review_source_revision_unavailable", url)
        )
    row = {
        "review_id": str(record.get("number") or url),
        "url": url,
        "forge": record.get("forge"),
        "description": description,
        "source_revision": source_revision or None,
    }
    return (row,), unavailable


def _authorized_review_evidence(
    root: Path,
    record: dict[str, object],
    *,
    url: str,
    source_branch: object,
) -> dict[str, object]:
    """Fetch only the exact durable review link through configured forge access."""

    from cascade.board.errors import GitError
    from cascade.tracking import MergeRequest, detect_forge, merge_request_snapshot

    recorded_forge = record.get("forge")
    forge = (
        recorded_forge
        if recorded_forge in {"github", "gitlab"}
        else detect_forge(root)
    )
    if forge not in {"github", "gitlab"}:
        return {}
    target_branch = record.get("target_branch")
    review = MergeRequest(
        url=url,
        number=str(record["number"]) if record.get("number") is not None else None,
        forge=forge,  # type: ignore[arg-type]
        source_branch=source_branch.strip() if isinstance(source_branch, str) else "",
        target_branch=target_branch.strip() if isinstance(target_branch, str) else "",
        draft=bool(record.get("draft", False)),
    )
    try:
        return merge_request_snapshot(root, review)
    except (GitError, OSError, ValueError):
        return {}


def _resolve_commit(root: Path, ref: str) -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--verify", "--end-of-options", f"{ref}^{{commit}}"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _reachable_from_head(root: Path, revision: str) -> bool:
    resolved = _resolve_commit(root, revision)
    if resolved is None:
        return False
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", resolved, "HEAD"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def _unavailable(scope: str, reason: str, detail: str = "") -> dict[str, str]:
    row = {"scope": scope, "reason": reason}
    if detail:
        row["detail"] = detail
    return row


def _promotion_evidence(
    store: ArchitectureReviewStore,
    unit: ArchitectureReviewUnit,
) -> dict[str, object]:
    accepted = store.resolve_current(unit.integration_lineage)
    if accepted is not None and accepted.accepted_review_unit_id != unit.review_unit_id:
        accepted = None
    pending = store.pending_promotion(unit.integration_lineage)
    if pending is not None and pending.approved_review_unit_id != unit.review_unit_id:
        pending = None
    return {
        "review_unit_id": unit.review_unit_id,
        "integration_lineage": unit.integration_lineage,
        "accepted": accepted.to_dict() if accepted is not None else None,
        "promotion": pending.to_dict() if pending is not None else None,
    }


def planning_context_prompt(project: ProjectContext, work_id: str) -> str:
    """Render deterministic context for a planning/SWE role prompt."""

    import json

    context = build_tier_planning_context(project, work_id)
    return (
        "Revision-pinned architecture context (owned and pinned ancestors only):\n"
        + json.dumps(context.to_dict(), sort_keys=True, separators=(",", ":"))
    )


def _pinned_work_chain(project: ProjectContext, work_id: str) -> tuple[WorkDoc, ...]:
    current = _read_current(project, work_id)
    chain = [current]
    child = current
    while child.meta.parent is not None:
        if child.meta.parent_rev is None:
            # Never substitute a live ancestor. Older active records may predate
            # parent pinning; expose the pinned prefix and stop at that boundary.
            break
        parent = read_doc(
            child.meta.parent,
            rev=child.meta.parent_rev,
            root=project.tracking.root,
        )
        expected = {"task": "feature", "feature": "epic"}.get(child.meta.tier)
        if expected is None or parent.meta.tier != expected:
            raise ArchitectureContextDenied("invalid work ancestry for planning context")
        chain.append(parent)
        child = parent
    return tuple(chain)


def _read_current(project: ProjectContext, work_id: str) -> WorkDoc:
    from cascade.workspace.doc_root import read_doc_resolved

    try:
        return read_doc_resolved(work_id, root=project.tracking.root)
    except NotFound:
        raise ArchitectureContextDenied(f"unknown work record {work_id}") from None


def _required_revision(doc: WorkDoc) -> str:
    if doc.sha is None:
        raise WorkspaceError(f"work record {doc.meta.id} is not revision pinned")
    return doc.sha


def _related_for_replay(
    requester: WorkDoc,
    target: WorkDoc,
    project: ProjectContext,
) -> bool:
    if requester.meta.id == target.meta.id:
        return True
    if target.meta.parent == requester.meta.id:
        return True
    # Ancestors are visible only through the requester's recorded parent edge;
    # this deliberately does not grant sibling or arbitrary same-epic access.
    child = requester
    while child.meta.parent is not None:
        if target.meta.id == child.meta.parent:
            return True
        if child.meta.parent_rev is None:
            return False
        try:
            child = read_doc(
                child.meta.parent,
                rev=child.meta.parent_rev,
                root=project.tracking.root,
            )
        except NotFound:
            return False
    return False


__all__ = [
    "ArchitectureContextDenied",
    "HistoricalReplayEvidence",
    "PlanningArtifact",
    "TierPlanningContext",
    "build_tier_planning_context",
    "planning_context_prompt",
    "read_historical_replay",
]
