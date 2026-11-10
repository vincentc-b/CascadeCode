"""Revision-pinned inventory for historical architecture reconstruction.

The inventory is deliberately evidence, not a design generator.  Commit messages,
work narratives, and review descriptions are retained as leads until a later pass
checks them against the pinned code and tests.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
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

_SCHEMA_VERSION = 1
_WORK_PATH = re.compile(r"^docs/(epics|features|tasks)/3_completed/[^/]+\.md$")
_WORK_ID = re.compile(r"\b(?:epic|feat|task)_\d+(?:_\d+){0,2}\b")
_REVISION = re.compile(r"^[0-9a-f]{40}$")
InventoryOutcome = Literal["unresolved"]


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
    version: int = _SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
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
        }

    @classmethod
    def from_dict(cls, value: object) -> "HistoricalEvidenceInventory":
        try:
            if not isinstance(value, dict) or value.get("version") != _SCHEMA_VERSION:
                raise ValueError
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
) -> HistoricalEvidenceInventory:
    """Snapshot all eligible work and reachable target history at exact commits.

    The caller supplies the agreed baselines.  Both are canonicalized to commit
    IDs before any evidence is read, so branch movement during a scan cannot
    silently change its contents.
    """

    target = _resolve_revision(project.target.root, target_revision)
    tracking = _resolve_revision(project.tracking.root, tracking_revision)
    handoffs = _validate_handoffs(authorized_work_handoffs)
    # A handoff is also an access boundary: do not open a board document whose
    # owner supplied a deliberately bounded record (for example a parent
    # closeout that cannot disclose its child task content).
    work_docs, unavailable = _completed_work(
        project.tracking.root, tracking, excluded_work_ids=set(handoffs)
    )
    work_ids = {doc.meta.id for doc, _, _ in work_docs} | set(handoffs)

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
    )


def pin_historical_inventory(
    project: ProjectContext,
    owner_work_id: str,
    *,
    target_revision: str = "HEAD",
    tracking_revision: str = "HEAD",
    authorized_work_handoffs: Sequence[AuthorizedWorkHandoff] = (),
    authorized_review_handoffs: Sequence[AuthorizedReviewHandoff] = (),
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
        for field in ("source_revision", "merge_revision"):
            value = review.get(field)
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


__all__ = [
    "AuthorizedReviewHandoff",
    "AuthorizedWorkHandoff",
    "HistoricalEvidenceInventory",
    "build_historical_inventory",
    "inventory_path",
    "pin_historical_inventory",
    "read_historical_inventory",
]
