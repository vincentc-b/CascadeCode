"""Revision-pinned inventory for historical architecture reconstruction.

The inventory is deliberately evidence, not a design generator.  Commit messages,
work narratives, and review descriptions are retained as leads until a later pass
checks them against the pinned code and tests.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Literal, Mapping, Sequence

from cascade.board.errors import GitError, SchemaError
from cascade.board.parse import parse_text
from cascade.board.types import WorkDoc
from cascade.workspace.architecture_context import (
    _authorized_review_evidence,
    _unavailable,
)
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import ProjectContext

_SCHEMA_VERSION = 2
_CONTRACT_VERSION = 1
_WORK_PATH = re.compile(r"^docs/(epics|features|tasks)/3_completed/[^/]+\.md$")
_WORK_ID = re.compile(r"\b(?:epic|feat|task)_\d+(?:_\d+){0,2}\b")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
InventoryOutcome = Literal["unresolved"]


@dataclass(frozen=True)
class BaselinePair:
    """Accepted Epic repositories plus the independently pinned G artifact."""

    target_repository_key: str
    target_revision: str
    tracking_repository_key: str
    tracking_revision: str
    g_artifact_repository_key: str
    g_artifact_repository_role: Literal["target", "tracking"]
    g_artifact_path: str
    g_artifact_revision: str
    g_artifact_sha256: str
    integrations: tuple[dict[str, object], ...] = ()
    accepted_deltas: tuple[dict[str, object], ...] = ()
    version: int = _CONTRACT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "target_repository_key": self.target_repository_key,
            "target_revision": self.target_revision,
            "tracking_repository_key": self.tracking_repository_key,
            "tracking_revision": self.tracking_revision,
            "g_artifact_repository_key": self.g_artifact_repository_key,
            "g_artifact_repository_role": self.g_artifact_repository_role,
            "g_artifact_path": self.g_artifact_path,
            "g_artifact_revision": self.g_artifact_revision,
            "g_artifact_sha256": self.g_artifact_sha256,
            "integrations": list(self.integrations),
            "accepted_deltas": list(self.accepted_deltas),
        }

    @classmethod
    def from_dict(cls, value: object) -> "BaselinePair":
        try:
            if not isinstance(value, dict) or value.get("version") != _CONTRACT_VERSION:
                raise ValueError
            pair = cls(
                target_repository_key=value["target_repository_key"],
                target_revision=value["target_revision"],
                tracking_repository_key=value["tracking_repository_key"],
                tracking_revision=value["tracking_revision"],
                g_artifact_repository_key=value["g_artifact_repository_key"],
                g_artifact_repository_role=value["g_artifact_repository_role"],
                g_artifact_path=value["g_artifact_path"],
                g_artifact_revision=value["g_artifact_revision"],
                g_artifact_sha256=value["g_artifact_sha256"],
                integrations=tuple(value.get("integrations", ())),
                accepted_deltas=tuple(value.get("accepted_deltas", ())),
            )
            _validate_baseline_pair_shape(pair)
            return pair
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid historical baseline pair") from exc


@dataclass(frozen=True)
class OwnerEvidenceHandoff:
    """Revision-pinned child evidence supplied by its authorized Feature owner."""

    work_id: str
    owning_feature: str
    authorized_source: str
    availability: Literal["available", "unavailable", "pending_owner_handoff"]
    record_revision: str | None
    source_repository: str | None = None
    source_path: str | None = None
    owner_request_id: str | None = None
    intent_excerpt: str | None = None
    intent_source_reference: str | None = None
    verification_excerpt: str | None = None
    verification_source_reference: str | None = None
    unavailable_reason: str | None = None
    responsible_owner: str | None = None
    title: str | None = None
    version: int = _CONTRACT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "work_id": self.work_id,
            "owning_feature": self.owning_feature,
            "authorized_source": self.authorized_source,
            "availability": self.availability,
            "record_revision": self.record_revision,
            "source_repository": self.source_repository,
            "source_path": self.source_path,
            "owner_request_id": self.owner_request_id,
            "intent_excerpt": self.intent_excerpt,
            "intent_source_reference": self.intent_source_reference,
            "verification_excerpt": self.verification_excerpt,
            "verification_source_reference": self.verification_source_reference,
            "unavailable_reason": self.unavailable_reason,
            "responsible_owner": self.responsible_owner,
            "title": self.title,
        }

    @classmethod
    def from_dict(cls, value: object) -> "OwnerEvidenceHandoff":
        try:
            if not isinstance(value, dict) or value.get("version") != _CONTRACT_VERSION:
                raise ValueError
            handoff = cls(
                work_id=value["work_id"],
                owning_feature=value["owning_feature"],
                authorized_source=value["authorized_source"],
                availability=value["availability"],
                record_revision=value["record_revision"],
                source_repository=value.get("source_repository"),
                source_path=value.get("source_path"),
                owner_request_id=value.get("owner_request_id"),
                intent_excerpt=value.get("intent_excerpt"),
                intent_source_reference=value.get("intent_source_reference"),
                verification_excerpt=value.get("verification_excerpt"),
                verification_source_reference=value.get(
                    "verification_source_reference"
                ),
                unavailable_reason=value.get("unavailable_reason"),
                responsible_owner=value.get("responsible_owner"),
                title=value.get("title"),
            )
            _validate_owner_evidence_handoffs((handoff,))
            return handoff
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid owner evidence handoff") from exc


@dataclass(frozen=True)
class ReviewEvidence:
    """Captured forge evidence; current text is not historical merge-time text."""

    review_id: str
    forge: str
    repository_key: str
    url: str
    work_ids: tuple[str, ...]
    captured_at: str
    description: str | None
    description_sha256: str | None
    description_provenance: Literal[
        "current_snapshot", "merge_time_archive", "unavailable"
    ]
    source_revision: str | None = None
    head_revision: str | None = None
    base_revision: str | None = None
    merge_revision: str | None = None
    linked_commit_ids: tuple[str, ...] = ()
    unavailable_fields: Mapping[str, str] = field(default_factory=dict)
    version: int = _CONTRACT_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "review_id": self.review_id,
            "forge": self.forge,
            "repository_key": self.repository_key,
            "url": self.url,
            "work_ids": list(self.work_ids),
            "captured_at": self.captured_at,
            "description": self.description,
            "description_sha256": self.description_sha256,
            "description_provenance": self.description_provenance,
            "source_revision": self.source_revision,
            "head_revision": self.head_revision,
            "base_revision": self.base_revision,
            "merge_revision": self.merge_revision,
            "linked_commit_ids": list(self.linked_commit_ids),
            "unavailable_fields": dict(self.unavailable_fields),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ReviewEvidence":
        try:
            if not isinstance(value, dict) or value.get("version") != _CONTRACT_VERSION:
                raise ValueError
            unavailable = value.get("unavailable_fields", {})
            if not isinstance(unavailable, dict) or not all(
                isinstance(key, str) and isinstance(reason, str)
                for key, reason in unavailable.items()
            ):
                raise ValueError
            evidence = cls(
                review_id=value["review_id"],
                forge=value["forge"],
                repository_key=value["repository_key"],
                url=value["url"],
                work_ids=tuple(value["work_ids"]),
                captured_at=value["captured_at"],
                description=value["description"],
                description_sha256=value["description_sha256"],
                description_provenance=value["description_provenance"],
                source_revision=value.get("source_revision"),
                head_revision=value.get("head_revision"),
                base_revision=value.get("base_revision"),
                merge_revision=value.get("merge_revision"),
                linked_commit_ids=tuple(value.get("linked_commit_ids", ())),
                unavailable_fields=unavailable,
            )
            if not all(isinstance(item, str) for item in (
                evidence.review_id,
                evidence.forge,
                evidence.repository_key,
                evidence.url,
                evidence.captured_at,
                *evidence.work_ids,
                *evidence.linked_commit_ids,
            )):
                raise ValueError
            return evidence
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid review evidence") from exc


@dataclass(frozen=True)
class AuthorizedWorkHandoff:
    """Owner-authorized work evidence supplied without widening board access."""

    work_id: str
    tier: str
    parent: str | None
    title: str
    evidence_revision: str | None
    narrative: str | None
    completion_evidence: Mapping[str, str]
    unavailable_reason: str | None = None


@dataclass(frozen=True)
class AuthorizedReviewHandoff:
    """A review lead supplied by an authorized owner or forge integration."""

    review_id: str
    url: str
    forge: str | None
    work_ids: tuple[str, ...]
    description: str | None = None
    source_revision: str | None = None
    merge_revision: str | None = None
    acceptance_status: str = "unknown"
    status_evidence_revision: str | None = None


@dataclass(frozen=True)
class HistoricalEvidenceInventory:
    """Immutable inputs and initial replay rows for one reconstruction pass."""

    owner_work_id: str
    target_repository_key: str
    target_baseline: str
    tracking_baseline: str
    work_items: tuple[dict[str, object], ...]
    commits: tuple[dict[str, object], ...]
    reviews: tuple[dict[str, object], ...]
    ledger: tuple[dict[str, object], ...]
    unavailable: tuple[dict[str, str], ...]
    baseline_pair: BaselinePair | None = None
    owner_evidence_handoffs: tuple[dict[str, object], ...] = ()
    version: int = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        value: dict[str, object] = {
            "version": self.version,
            "owner_work_id": self.owner_work_id,
            "target_repository_key": self.target_repository_key,
            "target_baseline": self.target_baseline,
            "tracking_baseline": self.tracking_baseline,
            "work_items": list(self.work_items),
            "commits": list(self.commits),
            "reviews": list(self.reviews),
            "ledger": list(self.ledger),
            "unavailable": list(self.unavailable),
            "owner_evidence_handoffs": list(self.owner_evidence_handoffs),
        }
        if self.baseline_pair is not None:
            value["baseline_pair"] = self.baseline_pair.to_dict()
        return value

    @classmethod
    def from_dict(cls, value: object) -> "HistoricalEvidenceInventory":
        try:
            if not isinstance(value, dict) or value.get("version") not in {1, _SCHEMA_VERSION}:
                raise ValueError
            baseline_value = value.get("baseline_pair")
            inventory = cls(
                owner_work_id=value["owner_work_id"],
                target_repository_key=value["target_repository_key"],
                target_baseline=value["target_baseline"],
                tracking_baseline=value["tracking_baseline"],
                work_items=tuple(value["work_items"]),
                commits=tuple(value["commits"]),
                reviews=tuple(value["reviews"]),
                ledger=tuple(value["ledger"]),
                unavailable=tuple(value["unavailable"]),
                baseline_pair=(
                    BaselinePair.from_dict(baseline_value)
                    if baseline_value is not None else None
                ),
                owner_evidence_handoffs=tuple(
                    value.get("owner_evidence_handoffs", ())
                ),
                version=value["version"],
            )
            if not all(
                isinstance(item, str)
                for item in (
                    inventory.owner_work_id,
                    inventory.target_repository_key,
                    inventory.target_baseline,
                    inventory.tracking_baseline,
                )
            ):
                raise ValueError
            if not _REVISION.fullmatch(inventory.target_baseline):
                raise ValueError
            if not _REVISION.fullmatch(inventory.tracking_baseline):
                raise ValueError
            if not all(isinstance(row, dict) for rows in (
                inventory.work_items, inventory.commits, inventory.reviews,
                inventory.ledger, inventory.unavailable,
                inventory.owner_evidence_handoffs,
            ) for row in rows):
                raise ValueError
            return inventory
        except (KeyError, TypeError, ValueError) as exc:
            raise WorkspaceError("invalid historical evidence inventory") from exc


def inventory_path(project: ProjectContext) -> Path:
    """Return the versioned inventory home in the configured architecture repo."""

    return project.editable_architecture_root / "historical-evidence-inventory.json"


def build_historical_inventory(
    project: ProjectContext,
    owner_work_id: str,
    *,
    target_revision: str = "HEAD",
    tracking_revision: str = "HEAD",
    authorized_work_handoffs: Sequence[AuthorizedWorkHandoff] = (),
    authorized_review_handoffs: Sequence[AuthorizedReviewHandoff] = (),
    baseline_pair: BaselinePair | None = None,
    owner_evidence_handoffs: Sequence[OwnerEvidenceHandoff] = (),
    review_evidence: Sequence[ReviewEvidence] = (),
) -> HistoricalEvidenceInventory:
    """Snapshot all eligible work and reachable target history at exact commits.

    The caller supplies the agreed baselines.  Both are canonicalized to commit
    IDs before any evidence is read, so branch movement during a scan cannot
    silently change its contents.
    """

    if baseline_pair is not None:
        _validate_baseline_pair(project, baseline_pair)
        if target_revision != "HEAD" and target_revision != baseline_pair.target_revision:
            raise WorkspaceError("target revision does not match accepted baseline pair")
        if tracking_revision != "HEAD" and tracking_revision != baseline_pair.tracking_revision:
            raise WorkspaceError("tracking revision does not match accepted baseline pair")
        target_revision = baseline_pair.target_revision
        tracking_revision = baseline_pair.tracking_revision
    target = _resolve_revision(project.target.root, target_revision)
    tracking = _resolve_revision(project.tracking.root, tracking_revision)
    handoffs = _validate_handoffs(authorized_work_handoffs)
    owner_handoffs = _validate_owner_evidence_handoffs(owner_evidence_handoffs)
    for handoff in owner_handoffs.values():
        if (
            handoff.record_revision is not None
            and not _is_ancestor(
                project.tracking.root, handoff.record_revision, tracking
            )
        ):
            raise WorkspaceError(
                f"owner evidence revision is unreachable: {handoff.work_id}"
            )
    overlap = set(handoffs) & set(owner_handoffs)
    if overlap:
        raise WorkspaceError(
            "duplicate legacy and owner evidence handoff: "
            + ",".join(sorted(overlap))
        )
    # A handoff is also an access boundary: do not open a board document whose
    # owner supplied a deliberately bounded record (for example a parent
    # closeout that cannot disclose its child task content).
    work_docs, unavailable = _completed_work(
        project.tracking.root,
        tracking,
        excluded_work_ids=set(handoffs) | set(owner_handoffs),
    )
    work_ids = (
        {doc.meta.id for doc, _, _ in work_docs}
        | set(handoffs)
        | set(owner_handoffs)
    )

    receipt_map, receipt_unavailable = _receipt_commit_map(
        project.target.root, target, work_ids
    )
    unavailable.extend(receipt_unavailable)
    review_rows, review_by_work, review_unavailable = _review_inventory(
        project, target, work_ids
    )
    unavailable.extend(review_unavailable)
    handoff_review_unavailable = _merge_authorized_reviews(
        review_rows,
        review_by_work,
        authorized_review_handoffs,
        work_ids,
    )
    unavailable.extend(handoff_review_unavailable)
    unavailable.extend(_merge_review_evidence(
        review_rows, review_by_work, review_evidence, work_ids,
        project=project, accepted_target_revision=target,
    ))

    commits = _reachable_commits(
        project.target.root, target, receipt_map, review_rows
    )
    merge_reviews, merge_unavailable = _merge_commit_reviews(
        project.target.root, commits, {str(row["url"]) for row in review_rows}
    )
    unavailable.extend(merge_unavailable)
    if merge_reviews:
        review_rows.extend(merge_reviews)
        review_rows.sort(key=lambda row: str(row["url"]))
    reachable_ids = {row["commit_id"] for row in commits}
    for review in review_rows:
        source_revision = review.get("source_revision")
        if isinstance(source_revision, str) and _REVISION.fullmatch(source_revision):
            review["source_revision_status"] = (
                "reachable" if source_revision in reachable_ids
                else "unreachable_from_target_baseline"
            )
            if source_revision not in reachable_ids:
                unavailable.append(
                    _unavailable(
                        "review", "review_source_revision_unreachable",
                        f"{review['url']}:{source_revision}",
                    )
                )
        else:
            review["source_revision_status"] = "unavailable"
    for revision, owners in sorted(receipt_map.items()):
        if revision not in reachable_ids:
            unavailable.append(
                _unavailable(
                    "git", "target_commit_unreachable",
                    f"{revision}:{','.join(sorted(owners))}",
                )
            )

    work_rows: list[dict[str, object]] = []
    ledger: list[dict[str, object]] = []
    for doc, evidence_revision, repository_path in work_docs:
        commit_ids = sorted(
            revision for revision, owners in receipt_map.items()
            if doc.meta.id in owners and revision in reachable_ids
        )
        review_ids = list(review_by_work.get(doc.meta.id, ()))
        work_rows.append(
            {
                "work_id": doc.meta.id,
                "tier": doc.meta.tier,
                "title": doc.meta.title,
                "parent": doc.meta.parent,
                "repository_path": repository_path,
                "evidence_revision": evidence_revision,
                "narrative": doc.body,
                "narrative_status": "lead_pending_current_code_check",
                "commit_ids": commit_ids,
                "review_ids": review_ids,
            }
        )
        if not commit_ids:
            unavailable.append(
                _unavailable("git", "reconciliation_receipt_missing", doc.meta.id)
            )
        ledger.append(_initial_ledger_row(
            f"work:{doc.meta.id}", "work_item", doc.meta.id,
            [evidence_revision, *commit_ids], review_ids,
        ))

    for work_id, handoff in handoffs.items():
        commit_ids = sorted(
            revision for revision, owners in receipt_map.items()
            if work_id in owners and revision in reachable_ids
        )
        review_ids = list(review_by_work.get(work_id, ()))
        work_rows.append({
            "work_id": work_id,
            "tier": handoff.tier,
            "title": handoff.title,
            "parent": handoff.parent,
            "repository_path": None,
            "evidence_revision": handoff.evidence_revision,
            "narrative": handoff.narrative,
            "narrative_status": (
                "lead_pending_current_code_check"
                if handoff.narrative is not None else "unavailable"
            ),
            "completion_evidence": dict(handoff.completion_evidence),
            "unavailable_reason": handoff.unavailable_reason,
            "commit_ids": commit_ids,
            "review_ids": review_ids,
        })
        if not commit_ids:
            unavailable.append(
                _unavailable("git", "reconciliation_receipt_missing", work_id)
            )
        if handoff.unavailable_reason is not None:
            unavailable.append(_unavailable(
                "work_record", handoff.unavailable_reason, work_id
            ))
        ledger_row = _initial_ledger_row(
            f"work:{work_id}", "work_item", work_id,
            ([handoff.evidence_revision] if handoff.evidence_revision else [])
            + commit_ids,
            review_ids,
        )
        ledger_row.update({
            "revision": handoff.evidence_revision,
            "completion_evidence": dict(handoff.completion_evidence),
            "unavailable_reason": handoff.unavailable_reason,
        })
        ledger.append(ledger_row)

    for work_id, handoff in owner_handoffs.items():
        commit_ids = sorted(
            revision for revision, owners in receipt_map.items()
            if work_id in owners and revision in reachable_ids
        )
        review_ids = list(review_by_work.get(work_id, ()))
        row = handoff.to_dict()
        work_rows.append({
            "work_id": work_id,
            "tier": "task",
            "title": handoff.title or work_id,
            "parent": handoff.owning_feature,
            "repository_path": None,
            "evidence_revision": handoff.record_revision,
            "narrative": None,
            "narrative_status": (
                "authorized_excerpts_available"
                if handoff.availability == "available" else handoff.availability
            ),
            "owner_evidence_handoff": row,
            "unavailable_reason": handoff.unavailable_reason,
            "commit_ids": commit_ids,
            "review_ids": review_ids,
        })
        if not commit_ids:
            unavailable.append(
                _unavailable("git", "reconciliation_receipt_missing", work_id)
            )
        if handoff.availability != "available":
            unavailable.append(_unavailable(
                "work_record", handoff.unavailable_reason or "unavailable", work_id
            ))
        ledger_row = _initial_ledger_row(
            f"work:{work_id}", "work_item", work_id,
            ([handoff.record_revision] if handoff.record_revision else [])
            + commit_ids,
            review_ids,
        )
        ledger_row.update({
            "revision": handoff.record_revision,
            "owner_evidence_handoff": row,
            "unavailable_reason": handoff.unavailable_reason,
        })
        ledger.append(ledger_row)

    covered = set(receipt_map) & reachable_ids
    for commit in commits:
        if commit["commit_id"] in covered:
            continue
        ledger.append(_initial_ledger_row(
            f"commit:{commit['commit_id']}", "uncovered_commit", None,
            [commit["commit_id"]], commit["review_ids"],
        ))

    # Repeated limitations are not extra evidence.  Preserve a stable order and
    # exact detail while collapsing overlap between work, commit, and review scans.
    unavailable = list({
        (row["scope"], row["reason"], row.get("detail", "")): row
        for row in unavailable
    }.values())
    unavailable.sort(key=lambda row: (
        row["scope"], row["reason"], row.get("detail", "")
    ))
    return HistoricalEvidenceInventory(
        owner_work_id=owner_work_id,
        target_repository_key=project.target_repository_key,
        target_baseline=target,
        tracking_baseline=tracking,
        work_items=tuple(sorted(work_rows, key=lambda row: str(row["work_id"]))),
        commits=tuple(commits),
        reviews=tuple(review_rows),
        ledger=tuple(sorted(ledger, key=lambda row: str(row["row_id"]))),
        unavailable=tuple(unavailable),
        baseline_pair=baseline_pair,
        owner_evidence_handoffs=tuple(
            owner_handoffs[key].to_dict() for key in sorted(owner_handoffs)
        ),
    )


def pin_historical_inventory(
    project: ProjectContext,
    owner_work_id: str,
    *,
    target_revision: str = "HEAD",
    tracking_revision: str = "HEAD",
    authorized_work_handoffs: Sequence[AuthorizedWorkHandoff] = (),
    authorized_review_handoffs: Sequence[AuthorizedReviewHandoff] = (),
    baseline_pair: BaselinePair | None = None,
    owner_evidence_handoffs: Sequence[OwnerEvidenceHandoff] = (),
    review_evidence: Sequence[ReviewEvidence] = (),
    path: Path | None = None,
) -> HistoricalEvidenceInventory:
    """Build and atomically persist a reproducible historical inventory."""

    inventory = build_historical_inventory(
        project,
        owner_work_id,
        target_revision=target_revision,
        tracking_revision=tracking_revision,
        authorized_work_handoffs=authorized_work_handoffs,
        authorized_review_handoffs=authorized_review_handoffs,
        baseline_pair=baseline_pair,
        owner_evidence_handoffs=owner_evidence_handoffs,
        review_evidence=review_evidence,
    )
    destination = path or inventory_path(project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(inventory.to_dict(), indent=2, sort_keys=True) + "\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return inventory


def read_historical_inventory(
    project: ProjectContext, *, path: Path | None = None
) -> HistoricalEvidenceInventory:
    """Read the persisted inventory without refreshing any of its evidence."""

    source = path or inventory_path(project)
    try:
        return HistoricalEvidenceInventory.from_dict(
            json.loads(source.read_text(encoding="utf-8"))
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise WorkspaceError(f"invalid historical evidence inventory: {source}") from exc


def _completed_work(
    root: Path, baseline: str, *, excluded_work_ids: set[str] | None = None
) -> tuple[list[tuple[WorkDoc, str, str]], list[dict[str, str]]]:
    paths = _git_lines(root, ["ls-tree", "-r", "--name-only", baseline, "--", "docs"])
    rows: list[tuple[WorkDoc, str, str]] = []
    unavailable: list[dict[str, str]] = []
    seen: set[str] = set()
    excluded = excluded_work_ids or set()
    for relative in paths:
        if not _WORK_PATH.fullmatch(relative):
            continue
        filename = Path(relative).name
        if any(
            filename == f"{work_id}.md"
            or filename.startswith(f"{work_id}_")
            for work_id in excluded
        ):
            continue
        try:
            text = _git_text(root, ["show", f"{baseline}:{relative}"])
            doc = parse_text(text, root / relative)
        except (GitError, SchemaError):
            unavailable.append(_unavailable("work_record", "work_record_unreadable", relative))
            continue
        if (
            doc.meta.status != "completed"
            or doc.meta.cancelled_at is not None
            or doc.meta.cancellation_reason is not None
        ):
            continue
        if doc.meta.id in seen:
            unavailable.append(_unavailable("work_record", "ambiguous_duplicate_work_id", doc.meta.id))
            continue
        seen.add(doc.meta.id)
        evidence_revision = _git_text(
            root, ["log", "-1", "--format=%H", baseline, "--", relative]
        ).strip()
        if not _REVISION.fullmatch(evidence_revision):
            unavailable.append(_unavailable("work_record", "source_revision_unavailable", relative))
            evidence_revision = baseline
        rows.append((doc, evidence_revision, relative))
    return rows, unavailable


def _validate_handoffs(
    values: Sequence[AuthorizedWorkHandoff],
) -> dict[str, AuthorizedWorkHandoff]:
    result: dict[str, AuthorizedWorkHandoff] = {}
    for value in values:
        if value.work_id in result:
            raise WorkspaceError(f"duplicate authorized handoff: {value.work_id}")
        if value.evidence_revision is not None and not _REVISION.fullmatch(
            value.evidence_revision
        ):
            raise WorkspaceError(
                f"invalid authorized handoff revision: {value.work_id}"
            )
        if not value.completion_evidence.get("kind"):
            raise WorkspaceError(
                f"authorized handoff lacks completion evidence: {value.work_id}"
            )
        result[value.work_id] = value
    return result


def _validate_owner_evidence_handoffs(
    values: Sequence[OwnerEvidenceHandoff],
) -> dict[str, OwnerEvidenceHandoff]:
    result: dict[str, OwnerEvidenceHandoff] = {}
    for value in values:
        if value.version != _CONTRACT_VERSION:
            raise WorkspaceError(f"unsupported owner evidence version: {value.work_id}")
        if value.work_id in result:
            raise WorkspaceError(f"duplicate owner evidence handoff: {value.work_id}")
        if not value.work_id or not value.owning_feature or not value.authorized_source:
            raise WorkspaceError(f"incomplete owner evidence handoff: {value.work_id}")
        if value.availability == "available":
            if value.record_revision is None or not _REVISION.fullmatch(
                value.record_revision
            ):
                raise WorkspaceError(
                    f"available owner evidence lacks exact revision: {value.work_id}"
                )
            if not all((
                value.intent_excerpt,
                value.intent_source_reference,
                value.verification_excerpt,
                value.verification_source_reference,
            )):
                raise WorkspaceError(
                    f"available owner evidence lacks referenced excerpts: {value.work_id}"
                )
            if value.unavailable_reason is not None:
                raise WorkspaceError(
                    f"available owner evidence has unavailable reason: {value.work_id}"
                )
        elif value.availability in {"unavailable", "pending_owner_handoff"}:
            if value.record_revision is not None:
                raise WorkspaceError(
                    f"non-available owner evidence has a revision: {value.work_id}"
                )
            if not value.unavailable_reason or not value.responsible_owner:
                raise WorkspaceError(
                    f"non-available owner evidence lacks reason or owner: {value.work_id}"
                )
            if any((
                value.intent_excerpt,
                value.intent_source_reference,
                value.verification_excerpt,
                value.verification_source_reference,
            )):
                raise WorkspaceError(
                    f"non-available owner evidence contains excerpts: {value.work_id}"
                )
            if value.availability == "pending_owner_handoff":
                if not value.owner_request_id:
                    raise WorkspaceError(
                        f"pending owner evidence lacks request id: {value.work_id}"
                    )
                if value.source_repository is not None or value.source_path is not None:
                    raise WorkspaceError(
                        f"pending owner evidence contains unreceived source: {value.work_id}"
                    )
        else:
            raise WorkspaceError(f"invalid owner evidence availability: {value.work_id}")
        result[value.work_id] = value
    return result


def _expected_repository_key(project: ProjectContext, role: str) -> str:
    if role == "target" or project.target.root == project.tracking.root:
        return project.target_repository_key
    assert project.tracking.repository_key is not None
    return project.tracking.repository_key


def _validate_baseline_pair_shape(pair: BaselinePair) -> None:
    string_values = (
        pair.target_repository_key,
        pair.tracking_repository_key,
        pair.g_artifact_repository_key,
        pair.g_artifact_path,
        pair.g_artifact_sha256,
    )
    if pair.version != _CONTRACT_VERSION or not all(
        isinstance(value, str) and value.strip() for value in string_values
    ):
        raise ValueError
    if pair.g_artifact_repository_role not in {"target", "tracking"}:
        raise ValueError
    if not all(_REVISION.fullmatch(revision) for revision in (
        pair.target_revision,
        pair.tracking_revision,
        pair.g_artifact_revision,
    )):
        raise ValueError
    if not re.fullmatch(r"[0-9a-f]{64}", pair.g_artifact_sha256):
        raise ValueError
    artifact_path = Path(pair.g_artifact_path)
    if artifact_path.is_absolute() or ".." in artifact_path.parts:
        raise ValueError
    if not all(isinstance(row, dict) for row in (
        *pair.integrations, *pair.accepted_deltas,
    )):
        raise ValueError


def _validate_baseline_pair(project: ProjectContext, pair: BaselinePair) -> None:
    try:
        _validate_baseline_pair_shape(pair)
    except ValueError as exc:
        raise WorkspaceError("invalid historical baseline pair") from exc
    if pair.target_repository_key != _expected_repository_key(project, "target"):
        raise WorkspaceError("baseline target repository mismatch")
    if pair.tracking_repository_key != _expected_repository_key(project, "tracking"):
        raise WorkspaceError("baseline tracking repository mismatch")
    artifact_root = (
        project.target.root
        if pair.g_artifact_repository_role == "target"
        else project.tracking.root
    )
    if pair.g_artifact_repository_key != _expected_repository_key(
        project, pair.g_artifact_repository_role
    ):
        raise WorkspaceError("G artifact repository mismatch")
    target = _resolve_revision(project.target.root, pair.target_revision)
    tracking = _resolve_revision(project.tracking.root, pair.tracking_revision)
    if target != pair.target_revision or tracking != pair.tracking_revision:
        raise WorkspaceError("baseline pair revisions are not exact commits")
    artifact_revision = _resolve_revision(artifact_root, pair.g_artifact_revision)
    artifact = _git_bytes(
        artifact_root, ["show", f"{artifact_revision}:{pair.g_artifact_path}"]
    )
    if hashlib.sha256(artifact).hexdigest() != pair.g_artifact_sha256:
        raise WorkspaceError("G artifact content hash mismatch")
    for integration in pair.integrations:
        _validate_integration_evidence(project.target.root, target, integration)
    for delta in pair.accepted_deltas:
        revision = delta.get("revision")
        if not isinstance(revision, str) or not _REVISION.fullmatch(revision):
            raise WorkspaceError("accepted delta lacks exact revision")
        if not _is_ancestor(project.target.root, revision, target):
            raise WorkspaceError(f"accepted delta is unreachable: {revision}")
    if pair.integrations:
        last_merge = pair.integrations[-1].get("merge_revision")
        assert isinstance(last_merge, str)
        expected_deltas = _git_lines(project.target.root, [
            "rev-list", "--first-parent", "--reverse",
            f"{last_merge}..{target}",
        ])
        recorded_deltas = [str(row["revision"]) for row in pair.accepted_deltas]
        if recorded_deltas != expected_deltas:
            raise WorkspaceError("accepted delta cut does not match accepted target")


def _validate_integration_evidence(
    root: Path, accepted_revision: str, integration: Mapping[str, object]
) -> None:
    merge = integration.get("merge_revision")
    head = integration.get("head_revision")
    base = integration.get("base_revision")
    if not all(
        isinstance(value, str) and _REVISION.fullmatch(value)
        for value in (merge, head, base)
    ):
        raise WorkspaceError("integration evidence lacks exact merge/head/base revisions")
    assert isinstance(merge, str) and isinstance(head, str) and isinstance(base, str)
    if not _is_ancestor(root, merge, accepted_revision):
        raise WorkspaceError(f"integration merge is not accepted: {merge}")
    parents = _git_lines(root, ["show", "-s", "--format=%P", merge])
    parent_ids = parents[0].split() if parents else []
    if parent_ids[:2] != [base, head]:
        raise WorkspaceError(f"integration linkage mismatch: {merge}")


def _validate_review_evidence(
    value: ReviewEvidence,
    *,
    expected_repository_key: str,
    root: Path,
    accepted_revision: str,
) -> None:
    if value.version != _CONTRACT_VERSION:
        raise WorkspaceError(f"unsupported review evidence version: {value.review_id}")
    if value.repository_key != expected_repository_key:
        raise WorkspaceError(f"review repository mismatch: {value.review_id}")
    if not all((value.review_id, value.forge, value.url, value.captured_at)):
        raise WorkspaceError("review evidence lacks identity or capture time")
    try:
        captured_at = datetime.fromisoformat(value.captured_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise WorkspaceError("review evidence has invalid capture time") from exc
    if captured_at.tzinfo is None:
        raise WorkspaceError("review evidence capture time lacks timezone")
    if not value.work_ids:
        raise WorkspaceError("review evidence lacks linked work")
    unavailable = dict(value.unavailable_fields)
    revision_fields = {
        "source_revision": value.source_revision,
        "head_revision": value.head_revision,
        "base_revision": value.base_revision,
        "merge_revision": value.merge_revision,
    }
    for field_name, revision in revision_fields.items():
        if revision is None:
            if not unavailable.get(field_name):
                raise WorkspaceError(
                    f"review evidence lacks explicit unavailable field: {field_name}"
                )
        elif not _REVISION.fullmatch(revision):
            raise WorkspaceError(f"invalid review revision: {field_name}")
    for field_name in ("source_revision", "head_revision", "base_revision"):
        revision = revision_fields[field_name]
        if revision is not None and not _is_ancestor(root, revision, accepted_revision):
            raise WorkspaceError(
                f"review revision is unreachable: {field_name}:{revision}"
            )
    if value.description is None:
        if value.description_sha256 is not None or not unavailable.get("description"):
            raise WorkspaceError("unavailable review description is not explicit")
        if value.description_provenance != "unavailable":
            raise WorkspaceError("unavailable review description has provenance")
    else:
        digest = hashlib.sha256(value.description.encode("utf-8")).hexdigest()
        if digest != value.description_sha256:
            raise WorkspaceError("review description content hash mismatch")
        if value.description_provenance not in {
            "current_snapshot", "merge_time_archive",
        }:
            raise WorkspaceError("invalid review description provenance")
    for revision in value.linked_commit_ids:
        if not _REVISION.fullmatch(revision) or not _is_ancestor(
            root, revision, accepted_revision
        ):
            raise WorkspaceError(f"review linked commit is unreachable: {revision}")
    if not value.linked_commit_ids and not unavailable.get("linked_commit_ids"):
        raise WorkspaceError("review evidence lacks linked commits or unavailable reason")
    if value.merge_revision is not None:
        if not _is_ancestor(root, value.merge_revision, accepted_revision):
            raise WorkspaceError(
                f"review merge is unreachable: {value.merge_revision}"
            )
        parents = _git_lines(
            root, ["show", "-s", "--format=%P", value.merge_revision]
        )
        parent_ids = parents[0].split() if parents else []
        head = value.head_revision or value.source_revision
        if head is not None and (
            len(parent_ids) < 2
            or parent_ids[1] != head
            or (
                value.base_revision is not None
                and parent_ids[0] != value.base_revision
            )
        ):
            raise WorkspaceError(
                f"review head/merge linkage mismatch: {value.review_id}"
            )
        if value.base_revision is not None and not _is_ancestor(
            root, value.base_revision, value.merge_revision
        ):
            raise WorkspaceError(
                f"review base/merge linkage mismatch: {value.review_id}"
            )


def _receipt_commit_map(
    root: Path, baseline: str, work_ids: set[str]
) -> tuple[dict[str, set[str]], list[dict[str, str]]]:
    state = _json_at_revision(root, baseline, "architecture/reconciliation-receipts.json")
    if state is None:
        return {}, [_unavailable("git", "reconciliation_receipt_store_missing")]
    receipts = state.get("receipts") if isinstance(state, dict) else None
    if not isinstance(receipts, dict):
        return {}, [_unavailable("git", "reconciliation_receipts_unreadable")]
    result: dict[str, set[str]] = {}
    unavailable: list[dict[str, str]] = []
    for work_id, rows in receipts.items():
        if work_id not in work_ids or not isinstance(rows, list):
            continue
        for row in rows:
            revisions = row.get("implementation_revisions") if isinstance(row, dict) else None
            if not isinstance(revisions, list):
                unavailable.append(_unavailable("git", "reconciliation_receipts_unreadable", work_id))
                continue
            for revision in revisions:
                if isinstance(revision, str) and _REVISION.fullmatch(revision):
                    result.setdefault(revision, set()).add(work_id)
                else:
                    unavailable.append(_unavailable("git", "ambiguous_receipt_revision", work_id))
    return result, unavailable


def _review_inventory(
    project: ProjectContext, baseline: str, work_ids: set[str]
) -> tuple[list[dict[str, object]], dict[str, tuple[str, ...]], list[dict[str, str]]]:
    state = _json_at_revision(project.target.root, baseline, ".cascade/reviews.json")
    runtime_state = False
    if state is None:
        # Review tracking is runtime state in older workspaces.  It may still be
        # consumed at the agreed HEAD because the resulting inventory captures
        # the exact rows; record that no Git revision authenticates the registry.
        if baseline == _resolve_revision(project.target.root, "HEAD"):
            try:
                state = json.loads(
                    (project.target.root / ".cascade" / "reviews.json").read_text(
                        encoding="utf-8"
                    )
                )
                runtime_state = True
            except (OSError, json.JSONDecodeError):
                pass
        if state is None:
            return [], {}, [_unavailable("review", "review_registry_unavailable")]
    if not isinstance(state, dict):
        return [], {}, [_unavailable("review", "review_registry_unreadable")]
    by_identity: dict[str, dict[str, object]] = {}
    by_work: dict[str, list[str]] = {}
    unavailable: list[dict[str, str]] = []
    if runtime_state:
        unavailable.append(
            _unavailable("review", "review_registry_revision_unavailable")
        )
    for work_id in sorted(work_ids):
        record = state.get(work_id)
        if not isinstance(record, dict):
            unavailable.append(_unavailable("review", "linked_review_missing", work_id))
            continue
        url = str(record.get("url") or record.get("review_url") or "").strip()
        if not url:
            unavailable.append(_unavailable("review", "linked_review_missing", work_id))
            continue
        identity = url
        description = record.get("description") or record.get("body")
        description = description if isinstance(description, str) and description.strip() else None
        source_revision = record.get("source_revision")
        source_revision = source_revision.strip() if isinstance(source_revision, str) else ""
        if description is None or not source_revision:
            remote = _authorized_review_evidence(
                project.target.root,
                record,
                url=url,
                source_branch=record.get("source_branch"),
            )
            if description is None and isinstance(remote.get("description"), str):
                description = remote["description"]
            if not source_revision and isinstance(remote.get("source_revision"), str):
                source_revision = remote["source_revision"]
        row = by_identity.setdefault(identity, {
            "review_id": str(record.get("number") or url),
            "url": url,
            "forge": record.get("forge"),
            "description": description,
            "description_status": "lead_pending_current_code_check" if description else "unavailable",
            "source_revision": source_revision or None,
            "merge_revision": record.get("merge_revision") or record.get("merge_sha"),
            "work_ids": [],
        })
        cast_work_ids = row["work_ids"]
        assert isinstance(cast_work_ids, list)
        cast_work_ids.append(work_id)
        by_work.setdefault(work_id, []).append(str(row["review_id"]))
        if description is None:
            unavailable.append(_unavailable("review", "review_description_unavailable", url))
        if not source_revision:
            unavailable.append(_unavailable("review", "review_source_revision_unavailable", url))
    reviews = sorted(by_identity.values(), key=lambda row: str(row["url"]))
    return reviews, {key: tuple(value) for key, value in by_work.items()}, unavailable


def _merge_authorized_reviews(
    reviews: list[dict[str, object]],
    review_by_work: dict[str, tuple[str, ...]],
    handoffs: Sequence[AuthorizedReviewHandoff],
    work_ids: set[str],
) -> list[dict[str, str]]:
    """Merge bounded review leads without treating an open review as accepted."""

    by_url = {str(row["url"]): row for row in reviews}
    unavailable: list[dict[str, str]] = []
    for handoff in handoffs:
        if not handoff.url or not handoff.review_id:
            raise WorkspaceError("authorized review handoff lacks identity")
        if handoff.source_revision is not None and not _REVISION.fullmatch(
            handoff.source_revision
        ):
            raise WorkspaceError(
                f"invalid authorized review source revision: {handoff.url}"
            )
        if handoff.merge_revision is not None and not _REVISION.fullmatch(
            handoff.merge_revision
        ):
            raise WorkspaceError(
                f"invalid authorized review merge revision: {handoff.url}"
            )
        if (
            handoff.status_evidence_revision is not None
            and not _REVISION.fullmatch(handoff.status_evidence_revision)
        ):
            raise WorkspaceError(
                f"invalid authorized review status revision: {handoff.url}"
            )
        unknown = set(handoff.work_ids) - work_ids
        if unknown:
            raise WorkspaceError(
                "authorized review references unknown work: "
                + ",".join(sorted(unknown))
            )
        row = by_url.get(handoff.url)
        if row is None:
            row = {
                "review_id": handoff.review_id,
                "url": handoff.url,
                "forge": handoff.forge,
                "description": handoff.description,
                "description_status": (
                    "lead_pending_current_code_check"
                    if handoff.description else "unavailable"
                ),
                "source_revision": handoff.source_revision,
                "merge_revision": handoff.merge_revision,
                "acceptance_status": handoff.acceptance_status,
                "status_evidence_revision": handoff.status_evidence_revision,
                "work_ids": list(handoff.work_ids),
            }
            reviews.append(row)
            by_url[handoff.url] = row
        else:
            linked = row["work_ids"]
            assert isinstance(linked, list)
            linked.extend(
                work_id for work_id in handoff.work_ids if work_id not in linked
            )
            row.setdefault("acceptance_status", handoff.acceptance_status)
        for work_id in handoff.work_ids:
            review_by_work[work_id] = tuple(dict.fromkeys((
                *review_by_work.get(work_id, ()), handoff.review_id,
            )))
        if row.get("description") is None:
            unavailable.append(_unavailable(
                "review", "review_description_unavailable", handoff.url
            ))
        if row.get("source_revision") is None:
            unavailable.append(_unavailable(
                "review", "review_source_revision_unavailable", handoff.url
            ))
    reviews.sort(key=lambda row: str(row["url"]))
    return unavailable


def _merge_review_evidence(
    reviews: list[dict[str, object]],
    review_by_work: dict[str, tuple[str, ...]],
    values: Sequence[ReviewEvidence],
    work_ids: set[str],
    *,
    project: ProjectContext,
    accepted_target_revision: str,
) -> list[dict[str, str]]:
    """Merge exact forge captures and reject repository or commit mismatches."""

    by_url = {str(row["url"]): row for row in reviews}
    seen: set[str] = set()
    unavailable: list[dict[str, str]] = []
    for value in values:
        if value.url in seen:
            raise WorkspaceError(f"duplicate review evidence: {value.url}")
        seen.add(value.url)
        unknown = set(value.work_ids) - work_ids
        if unknown:
            raise WorkspaceError(
                "review evidence references unknown work: "
                + ",".join(sorted(unknown))
            )
        _validate_review_evidence(
            value,
            expected_repository_key=_expected_repository_key(project, "target"),
            root=project.target.root,
            accepted_revision=accepted_target_revision,
        )
        row = value.to_dict()
        row.update({
            "description_status": (
                "captured_current_description"
                if value.description_provenance == "current_snapshot"
                else "captured_merge_time_description"
                if value.description_provenance == "merge_time_archive"
                else "unavailable"
            ),
            "acceptance_status": (
                "merged_reachable_from_accepted_target"
                if value.merge_revision is not None else "not_proven_merged"
            ),
        })
        existing = by_url.get(value.url)
        if existing is None:
            reviews.append(row)
            by_url[value.url] = row
        else:
            existing.clear()
            existing.update(row)
        for work_id in value.work_ids:
            review_by_work[work_id] = tuple(dict.fromkeys((
                *review_by_work.get(work_id, ()), value.review_id,
            )))
        for field_name, reason in sorted(value.unavailable_fields.items()):
            unavailable.append(_unavailable(
                "review", f"review_{field_name}_unavailable", f"{value.url}:{reason}"
            ))
    reviews.sort(key=lambda row: str(row["url"]))
    return unavailable


def _merge_commit_reviews(
    root: Path,
    commits: list[dict[str, object]],
    known_urls: set[str],
) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Resolve review descriptions only from exact links in merge narratives."""

    from cascade.board.errors import GitError
    from cascade.tracking import (
        MergeRequest,
        detect_forge,
        merge_request_snapshot,
        remote_repo_web_base,
        remote_url,
    )

    forge = detect_forge(root)
    origin = remote_url(root)
    base = remote_repo_web_base(origin, forge=forge) if origin and forge else None
    if forge is None or base is None:
        return [], []
    patterns = (
        re.compile(r"Merge pull request #(\d+)"),
        re.compile(r"See merge request [^\s!]+!(\d+)"),
    )
    rows: list[dict[str, object]] = []
    unavailable: list[dict[str, str]] = []
    for commit in commits:
        if len(commit["parents"]) < 2:
            continue
        narrative = str(commit["subject"]) + "\n" + str(commit["body"])
        number = next(
            (match.group(1) for pattern in patterns if (match := pattern.search(narrative))),
            None,
        )
        if number is None:
            continue
        url = (
            f"{base}/pull/{number}" if forge == "github"
            else f"{base}/-/merge_requests/{number}"
        )
        if url in known_urls:
            continue
        review = MergeRequest(
            url=url, number=number, forge=forge,
            source_branch="", target_branch="", draft=False,
        )
        try:
            snapshot = merge_request_snapshot(root, review)
        except (GitError, OSError, ValueError):
            snapshot = {}
        description = snapshot.get("description")
        source_revision = snapshot.get("source_revision")
        row = {
            "review_id": number,
            "url": url,
            "forge": forge,
            "description": description if isinstance(description, str) else None,
            "description_status": (
                "lead_pending_current_code_check"
                if isinstance(description, str) and description.strip()
                else "unavailable"
            ),
            "source_revision": (
                source_revision if isinstance(source_revision, str) else None
            ),
            "merge_revision": commit["commit_id"],
            "work_ids": [],
        }
        rows.append(row)
        cast_review_ids = commit["review_ids"]
        assert isinstance(cast_review_ids, list)
        cast_review_ids.append(number)
        if row["description"] is None:
            unavailable.append(
                _unavailable("review", "review_description_unavailable", url)
            )
        if row["source_revision"] is None:
            unavailable.append(
                _unavailable("review", "review_source_revision_unavailable", url)
            )
    return rows, unavailable


