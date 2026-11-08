"""Typed, read-only health observations for Task, Feature, and Epic work.

This module is deliberately separate from :mod:`cascade.watchdog.health`.
The latter is a periodic reconciliation sweep; the functions here only read
canonical board and lifecycle projections and are safe to use for auditing.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Mapping, TypeAlias

from cascade.board.context import (
    get_project_context,
    resolve_root,
    resolve_tracking_root,
)
from cascade.board.gitutil import _run, head_sha
from cascade.board.store import read_doc
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
