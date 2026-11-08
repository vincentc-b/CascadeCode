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
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Literal, Mapping, TypeAlias

from cascade.board.context import (
    get_project_context,
    resolve_root,
    resolve_tracking_root,
)
from cascade.board.gitutil import _run, head_sha
from cascade.board.store import list_board, read_doc
from cascade.board.types import BoardIndex, WorkDoc, WorkTier
from cascade.board.work_ids import parse_work_id_parts
from cascade.epic.plan_readiness import compute_epic_plan_readiness
from cascade.feature.readiness import compute_feature_readiness
from cascade.task.action_recovery import recovery_actions
from cascade.task.execution import execution_views
from cascade.watchdog.health import classify_child
from cascade.workspace.integration_worktree import merged_board

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
            raise AuditIdentityError("generation must contain a full lowercase sha256 digest")

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
        if not isinstance(self.max_seconds, (int, float)) or not 0 < self.max_seconds <= 60:
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
    "merged",
    "closed",
    "repaired",
    "already_delivered",
    "requeue_commit",
    "resume_workspace",
    "no_op_live_owner",
}


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
    board = list_board(tracking)
    positions, next_tier = _decode_candidate_cursor(cursor)
    cutoff = (today or date.today()) - timedelta(days=7)
    reasons: dict[tuple[WorkTier, str], set[str]] = {}
    errors: dict[tuple[WorkTier, str], set[str]] = {}

    for meta in board.by_id.values():
        key = (meta.tier, meta.id)
        if meta.status not in {"completed", "cancelled"}:
            reasons.setdefault(key, set()).add("nonterminal")
        elif meta.status == "completed" and meta.updated >= cutoff:
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
        meta = board.by_id.get(str(typed_id))
        if meta is None or meta.tier != tier:
            errors.setdefault(key, set()).add("canonical_document_unavailable")

    worktrees, worktree_errors = _registered_worktrees(product)
    unavailable.extend(worktree_errors)
    for key, path in worktrees.items():
        if not path.is_dir():
            errors.setdefault(key, set()).add("registered_worktree_unavailable")
            unavailable.append(f"worktree:{key[1]}:unavailable")
        meta = board.by_id.get(key[1])
        if meta is None or meta.tier != key[0]:
            reasons.setdefault(key, set()).add("unresolved_cleanup")
            errors.setdefault(key, set()).add("canonical_document_unavailable")
        elif meta.status in {"completed", "cancelled"}:
            reasons.setdefault(key, set()).add("unresolved_cleanup")
    lanes: dict[WorkTier, list[str]] = {
        tier: sorted(work_id for candidate_tier, work_id in reasons if candidate_tier == tier)
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
        work_id = _next_candidate_id(
            lanes[tier], positions[tier], selected_keys, tier
        )
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
) -> tuple[list[tuple[str, str]], list[str]]:
    references: list[tuple[str, str]] = []
    unavailable: list[str] = []
    for label, filename in _UNRESOLVED_SOURCES:
        payload, error = _read_json_source(product / ".cascade" / filename, label)
        if error:
            unavailable.append(error)
            continue
        if payload is None:
            continue
        if not isinstance(payload, Mapping):
            unavailable.append(f"{label}:unavailable")
            continue
        _collect_unresolved_references(payload, label, references)
    return references, unavailable


def _collect_unresolved_references(
    value: Any,
    source: str,
    references: list[tuple[str, str]],
    *,
    inherited_id: str | None = None,
) -> None:
    if isinstance(value, list):
        for item in value:
            _collect_unresolved_references(item, source, references)
        return
    if not isinstance(value, Mapping):
        return
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
    terminal = bool(states) and states.issubset(_TERMINAL_MARKERS)
    if value.get("closed") is True:
        terminal = True
    if terminal:
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
            or key == "owner_id" and isinstance(item, str) and _looks_like_work_id(item)
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
                item, source, references, inherited_id=child_id
            )


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
            "healthy", "expected_wait", "proven_incident", "unavailable_evidence"
        }:
            raise AuditIdentityError("unknown audit classification")
        _require_exact(self.evidence, AuditEvidence, "evidence")
        if self.classification == "proven_incident":
            _require_exact(self.incident, AuditIncidentIdentity, "incident")
        elif self.incident is not None:
            raise AuditIdentityError("only a proven incident may carry incident identity")

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
    board = merged_board(tracking)
    doc = read_doc(work_id, root=tracking)
    return _project_doc(doc, board=board, product=product, tracking=tracking)


def project_audit_observations(
    *, root: Path | None = None
) -> tuple[AuditObservation, ...]:
    """Project the canonical board in stable tier/ID order, without writes."""

    product, tracking = _canonical_repositories(root)
    board = merged_board(tracking)
    order = {"epic": 0, "feature": 1, "task": 2}
    docs = (
        read_doc(meta.id, root=tracking)
        for meta in sorted(board.by_id.values(), key=lambda row: (order[row.tier], row.id))
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
    git_head = head_sha(product)
    branch = _branch(product)
    execution: Mapping[str, Any] | None = None
    gates: list[str] = []
    errors: list[str] = []
    if doc.sha is None:
        errors.append("document_revision_unavailable")
    if git_head is None:
        errors.append("git_head_unavailable")
    if branch is None:
        errors.append("branch_unavailable")

    if doc.meta.tier == "task":
        execution = execution_views({doc.meta.id}, root=product).get(doc.meta.id)
    gates.extend(_dependency_gates(doc, board))
    if doc.meta.tier == "feature":
        try:
            readiness = compute_feature_readiness(doc.meta.id, root=tracking, board=board)
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
    )
    generation = _generation(doc, git_head, branch, evidence)
    identity = _identity(doc, git_head, branch, generation)
    classification, reason = _classification(doc, board, evidence)
    incident = (
        AuditIncidentIdentity(identity, reason, evidence)
        if classification == "proven_incident"
        else None
    )
    return AuditObservation(identity, classification, reason, evidence, incident)


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
    return (
        tuple(
            sorted(
                str(row.get("action_id"))
                for row in actions
                if row.get("recovery_state") != "completed"
                and (
                    row.get("affected_work_id") == work_id
                    or ((row.get("recovery") or {}).get("evidence") or {}).get(
                        "affected_work_id"
                    )
                    == work_id
                )
                and row.get("action_id")
            )
        ),
        None,
    )


def _classification(
    doc: WorkDoc, board: BoardIndex, evidence: AuditEvidence
) -> tuple[AuditClassification, str]:
    if evidence.errors:
        return "unavailable_evidence", evidence.errors[0]
    if doc.meta.status in {"completed", "cancelled"}:
        return "healthy", "terminal"
    if evidence.gates:
        return "expected_wait", evidence.gates[0]
    if doc.meta.status in {"backlog", "ready_to_plan", "cancelling"}:
        return "expected_wait", "lifecycle_gate"
    if evidence.unresolved_references:
        return "proven_incident", "unresolved_recovery_reference"
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
    doc: WorkDoc, head: str | None, branch: str | None, evidence: AuditEvidence
) -> AuditGeneration:
    payload = {
        "work_id": doc.meta.id,
        "tier": doc.meta.tier,
        "document_revision": doc.sha,
        "git_head": head,
        "branch": branch,
        "status": evidence.status,
        "gates": evidence.gates,
        "execution": evidence.execution,
        "unresolved_references": evidence.unresolved_references,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return AuditGeneration("sha256:" + hashlib.sha256(encoded.encode()).hexdigest())


def _branch(root: Path) -> str | None:
    result = _run(["symbolic-ref", "--quiet", "--short", "HEAD"], root, check=False)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None