def _reachable_commits(
    root: Path,
    baseline: str,
    receipt_map: dict[str, set[str]],
    reviews: list[dict[str, object]],
) -> list[dict[str, object]]:
    revisions = _git_lines(root, ["rev-list", "--reverse", "--topo-order", baseline])
    review_by_revision: dict[str, list[str]] = {}
    for review in reviews:
        for revision_field in ("source_revision", "merge_revision"):
            value = review.get(revision_field)
            if isinstance(value, str) and _REVISION.fullmatch(value):
                review_by_revision.setdefault(value, []).append(str(review["review_id"]))
    rows: list[dict[str, object]] = []
    for revision in revisions:
        raw = _git_text(
            root,
            ["show", "-s", "--format=%P%n%aI%n%s%n%b", revision],
        ).splitlines()
        parents = raw[0].split() if raw else []
        authored_at = raw[1] if len(raw) > 1 else ""
        subject = raw[2] if len(raw) > 2 else ""
        body = "\n".join(raw[3:]).strip()
        mentioned = sorted(set(_WORK_ID.findall(subject + "\n" + body)))
        receipt_owners = sorted(receipt_map.get(revision, ()))
        provenance = "reconciliation_receipt" if receipt_owners else (
            "merge_commit" if len(parents) > 1 else "direct_or_rebased_commit"
        )
        rows.append({
            "commit_id": revision,
            "parents": parents,
            "authored_at": authored_at,
            "subject": subject,
            "body": body,
            "narrative_status": "lead_pending_current_code_check",
            "provenance": provenance,
            "receipt_work_ids": receipt_owners,
            "mentioned_work_ids": mentioned,
            "provenance_status": (
                "durable" if receipt_owners else
                "ambiguous" if mentioned else "unattributed"
            ),
            "review_ids": list(dict.fromkeys(review_by_revision.get(revision, ()))),
        })
    return rows


