"""Typed, read-only health observations for Task, Feature, and Epic work.

This module is deliberately separate from :mod:`cascade.watchdog.health`.
The latter is a periodic reconciliation sweep; the functions here only read
canonical board and lifecycle projections and are safe to use for auditing.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import time
from collections import OrderedDict
from dataclasses import dataclass, replace
from datetime import date, timedelta
from pathlib import Path
from threading import RLock
from typing import Any, Callable, Literal, Mapping, TypeAlias

from cascade.board.context import (
    get_project_context,
    resolve_root,
    resolve_tracking_root,
)
from cascade.board.gitutil import _run, head_sha
from cascade.board.errors import SchemaError
from cascade.board.store import _scan_meta, read_doc
from cascade.board.types import BoardIndex, WorkDoc, WorkMeta, WorkTier
from cascade.board.work_ids import parse_work_id_parts
from cascade.epic.plan_readiness import compute_epic_plan_readiness
from cascade.feature.readiness import compute_feature_readiness
from cascade.task.action_recovery import recovery_actions
from cascade.task.execution import execution_views
from cascade.watchdog.health import classify_child
from cascade.watchdog.incidents import capability_authority_fingerprint
from cascade.workspace.integration_worktree import merged_board_readonly

AuditClassification = Literal[
    "healthy", "expected_wait", "proven_incident", "unavailable_evidence"
]


class AuditIdentityError(ValueError):
    """Raised when fields from different audit identity domains are mixed."""


@dataclass(frozen=True, slots=True)
class _WorkId:
    value: str
    _tier: WorkTier

    def __post_init__(self) -> None:
        if type(self.value) is not str:  # reject another typed scalar
            raise AuditIdentityError("work ID must be an untyped string")
        try:
            actual = parse_work_id_parts(self.value).tier
        except Exception as exc:
            raise AuditIdentityError(f"invalid work ID: {self.value!r}") from exc
        if actual != self._tier:
            raise AuditIdentityError(
                f"{self.value!r} is a {actual} ID, not a {self._tier} ID"
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, init=False)
class TaskId(_WorkId):
    def __init__(self, value: str) -> None:
        _WorkId.__init__(self, value, "task")


@dataclass(frozen=True, slots=True, init=False)
class FeatureId(_WorkId):
    def __init__(self, value: str) -> None:
        _WorkId.__init__(self, value, "feature")


@dataclass(frozen=True, slots=True, init=False)
class EpicId(_WorkId):
    def __init__(self, value: str) -> None:
        _WorkId.__init__(self, value, "epic")


@dataclass(frozen=True, slots=True)
class DocumentRevision:
    value: str

    def __post_init__(self) -> None:
        _validate_hex_identity(self.value, "document revision")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class GitHead:
    value: str

    def __post_init__(self) -> None:
        _validate_hex_identity(self.value, "Git head")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class BranchName:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not self.value or self.value.startswith("-"):
            raise AuditIdentityError("branch must be a nonempty Git branch name")
        if any(char.isspace() for char in self.value) or ".." in self.value:
            raise AuditIdentityError("branch must be a valid single-line Git ref")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class AuditGeneration:
    value: str

    def __post_init__(self) -> None:
        if type(self.value) is not str or not self.value.startswith("sha256:"):
            raise AuditIdentityError("generation must be a sha256 identity")
        digest = self.value.removeprefix("sha256:")
        if len(digest) != 64 or any(char not in "0123456789abcdef" for char in digest):
            raise AuditIdentityError(
                "generation must contain a full lowercase sha256 digest"
            )

    def __str__(self) -> str:
        return self.value


def _validate_hex_identity(value: object, field: str) -> None:
    if type(value) is not str:
        raise AuditIdentityError(f"{field} must be an untyped string")
    if len(value) != 40 or any(char not in "0123456789abcdef" for char in value):
        raise AuditIdentityError(f"{field} must be a full lowercase Git object ID")


@dataclass(frozen=True, slots=True)
class AuditEvidence:
    tracking_repository: Path
    product_repository: Path
    status: str
    parent_id: str | None
    child_ids: tuple[str, ...]
    dependency_ids: tuple[str, ...]
    owners: tuple[str, ...]
    execution: Mapping[str, Any] | None
    gates: tuple[str, ...]
    unresolved_references: tuple[str, ...]
    errors: tuple[str, ...] = ()
    local_fingerprint: str | None = None


@dataclass(frozen=True, slots=True)
class _AuditIdentity:
    document_revision: DocumentRevision | None
    git_head: GitHead | None
    branch: BranchName | None
    generation: AuditGeneration

    def __post_init__(self) -> None:
        _require_optional_exact(
            self.document_revision, DocumentRevision, "document_revision"
        )
        _require_optional_exact(self.git_head, GitHead, "git_head")
        _require_optional_exact(self.branch, BranchName, "branch")
        _require_exact(self.generation, AuditGeneration, "generation")


@dataclass(frozen=True, slots=True)
class TaskAuditIdentity(_AuditIdentity):
    work_id: TaskId
    tier: Literal["task"] = "task"

    def __post_init__(self) -> None:
        super(TaskAuditIdentity, self).__post_init__()
        _require_exact(self.work_id, TaskId, "work_id")
        if self.tier != "task":
            raise AuditIdentityError("Task identity tier must be 'task'")


@dataclass(frozen=True, slots=True)
class FeatureAuditIdentity(_AuditIdentity):
    work_id: FeatureId
    tier: Literal["feature"] = "feature"

    def __post_init__(self) -> None:
        super(FeatureAuditIdentity, self).__post_init__()
        _require_exact(self.work_id, FeatureId, "work_id")
        if self.tier != "feature":
            raise AuditIdentityError("Feature identity tier must be 'feature'")


@dataclass(frozen=True, slots=True)
class EpicAuditIdentity(_AuditIdentity):
    work_id: EpicId
    tier: Literal["epic"] = "epic"

    def __post_init__(self) -> None:
        super(EpicAuditIdentity, self).__post_init__()
        _require_exact(self.work_id, EpicId, "work_id")
        if self.tier != "epic":
            raise AuditIdentityError("Epic identity tier must be 'epic'")


AuditIdentity: TypeAlias = TaskAuditIdentity | FeatureAuditIdentity | EpicAuditIdentity
AuditWorkId: TypeAlias = TaskId | FeatureId | EpicId


@dataclass(frozen=True, slots=True)
class CandidateBudget:
    """Hard bounds for one inventory pass.

    The coordinator's limits are part of the contract rather than trusted
    caller input.  Smaller limits are useful for tests and incremental work.
    """

    max_items: int = 100
    max_seconds: float = 60.0

    def __post_init__(self) -> None:
        if type(self.max_items) is not int or not 1 <= self.max_items <= 100:
            raise ValueError("candidate budget must contain 1 to 100 items")
        if (
            not isinstance(self.max_seconds, (int, float))
            or not 0 < self.max_seconds <= 60
        ):
            raise ValueError("candidate budget must contain at most 60 seconds")


@dataclass(frozen=True, slots=True)
class AuditCandidate:
    """One coalesced typed work reference selected for observation."""

    work_id: AuditWorkId
    tier: WorkTier
    reasons: tuple[str, ...]
    tracking_repository: Path
    product_repository: Path
    registered_worktree: Path | None = None
    evidence_available: bool = True
    evidence_errors: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CandidatePage:
    candidates: tuple[AuditCandidate, ...]
    next_cursor: str
    unavailable_evidence: tuple[str, ...] = ()


_CANDIDATE_CURSOR_VERSION = 1
_CANDIDATE_TIERS: tuple[WorkTier, ...] = ("task", "feature", "epic")
_UNRESOLVED_SOURCES = (
    ("action", "executions.json"),
    ("review", "reviews.json"),
    ("reconciliation", "resolution_actions.json"),
    ("cleanup", "orphan_delivery_recoveries.json"),
)
_TERMINAL_MARKERS = {
    "completed",
    "succeeded",
    "success",
    "merged",
    "closed",
    "repaired",
    "requeue_commit",
}
# A workspace can retain dozens of owned checkouts. Keep their inventories in
# the bounded cache together instead of evicting every checkout each pass.
_COMPLETED_CACHE_LIMIT = 128
_completed_cache_lock = RLock()
_completed_cache: OrderedDict[
    Path,
    tuple[
        tuple[tuple[int, int, int, int] | None, ...],
        dict[str, WorkMeta],
        date,
        dict[str, WorkMeta],
    ],
] = OrderedDict()


def _candidate_board(
    tracking: Path, cutoff: date
) -> tuple[dict[str, WorkMeta], dict[str, WorkMeta], dict[str, WorkMeta]]:
    """Read live metadata and reuse completed metadata until a directory changes.

    Canonical board writes replace files, which changes the containing directory.
    A new process scans completed directories once; unchanged passes do not
    inspect every completed document again.
    """

    directories = tuple(
        tracking / "docs" / dirname / "3_completed"
        for dirname in ("tasks", "features", "epics")
    )

    def signature(path: Path) -> tuple[int, int, int, int] | None:
        if not path.is_dir():
            return None
        stat = path.stat()
        return stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_ctime_ns

    stamps = tuple(signature(path) for path in directories)
    with _completed_cache_lock:
        cached = _completed_cache.get(tracking)
        if cached is not None and cached[0] == stamps:
            _completed_cache.move_to_end(tracking)
            completed = cached[1]
            recent = (
                cached[3]
                if cached[2] == cutoff
                else {
                    work_id: meta
                    for work_id, meta in completed.items()
                    if meta.status == "completed" and meta.updated >= cutoff
                }
            )
        else:
            completed = {}
            for directory in directories:
                _scan_candidate_directory(directory, completed)
            recent = {
                work_id: meta
                for work_id, meta in completed.items()
                if meta.status == "completed" and meta.updated >= cutoff
            }
            # A concurrent canonical write may have changed a directory while
            # it was scanned. Return this read, but do not cache it.
        if stamps == tuple(signature(path) for path in directories):
            _completed_cache[tracking] = (stamps, completed, cutoff, recent)
            _completed_cache.move_to_end(tracking)
            while len(_completed_cache) > _COMPLETED_CACHE_LIMIT:
                _completed_cache.popitem(last=False)

    live: dict[str, WorkMeta] = {}
    for dirname in ("tasks", "features", "epics"):
        for column in ("1_backlog", "2_active"):
            _scan_candidate_directory(tracking / "docs" / dirname / column, live)
    if live.keys() & completed.keys():
        duplicate = next(iter(live.keys() & completed.keys()))
        raise SchemaError(f"duplicate id {duplicate} in live and completed board")
    return live, completed, recent


def _scan_candidate_directory(directory: Path, output: dict[str, WorkMeta]) -> None:
    if not directory.is_dir():
        return
    for path in sorted(directory.glob("*.md")):
        if path.is_symlink() or not path.is_file():
            continue
        try:
            meta = _scan_meta(path)
        except (SchemaError, OSError, UnicodeDecodeError):
            continue
        if meta.id in output:
            raise SchemaError(
                f"duplicate id {meta.id} at {path} and {output[meta.id].path}"
            )
        output[meta.id] = meta


def _canonical_candidate_board(
    tracking: Path, cutoff: date
) -> tuple[dict[str, WorkMeta], dict[str, WorkMeta], dict[str, WorkMeta]]:
    """Apply canonical checkout precedence while caching completed inventories.

    Only tracking checkouts own lifecycle documents in a split workspace.
    Product worktrees supply Git provenance separately, never stale plan copies.
    """
    from cascade.workspace.integration_worktree import (
        _meta_preference, is_trunk_pointer, load_registry_readonly,
    )
    from cascade.workspace.backlog_snapshot import read_provenance, snapshot_board

    live, completed, _recent = _candidate_board(tracking, cutoff)
    by_id = {**completed, **live}
    closed_epics = {
        work_id for work_id, meta in completed.items()
        if meta.tier == "epic" and meta.status == "completed"
        and not is_trunk_pointer(meta)
    }
    seen = {tracking.resolve()}
    for entry in load_registry_readonly(tracking):
        checkout = entry.path.resolve()
        if checkout in seen or not checkout.is_dir():
            continue
        seen.add(checkout)
        child_live, child_completed, _ = _candidate_board(checkout, cutoff)
        for work_id, meta in {**child_completed, **child_live}.items():
            current = by_id.get(work_id)
            if work_id not in closed_epics and (
                current is None or _meta_preference(meta) > _meta_preference(current)
            ):
                by_id[work_id] = meta
    if read_provenance(tracking) is not None:
        for work_id, meta in snapshot_board(tracking).by_id.items():
            if meta.tier != "epic":
                continue
            current = by_id.get(work_id)
            if current is None or (
                current.status == "backlog" and current.path.parent.name == "1_backlog"
            ):
                if meta.path.parent.name == "1_backlog" or meta.status == "cancelled":
                    by_id[work_id] = meta
    completed = {
        work_id: meta for work_id, meta in by_id.items()
        if meta.path.parent.name == "3_completed"
    }
    live = {work_id: meta for work_id, meta in by_id.items() if work_id not in completed}
    recent = {
        work_id: meta for work_id, meta in completed.items()
        if meta.status == "completed" and meta.updated >= cutoff
    }
    return live, completed, recent


def select_audit_candidates(
    cursor: str | None = None,
    budget: CandidateBudget | None = None,
    *,
    root: Path | None = None,
    today: date | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> CandidatePage:
    """Return a bounded, fair, mutation-free page of canonical work refs.

    Cursor positions are independent per tier.  Selection rotates tiers and
    wraps each typed keyspace, so newly eligible lower IDs and older unresolved
    completed work are eventually admitted without a completed-document read.
    The caller owns persistence of the returned opaque cursor.
    """

    limit = budget or CandidateBudget()
    started = monotonic()
    product, tracking = _canonical_repositories(root)
    # ``merged_board`` acquires the product registry's file lock.  Candidate
    # selection needs lifecycle truth from tracking and reads product-worktree
    # provenance separately, so avoid even that incidental lock-file write.
    positions, next_tier = _decode_candidate_cursor(cursor)
    cutoff = (today or date.today()) - timedelta(days=7)
    live, completed, recent = _canonical_candidate_board(tracking, cutoff)
    reasons: dict[tuple[WorkTier, str], set[str]] = {}
    errors: dict[tuple[WorkTier, str], set[str]] = {}

    for meta in live.values():
        key = (meta.tier, meta.id)
        if meta.status not in {"completed", "cancelled"}:
            reasons.setdefault(key, set()).add("nonterminal")
    for meta in recent.values():
        key = (meta.tier, meta.id)
        reasons.setdefault(key, set()).add("recently_completed")

    unresolved, unavailable = _unresolved_candidate_references(product)
    for source, work_id in unresolved:
        try:
            typed_id, tier = _typed_work_id(work_id)
        except AuditIdentityError:
            unavailable.append(f"{source}:invalid_work_id:{work_id}")
            continue
        key = (tier, str(typed_id))
        reasons.setdefault(key, set()).add(f"unresolved_{source}")
        meta = live.get(str(typed_id)) or completed.get(str(typed_id))
        if meta is None or meta.tier != tier:
            errors.setdefault(key, set()).add("canonical_document_unavailable")

    worktrees, worktree_errors = _registered_worktrees(product)
    unavailable.extend(worktree_errors)
    for key, path in worktrees.items():
        if not path.is_dir():
            errors.setdefault(key, set()).add("registered_worktree_unavailable")
            unavailable.append(f"worktree:{key[1]}:unavailable")
        meta = live.get(key[1]) or completed.get(key[1])
        if meta is None or meta.tier != key[0]:
            reasons.setdefault(key, set()).add("unresolved_cleanup")
            errors.setdefault(key, set()).add("canonical_document_unavailable")
        elif meta.status in {"completed", "cancelled"}:
            reasons.setdefault(key, set()).add("unresolved_cleanup")
    lanes: dict[WorkTier, list[str]] = {
        tier: sorted(
            work_id for candidate_tier, work_id in reasons if candidate_tier == tier
        )
        for tier in _CANDIDATE_TIERS
    }
    selected: list[AuditCandidate] = []
    selected_keys: set[tuple[WorkTier, str]] = set()
    tier_index = next_tier
    empty_turns = 0
    while len(selected) < limit.max_items and empty_turns < len(_CANDIDATE_TIERS):
        if monotonic() - started >= limit.max_seconds:
            break
        tier = _CANDIDATE_TIERS[tier_index]
        tier_index = (tier_index + 1) % len(_CANDIDATE_TIERS)
        work_id = _next_candidate_id(lanes[tier], positions[tier], selected_keys, tier)
        if work_id is None:
            empty_turns += 1
            continue
        empty_turns = 0
        positions[tier] = work_id
        key = (tier, work_id)
        selected_keys.add(key)
        typed_id, _ = _typed_work_id(work_id)
        candidate_errors = tuple(sorted(errors.get(key, ())))
        selected.append(
            AuditCandidate(
                work_id=typed_id,
                tier=tier,
                reasons=tuple(sorted(reasons[key])),
                tracking_repository=tracking,
                product_repository=product,
                registered_worktree=worktrees.get(key),
                evidence_available=not candidate_errors,
                evidence_errors=candidate_errors,
            )
        )
    return CandidatePage(
        candidates=tuple(selected),
        next_cursor=_encode_candidate_cursor(positions, tier_index),
        unavailable_evidence=tuple(sorted(set(unavailable))),
    )


def select_candidates(
    cursor: str | None = None,
    budget: CandidateBudget | None = None,
    *,
    root: Path | None = None,
    today: date | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> tuple[tuple[AuditCandidate, ...], str]:
    """Feature-contract spelling returning ``(work_refs, next_cursor)``."""

    page = select_audit_candidates(
        cursor, budget, root=root, today=today, monotonic=monotonic
    )
    return page.candidates, page.next_cursor


def _typed_work_id(value: str) -> tuple[AuditWorkId, WorkTier]:
    try:
        tier = parse_work_id_parts(value).tier
    except Exception as exc:
        raise AuditIdentityError(f"invalid work ID: {value!r}") from exc
    if tier == "task":
        return TaskId(value), tier
    if tier == "feature":
        return FeatureId(value), tier
    return EpicId(value), tier


def _next_candidate_id(
    lane: list[str],
    after: str | None,
    selected: set[tuple[WorkTier, str]],
    tier: WorkTier,
) -> str | None:
    if not lane:
        return None
    ordered = [item for item in lane if after is None or item > after]
    ordered.extend(item for item in lane if after is not None and item <= after)
    return next((item for item in ordered if (tier, item) not in selected), None)


def _encode_candidate_cursor(
    positions: Mapping[WorkTier, str | None], next_tier: int
) -> str:
    payload = {
        "v": _CANDIDATE_CURSOR_VERSION,
        "after": {tier: positions[tier] for tier in _CANDIDATE_TIERS},
        "next_tier": next_tier,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_candidate_cursor(
    cursor: str | None,
) -> tuple[dict[WorkTier, str | None], int]:
    empty: dict[WorkTier, str | None] = {tier: None for tier in _CANDIDATE_TIERS}
    if cursor is None:
        return empty, 0
    if not isinstance(cursor, str) or not cursor:
        raise ValueError("candidate cursor must be a nonempty opaque string")
    if len(cursor) > 4096:
        raise ValueError("invalid candidate continuation cursor")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
        after = payload["after"]
        next_tier = payload["next_tier"]
        if payload["v"] != _CANDIDATE_CURSOR_VERSION:
            raise ValueError
        if type(next_tier) is not int or not 0 <= next_tier < len(_CANDIDATE_TIERS):
            raise ValueError
        positions = {
            tier: after[tier]
            if after[tier] is None or isinstance(after[tier], str)
            else (_raise_invalid_cursor())
            for tier in _CANDIDATE_TIERS
        }
    except (
        KeyError,
        TypeError,
        ValueError,
        UnicodeDecodeError,
        binascii.Error,
        json.JSONDecodeError,
    ) as exc:
        raise ValueError("invalid candidate continuation cursor") from exc
    return positions, next_tier


def _raise_invalid_cursor() -> None:
    raise ValueError("invalid cursor position")


def _read_json_source(path: Path, label: str) -> tuple[Any | None, str | None]:
    if not path.exists():
        return None, None
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None, f"{label}:unavailable"


def _unresolved_candidate_references(
    product: Path,
    sources: tuple[tuple[str, str], ...] = _UNRESOLVED_SOURCES,
    *,
    include_auditor_receipts: bool = True,
) -> tuple[list[tuple[str, str]], list[str]]:
    references: list[tuple[str, str]] = []
    unavailable: list[str] = []
    for label, filename in sources:
        from cascade.task.lifecycle_lock import lifecycle_root

        store_root = lifecycle_root(product) if label in {"action", "cleanup"} else product
        payload, error = _read_json_source(store_root / ".cascade" / filename, label)
        if error:
            unavailable.append(error)
            continue
        if payload is None:
            continue
        if not isinstance(payload, Mapping):
            unavailable.append(f"{label}:unavailable")
            continue
        _collect_unresolved_references(
            payload, label, references, include_auditor_receipts=include_auditor_receipts
        )
        if label == "reconciliation":
            reviews, review_error = _read_json_source(
                product / ".cascade" / "reviews.json", "review"
            )
            if review_error or (
                reviews is not None and not isinstance(reviews, Mapping)
            ):
                unavailable.append("reconciliation:unavailable")
            elif reviews is None:
                if _has_unresolved_resolution_review_identity(payload):
                    unavailable.append("reconciliation:unavailable")
            elif isinstance(reviews, Mapping):
                if not _collect_resolution_review_references(
                    payload, reviews, references
                ):
                    unavailable.append("reconciliation:unavailable")
    return references, unavailable


def _has_unresolved_resolution_review_identity(value: Any) -> bool:
    """Return whether a live resolution row requires the review registry."""

    if isinstance(value, list):
        return any(_has_unresolved_resolution_review_identity(item) for item in value)
    if not isinstance(value, Mapping) or _reference_is_terminal(value):
        return False
    request = value.get("request")
    if isinstance(request, Mapping) and any(
        str(request.get(field) or "").strip()
        for field in ("review_id", "review_url")
    ):
        return True
    if _is_resolution_action_row(value):
        return True
    return any(
        _has_unresolved_resolution_review_identity(item)
        for item in value.values()
        if isinstance(item, (Mapping, list))
    )


def _collect_resolution_review_references(
    value: Any,
    reviews: Mapping[str, Any],
    references: list[tuple[str, str]],
) -> bool:
    """Attribute real resolution-action rows through their review registry owner."""

    if isinstance(value, list):
        results = tuple(
            _collect_resolution_review_references(item, reviews, references)
            for item in value
        )
        return all(results)
    if not isinstance(value, Mapping) or _reference_is_terminal(value):
        return True
    valid = True
    request = value.get("request")
    if isinstance(request, Mapping):
        review_id = str(request.get("review_id") or "").strip()
        review_url = str(request.get("review_url") or "").strip()
        id_matches: set[str] = set()
        url_matches: set[str] = set()
        for owner_id, record in reviews.items():
            if not isinstance(owner_id, str) or not isinstance(record, Mapping):
                continue
            number = str(record.get("number") or record.get("review_id") or "").strip()
            url = str(record.get("url") or record.get("review_url") or "").strip()
            if review_id and review_id == number:
                id_matches.add(owner_id)
            if review_url and review_url == url:
                url_matches.add(owner_id)
        identity_matches = [
            matches
            for identity, matches in (
                (review_id, id_matches),
                (review_url, url_matches),
            )
            if identity
        ]
        owners = {
            next(iter(matches))
            for matches in identity_matches
            if len(matches) == 1
        }
        owner_id = (
            next(iter(owners))
            if identity_matches
            and all(len(matches) == 1 for matches in identity_matches)
            and len(owners) == 1
            else None
        )
        if owner_id is not None and _looks_like_work_id(owner_id):
            references.append(("reconciliation", owner_id))
        else:
            valid = False
    elif _is_resolution_action_row(value):
        valid = False
    for item in value.values():
        if isinstance(item, (Mapping, list)):
            valid = (
                _collect_resolution_review_references(item, reviews, references)
                and valid
            )
    return valid


def _is_resolution_action_row(value: Mapping[str, Any]) -> bool:
    """Distinguish a persisted action from its surrounding registry wrappers."""

    return any(value.get(field) is not None for field in ("action_id", "idempotency_key"))


def _reference_is_terminal(value: Mapping[str, Any]) -> bool:
    states = {
        str(value.get(field)).lower()
        for field in (
            "status",
            "state",
            "stage",
            "outcome",
            "recovery_state",
            "result",
            "decision",
        )
        if value.get(field) is not None
    }
    return (bool(states) and states.issubset(_TERMINAL_MARKERS)) or value.get(
        "closed"
    ) is True


def _collect_unresolved_references(
    value: Any,
    source: str,
    references: list[tuple[str, str]],
    *,
    inherited_id: str | None = None,
    include_auditor_receipts: bool = True,
) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_unresolved_references(
                item, source, references, include_auditor_receipts=include_auditor_receipts
            )
        return
    if not isinstance(value, Mapping):
        return
    if not include_auditor_receipts and _auditor_receipt(value):
        return
    if _reference_is_terminal(value):
        return
    identity_fields = {
        "work_id",
        "affected_work_id",
        "task_id",
        "feature_id",
        "epic_id",
        "review_owner_id",
    }
    ids = {
        item
        for key, item in value.items()
        if (
            key in identity_fields
            or key.endswith("_work_id")
            or key == "owner_id"
            and isinstance(item, str)
            and _looks_like_work_id(item)
        )
        and isinstance(item, str)
    }
    if inherited_id is not None:
        ids.add(inherited_id)
    references.extend((source, item) for item in ids)
    for key, item in value.items():
        child_id = None
        if isinstance(key, str):
            if _looks_like_work_id(key):
                child_id = key
            else:
                prefix = key.partition(":")[0]
                child_id = prefix if _looks_like_work_id(prefix) else None
        if isinstance(item, (Mapping, list)):
            _collect_unresolved_references(
                item, source, references, inherited_id=child_id,
                include_auditor_receipts=include_auditor_receipts,
            )


def _auditor_receipt(row: Mapping[str, Any]) -> bool:
    """Audit bookkeeping is not a new authoritative lifecycle failure."""
    return row.get("action_kind") in {
        "health_auditor_capability_probe", "health_auditor_reservation"
    } or bool(row.get("reservation_id") and row.get("durable_store"))


def _looks_like_work_id(value: str) -> bool:
    try:
        parse_work_id_parts(value)
    except Exception:
        return False
    return True


def _registered_worktrees(
    product: Path,
) -> tuple[dict[tuple[WorkTier, str], Path], list[str]]:
    payload, error = _read_json_source(
        product / ".cascade" / "worktrees.json", "worktree_registry"
    )
    if error:
        return {}, [error]
    if payload is None:
        return {}, []
    entries = payload.get("entries") if isinstance(payload, Mapping) else None
    if not isinstance(entries, list):
        return {}, ["worktree_registry:unavailable"]
    result: dict[tuple[WorkTier, str], Path] = {}
    unavailable: list[str] = []
    for row in entries:
        if not isinstance(row, Mapping):
            unavailable.append("worktree_registry:invalid_entry")
            continue
        work_id, tier, raw_path = row.get("work_id"), row.get("kind"), row.get("path")
        if (
            not isinstance(work_id, str)
            or tier not in _CANDIDATE_TIERS
            or not isinstance(raw_path, str)
        ):
            unavailable.append("worktree_registry:invalid_entry")
            continue
        try:
            _, actual_tier = _typed_work_id(work_id)
        except AuditIdentityError:
            unavailable.append(f"worktree_registry:invalid_work_id:{work_id}")
            continue
        if actual_tier != tier:
            unavailable.append(f"worktree_registry:tier_mismatch:{work_id}")
            continue
        path = Path(raw_path)
        result[(actual_tier, work_id)] = (
            path.resolve() if path.is_absolute() else (product / path).resolve()
        )
    return result, unavailable


@dataclass(frozen=True, slots=True)
class AuditIncidentIdentity:
    identity: AuditIdentity
    failure_class: str
    evidence: AuditEvidence

    def __post_init__(self) -> None:
        if type(self.identity) not in {
            TaskAuditIdentity,
            FeatureAuditIdentity,
            EpicAuditIdentity,
        }:
            raise AuditIdentityError("incident identity must be a typed audit identity")
        if type(self.failure_class) is not str or not self.failure_class:
            raise AuditIdentityError("incident failure_class is required")
        _require_exact(self.evidence, AuditEvidence, "evidence")

    @property
    def work_id(self) -> TaskId | FeatureId | EpicId:
        return self.identity.work_id

    @property
    def tier(self) -> WorkTier:
        return self.identity.tier

    @property
    def document_revision(self) -> DocumentRevision | None:
        return self.identity.document_revision

    @property
    def git_head(self) -> GitHead | None:
        return self.identity.git_head

    @property
    def branch(self) -> BranchName | None:
        return self.identity.branch

    @property
    def generation(self) -> AuditGeneration:
        return self.identity.generation


@dataclass(frozen=True, slots=True)
class AuditObservation:
    identity: AuditIdentity
    classification: AuditClassification
    reason: str
    evidence: AuditEvidence
    incident: AuditIncidentIdentity | None = None

    def __post_init__(self) -> None:
        if self.classification not in {
            "healthy",
            "expected_wait",
            "proven_incident",
            "unavailable_evidence",
        }:
            raise AuditIdentityError("unknown audit classification")
        _require_exact(self.evidence, AuditEvidence, "evidence")
        if self.classification == "proven_incident":
            _require_exact(self.incident, AuditIncidentIdentity, "incident")
        elif self.incident is not None:
            raise AuditIdentityError(
                "only a proven incident may carry incident identity"
            )

    @property
    def work_id(self) -> TaskId | FeatureId | EpicId:
        return self.identity.work_id

    @property
    def tier(self) -> WorkTier:
        return self.identity.tier

    @property
    def document_revision(self) -> DocumentRevision | None:
        return self.identity.document_revision

    @property
    def git_head(self) -> GitHead | None:
        return self.identity.git_head

    @property
    def branch(self) -> BranchName | None:
        return self.identity.branch

    @property
    def generation(self) -> AuditGeneration:
        return self.identity.generation


def _require_exact(value: object, expected: type, field: str) -> None:
    if type(value) is not expected:
        raise AuditIdentityError(f"{field} must be {expected.__name__}")


def _require_optional_exact(value: object, expected: type, field: str) -> None:
    if value is not None:
        _require_exact(value, expected, field)


def project_audit_observation(
    work_id: str, *, root: Path | None = None
) -> AuditObservation:
    """Project one canonical work item without invoking any mutation path."""

    product, tracking = _canonical_repositories(root)
    board = merged_board_readonly(tracking)
    doc = read_doc(work_id, root=tracking)
    return _project_doc(doc, board=board, product=product, tracking=tracking)


def project_audit_observations(
    *, root: Path | None = None
) -> tuple[AuditObservation, ...]:
    """Project the canonical board in stable tier/ID order, without writes."""

    product, tracking = _canonical_repositories(root)
    board = merged_board_readonly(tracking)
    order = {"epic": 0, "feature": 1, "task": 2}
    docs = (
        read_doc(meta.id, root=tracking)
        for meta in sorted(
            board.by_id.values(), key=lambda row: (order[row.tier], row.id)
        )
    )
    return tuple(
        _project_doc(doc, board=board, product=product, tracking=tracking)
        for doc in docs
    )


def _canonical_repositories(root: Path | None) -> tuple[Path, Path]:
    requested = resolve_root(root)
    project = get_project_context()
    if project is not None and (
        requested in {project.target.root.resolve(), project.tracking.root.resolve()}
        or requested.is_relative_to(
            project.target.root.resolve() / ".cascade" / "worktrees"
        )
    ):
        product = project.target.root.resolve()
    else:
        product = requested
    return product, resolve_tracking_root(product)


def _project_doc(
    doc: WorkDoc, *, board: BoardIndex, product: Path, tracking: Path
) -> AuditObservation:
    local_error = None
    try:
        local_fingerprint = local_audit_fingerprint(doc.meta.id, root=product)
    except Exception as exc:
        local_fingerprint = None
        local_error = f"local_evidence:{type(exc).__name__}"
    worktrees, worktree_errors = _registered_worktrees(product)
    worktree = worktrees.get((doc.meta.tier, doc.meta.id))
    git_root = worktree if worktree is not None else product
    git_head = head_sha(git_root) if git_root.is_dir() else None
    branch = _branch(git_root) if git_root.is_dir() else None
    execution: Mapping[str, Any] | None = None
    gates: list[str] = []
    errors: list[str] = list(worktree_errors)
    if worktree is not None and not worktree.is_dir():
        errors.append("registered_worktree_unavailable")
    if doc.sha is None:
        errors.append("document_revision_unavailable")
    if git_head is None:
        errors.append("git_head_unavailable")
    if branch is None:
        errors.append("branch_unavailable")

    if doc.meta.tier == "task":
        execution = execution_views({doc.meta.id}, root=product).get(doc.meta.id)
    gates.extend(_dependency_gates(doc, board))
    review_gate, review_error = _review_gate(doc.meta.id, product)
    if review_gate is not None:
        gates.append(review_gate)
    if review_error is not None:
        errors.append(review_error)
    if doc.meta.tier == "feature":
        try:
            readiness = compute_feature_readiness(
                doc.meta.id, root=tracking, board=board
            )
            if readiness is not None:
                gates.extend(readiness.blockers)
            if doc.meta.status not in {"backlog", "ready_to_plan"}:
                from cascade.comments.gate import refusal_if_blocked

                if refusal_if_blocked(doc.meta.id, root=tracking, board=board):
                    gates.append("review_threads_blocking")
        except Exception as exc:
            errors.append(f"feature_readiness:{type(exc).__name__}")
    elif doc.meta.tier == "epic" and doc.meta.plan_approved_at is None:
        gates.append("plan_approval")
        if doc.meta.status == "active":
            try:
                readiness = compute_epic_plan_readiness(
                    doc.meta.id, root=tracking, board=board
                )
                if readiness is not None:
                    gates.extend(blocker.code for blocker in readiness.blockers)
            except Exception as exc:
                errors.append(f"epic_readiness:{type(exc).__name__}")

    unresolved, recovery_error = _unresolved_references(doc.meta.id, product)
    if recovery_error is not None:
        errors.append(recovery_error)
    if local_error is not None:
        errors.append(local_error)
    if worktree is not None and doc.meta.status in {"completed", "cancelled"}:
        unresolved = (*unresolved, f"worktree:{doc.meta.id}")
    evidence = AuditEvidence(
        tracking_repository=tracking,
        product_repository=product,
        status=doc.meta.status,
        parent_id=doc.meta.parent,
        child_ids=tuple(doc.meta.children),
        dependency_ids=tuple(doc.meta.depends_on),
        owners=tuple(doc.meta.owners),
        execution=execution,
        gates=tuple(dict.fromkeys(gates)),
        unresolved_references=unresolved,
        errors=tuple(errors),
        local_fingerprint=local_fingerprint,
    )
    generation = _generation(doc, git_head, branch, evidence, board=board)
    identity = _identity(doc, git_head, branch, generation)
    classification, reason = _classification(doc, board, evidence)
    incident = (
        AuditIncidentIdentity(identity, incident_failure_class(doc.meta.tier, reason, evidence), evidence)
        if classification == "proven_incident"
        else None
    )
    try:
        unchanged = local_fingerprint is not None and local_audit_fingerprint(doc.meta.id, root=product) == local_fingerprint
    except Exception:
        unchanged = False
    if not unchanged and local_error is None:
        return AuditObservation(
            identity, "unavailable_evidence", "local_evidence_changed",
            replace(evidence, errors=(*evidence.errors, "local_evidence_changed")), None,
        )
    return AuditObservation(identity, classification, reason, evidence, incident)


def incident_failure_class(tier: WorkTier, reason: str, evidence: AuditEvidence) -> str:
    """Map observed symptoms to the existing owning recovery contract.

    Keep manual blockage and unknown evidence unclassified: neither authorizes
    a retry. Later adapters may register additional concrete incident classes.
    """
    if tier == "task":
        execution = evidence.execution or {}
        if reason == "blocked" and execution.get("outcome") == "failed":
            return "blocked_task_failed"
        if reason == "stale":
            return "stalled_execution"
        if reason == "merge_blocked":
            return "delivery_reconciliation"
    return reason


def local_audit_fingerprint(work_id: str, *, root: Path) -> str:
    """Fingerprint scoped local authority without subprocess or network I/O.

    Reservation compares this under the lifecycle lock. Include related plan
    content, comments, leases, review and action records, so a gate or child
    change between projection and admission invalidates the prepared evidence.
    Auditor receipts and clock-derived lease age are not authority changes.
    """
    product, tracking = _canonical_repositories(root)
    board = merged_board_readonly(tracking)
    owner = board.by_id[work_id]
    ids = {work_id, *owner.children, *owner.depends_on}
    if owner.parent:
        ids.add(owner.parent)
    ids.update(meta.id for meta in board.by_id.values() if meta.parent == work_id)
    documents = {}
    comments = {}
    for related_id in sorted(ids):
        meta = board.by_id.get(related_id)
        documents[related_id] = (
            (str(meta.path), hashlib.sha256(meta.path.read_bytes()).hexdigest())
            if meta is not None else None
        )
        path = tracking / "docs" / "_comments" / f"{related_id}.jsonl"
        comments[related_id] = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None
    views = execution_views({key for key in ids if key.startswith("task_")}, root=product)
    executions = {
        key: ({name: value for name, value in view.items() if name != "heartbeat_age_seconds"} if view is not None else None)
        for key, view in views.items()
    }
    actions = [
        row for row in recovery_actions(root=product)
        if (row.get("affected_work_id") or ((row.get("recovery") or {}).get("evidence") or {}).get("affected_work_id")) in ids
        and row.get("action_kind") not in {"health_auditor_capability_probe", "health_auditor_reservation"}
        and ":health_" not in str(row.get("action_id", ""))
    ]
    reviews, review_error = _read_json_source(product / ".cascade" / "reviews.json", "review")
    if review_error:
        raise ValueError(review_error)
    worktrees, errors = _registered_worktrees(product)
    payload = {
        "documents": documents, "comments": comments, "executions": executions,
        "actions": sorted(actions, key=lambda row: str(row.get("action_id"))),
        "reviews": {key: reviews.get(key) for key in sorted(ids)} if isinstance(reviews, Mapping) else None,
        "worktrees": [(key, str(path), path.is_dir()) for key, path in sorted(worktrees.items()) if key[1] in ids],
        "registry_errors": errors,
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def _dependency_gates(doc: WorkDoc, board: BoardIndex) -> list[str]:
    return [
        f"dependency:{dependency_id}"
        for dependency_id in doc.meta.depends_on
        if (dependency := board.by_id.get(dependency_id)) is None
        or dependency.status not in {"completed", "cancelled"}
    ]


def _unresolved_references(
    work_id: str, product: Path
) -> tuple[tuple[str, ...], str | None]:
    try:
        actions = recovery_actions(root=product)
    except Exception:
        return (), "action_recovery_unavailable"
    references = {
        str(row.get("action_id"))
        for row in actions
        if row.get("recovery_state") != "completed"
        and not _auditor_receipt(row)
        and (
            row.get("affected_work_id") == work_id
            or ((row.get("recovery") or {}).get("evidence") or {}).get(
                "affected_work_id"
            )
            == work_id
        )
        and row.get("action_id")
    }
    unresolved, errors = _unresolved_candidate_references(
        product, _UNRESOLVED_SOURCES[2:], include_auditor_receipts=False
    )
    references.update(
        f"{source}:{work_id}"
        for source, candidate_id in unresolved
        if candidate_id == work_id and source in {"reconciliation", "cleanup"}
    )
    relevant_error = next(
        (
            error
            for error in errors
            if error.split(":", 1)[0] in {"reconciliation", "cleanup"}
        ),
        None,
    )
    return tuple(sorted(references)), relevant_error


def _review_gate(work_id: str, product: Path) -> tuple[str | None, str | None]:
    """An open review remains a human wait even after its work doc completes."""

    payload, error = _read_json_source(product / ".cascade" / "reviews.json", "review")
    if error is not None:
        return None, error
    if payload is None:
        return None, None
    if not isinstance(payload, Mapping):
        return None, "review:unavailable"
    record = payload.get(work_id)
    if record is None:
        return None, None
    if not isinstance(record, Mapping):
        return None, "review:unavailable"
    return ("review_pending", None) if not record.get("closed") else (None, None)


def _classification(
    doc: WorkDoc, board: BoardIndex, evidence: AuditEvidence
) -> tuple[AuditClassification, str]:
    if evidence.errors:
        return "unavailable_evidence", evidence.errors[0]
    if evidence.unresolved_references:
        return "proven_incident", "unresolved_recovery_reference"
    if "review_pending" in evidence.gates:
        return "expected_wait", "review_pending"
    if doc.meta.status in {"completed", "cancelled"}:
        return "healthy", "terminal"
    if evidence.gates:
        return "expected_wait", evidence.gates[0]
    if doc.meta.status in {"backlog", "ready_to_plan", "cancelling"}:
        return "expected_wait", "lifecycle_gate"
    if doc.meta.status == "blocked":
        return "proven_incident", "blocked"
    if doc.meta.tier == "task":
        execution = evidence.execution
        if execution is None:
            return "unavailable_evidence", "execution_evidence_missing"
        health = execution.get("health")
        outcome = execution.get("outcome")
        if outcome == "failed" or health in {"failed", "stale", "merge_blocked"}:
            return "proven_incident", str(health or "execution_failed")
        if outcome is None:
            return (
                "expected_wait",
                "live_owner" if health in {"healthy", "queued"} else str(health),
            )
        return "healthy", "execution_succeeded"

    for child_id in doc.meta.children:
        child = board.by_id.get(child_id)
        if child is None:
            return "unavailable_evidence", f"child_missing:{child_id}"
        child_doc = read_doc(child_id, root=evidence.tracking_repository)
        child_execution = None
        if child.tier == "task":
            child_execution = execution_views(
                {child_id}, root=evidence.product_repository
            ).get(child_id)
        child_health = classify_child(doc, child_doc, child_execution)
        if child_health.classification in {"remediation_eligible", "unresolved"}:
            return "proven_incident", f"child:{child_id}:{child_health.reason}"
    return "healthy", "authoritative_state_consistent"


def _identity(
    doc: WorkDoc,
    head: str | None,
    branch: str | None,
    generation: AuditGeneration,
) -> AuditIdentity:
    common = {
        "document_revision": (
            DocumentRevision(doc.sha) if doc.sha is not None else None
        ),
        "git_head": GitHead(head) if head is not None else None,
        "branch": BranchName(branch) if branch is not None else None,
        "generation": generation,
    }
    if doc.meta.tier == "task":
        return TaskAuditIdentity(**common, work_id=TaskId(doc.meta.id))
    if doc.meta.tier == "feature":
        return FeatureAuditIdentity(**common, work_id=FeatureId(doc.meta.id))
    return EpicAuditIdentity(**common, work_id=EpicId(doc.meta.id))


def _generation(
    doc: WorkDoc,
    head: str | None,
    branch: str | None,
    evidence: AuditEvidence,
    *,
    board: BoardIndex,
) -> AuditGeneration:
    payload = {
        "work_id": doc.meta.id,
        "tier": doc.meta.tier,
        "document_revision": doc.sha,
        "git_head": head,
        "branch": branch,
        "status": evidence.status,
        "gates": evidence.gates,
        # Elapsed age is derived from the observation clock, not a change to
        # the authoritative lease. Keep the heartbeat timestamp in the hash.
        "execution": (
            {
                key: value
                for key, value in evidence.execution.items()
                if key != "heartbeat_age_seconds"
            }
            if evidence.execution is not None
            else None
        ),
        "unresolved_references": evidence.unresolved_references,
        "errors": evidence.errors,
        "local_fingerprint": evidence.local_fingerprint,
        "capability_fingerprint": capability_authority_fingerprint(),
        "direct_reports": _direct_report_inputs(doc, board, evidence),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return AuditGeneration("sha256:" + hashlib.sha256(encoded.encode()).hexdigest())


def _direct_report_inputs(
    doc: WorkDoc, board: BoardIndex, evidence: AuditEvidence
) -> tuple[Mapping[str, Any], ...]:
    """Include the direct-report facts that can change a supervisor incident."""

    if doc.meta.tier == "task":
        return ()
    task_ids = {
        child_id
        for child_id in doc.meta.children
        if (meta := board.by_id.get(child_id)) is not None and meta.tier == "task"
    }
    task_views = (
        execution_views(task_ids, root=evidence.product_repository) if task_ids else {}
    )
    children = []
    for child_id in doc.meta.children:
        meta = board.by_id.get(child_id)
        if meta is None:
            children.append({"work_id": child_id, "missing": True})
            continue
        child = read_doc(child_id, root=evidence.tracking_repository)
        item: dict[str, Any] = {
            "work_id": child_id,
            "status": child.meta.status,
            "document_revision": child.sha,
        }
        if child.meta.tier == "task":
            view = task_views.get(child_id)
            item["execution"] = (
                {
                    key: value
                    for key, value in view.items()
                    if key != "heartbeat_age_seconds"
                }
                if view is not None
                else None
            )
        children.append(item)
    return tuple(children)


def _branch(root: Path) -> str | None:
    result = _run(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