def _initial_ledger_row(
    row_id: str,
    kind: str,
    work_id: str | None,
    evidence_revisions: list[str],
    review_ids: list[str],
) -> dict[str, object]:
    return {
        "row_id": row_id,
        "kind": kind,
        "work_id": work_id,
        "evidence_revisions": list(dict.fromkeys(evidence_revisions)),
        "review_ids": list(dict.fromkeys(review_ids)),
        "requirement_ids": [],
        "decision_ids": [],
        "outcome": "unresolved",
        "current_code_check": "pending",
    }


def _json_at_revision(root: Path, revision: str, relative: str) -> object | None:
    result = subprocess.run(
        ["git", "show", f"{revision}:{relative}"], cwd=root,
        capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return False


def _resolve_revision(root: Path, revision: str) -> str:
    value = _git_text(
        root, ["rev-parse", "--verify", "--end-of-options", f"{revision}^{{commit}}"]
    ).strip()
    if not _REVISION.fullmatch(value):
        raise WorkspaceError(f"cannot resolve inventory baseline {revision}")
    return value


def _git_lines(root: Path, args: list[str]) -> list[str]:
    return [line for line in _git_text(root, args).splitlines() if line]


def _git_text(root: Path, args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def _git_bytes(root: Path, args: list[str]) -> bytes:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True)
    if result.returncode != 0:
        raise GitError(
            result.stderr.decode("utf-8", errors="replace").strip()
            or f"git {' '.join(args)} failed"
        )
    return result.stdout


def _is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        capture_output=True,
    ).returncode == 0


__all__ = [
    "BaselinePair",
    "OwnerEvidenceHandoff",
    "ReviewEvidence",
    "AuthorizedReviewHandoff",
    "AuthorizedWorkHandoff",
    "HistoricalEvidenceInventory",
    "build_historical_inventory",
    "inventory_path",
    "pin_historical_inventory",
    "read_historical_inventory",
]
