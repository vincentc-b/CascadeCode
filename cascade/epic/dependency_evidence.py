"""Append-only dependency check evidence and immutable readiness snapshots.

The recorder is deliberately execution-agnostic.  Slice B owns command execution and
calls the trusted completion boundary with the environment it actually observed.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Mapping, Sequence

from cascade.board.gitutil import commit_paths, has_git
from cascade.board.lock import process_lock
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestError,
    DependencyManifestSnapshot,
    EnvironmentIdentity,
    environment_identities_match,
    manifest_path,
    require_dependency_manifest,
)
from cascade.workspace.integration_worktree import locate_trunk

_EVIDENCE_DIR = Path("docs") / "epics" / "2_active" / "_dependency_evidence"
_SCHEMA_VERSION = 1
class DependencyEvidenceError(ValueError):
    """Base error for invalid evidence operations or persisted evidence."""


class CheckAttemptNotFound(DependencyEvidenceError):
    """The named admitted attempt does not exist."""


class CheckAttemptAlreadyCompleted(DependencyEvidenceError):
    """An append-only attempt already has its single completion."""


class DependencyReadinessError(DependencyEvidenceError):
    """Current dependency evidence cannot be snapshotted."""


class CheckOperationKind(StrEnum):
    READ_ONLY = "read_only"
    INSTALL = "install"
    UPGRADE = "upgrade"
    IMPLICIT_PULL = "implicit_pull"


class CheckResult(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class CheckAdmission:
    attempt_id: str
    dependency_id: str
    manifest_revision: int
    entry_revision: str
    recipe_revision: str
    exact_operation: str
    operation_kind: CheckOperationKind
    target_environment_fingerprint: str
    admitted_at: datetime
    selected_version: str
    integrity_reference: str
    lock_references: tuple[str, ...]
    approval_reference: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "admitted",
            "attempt_id": self.attempt_id,
            "dependency_id": self.dependency_id,
            "manifest_revision": self.manifest_revision,
            "entry_revision": self.entry_revision,
            "recipe_revision": self.recipe_revision,
            "exact_operation": self.exact_operation,
            "operation_kind": self.operation_kind.value,
            "target_environment_fingerprint": self.target_environment_fingerprint,
            "admitted_at": _timestamp(self.admitted_at),
            "selected_version": self.selected_version,
            "integrity_reference": self.integrity_reference,
            "lock_references": list(self.lock_references),
            "approval_reference": self.approval_reference,
        }

    @classmethod
    def from_dict(cls, raw: object) -> CheckAdmission:
        data = _mapping(raw, "admission")
        _keys(
            data,
            {
                "type",
                "attempt_id",
                "dependency_id",
                "manifest_revision",
                "entry_revision",
                "recipe_revision",
                "exact_operation",
                "operation_kind",
                "target_environment_fingerprint",
                "admitted_at",
                "selected_version",
                "integrity_reference",
                "lock_references",
                "approval_reference",
            },
            "admission",
        )
        if data.get("type") != "admitted":
            raise DependencyEvidenceError("admission.type must be admitted")
        approval = data.get("approval_reference")
        if approval is not None:
            approval = _text(approval, "admission.approval_reference")
        try:
            kind = CheckOperationKind(data.get("operation_kind"))
        except (ValueError, TypeError) as exc:
            raise DependencyEvidenceError(
                "admission.operation_kind is invalid"
            ) from exc
        refs = data.get("lock_references")
        if not isinstance(refs, list):
            raise DependencyEvidenceError("admission.lock_references must be a list")
        admission = cls(
            attempt_id=_text(data.get("attempt_id"), "admission.attempt_id"),
            dependency_id=_text(data.get("dependency_id"), "admission.dependency_id"),
            manifest_revision=_positive_int(
                data.get("manifest_revision"), "admission.manifest_revision"
            ),
            entry_revision=_fingerprint(
                data.get("entry_revision"), "admission.entry_revision"
            ),
            recipe_revision=_fingerprint(
                data.get("recipe_revision"), "admission.recipe_revision"
            ),
            exact_operation=_text(
                data.get("exact_operation"), "admission.exact_operation"
            ),
            operation_kind=kind,
            target_environment_fingerprint=_fingerprint(
                data.get("target_environment_fingerprint"),
                "admission.target_environment_fingerprint",
            ),
            admitted_at=_datetime(data.get("admitted_at"), "admission.admitted_at"),
            selected_version=_text(
                data.get("selected_version"), "admission.selected_version"
            ),
            integrity_reference=_text(
                data.get("integrity_reference"), "admission.integrity_reference"
            ),
            lock_references=tuple(
                _text(ref, "admission.lock_reference") for ref in refs
            ),
            approval_reference=approval,
        )
        _validate_approval_reference(kind, approval)
        return admission


@dataclass(frozen=True, slots=True)
class CheckCompletion:
    attempt_id: str
    dependency_id: str
    manifest_revision: int
    entry_revision: str
    recipe_revision: str
    exact_operation: str
    operation_kind: CheckOperationKind
    actual_environment: EnvironmentIdentity
    actual_environment_fingerprint: str
    admitted_at: datetime
    completed_at: datetime
    result: CheckResult
    redacted_output: str
    selected_version: str
    integrity_reference: str
    lock_references: tuple[str, ...]
    approval_reference: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "type": "completed",
            "attempt_id": self.attempt_id,
            "dependency_id": self.dependency_id,
            "manifest_revision": self.manifest_revision,
            "entry_revision": self.entry_revision,
            "recipe_revision": self.recipe_revision,
            "exact_operation": self.exact_operation,
            "operation_kind": self.operation_kind.value,
            "actual_environment": self.actual_environment.to_dict(),
            "actual_environment_fingerprint": self.actual_environment_fingerprint,
            "admitted_at": _timestamp(self.admitted_at),
            "completed_at": _timestamp(self.completed_at),
            "result": self.result.value,
            "redacted_output": self.redacted_output,
            "selected_version": self.selected_version,
            "integrity_reference": self.integrity_reference,
            "lock_references": list(self.lock_references),
            "approval_reference": self.approval_reference,
        }

    @classmethod
    def from_dict(cls, raw: object) -> CheckCompletion:
        data = _mapping(raw, "completion")
        _keys(
            data,
            {
                "type",
                "attempt_id",
                "dependency_id",
                "manifest_revision",
                "entry_revision",
                "recipe_revision",
                "exact_operation",
                "operation_kind",
                "actual_environment",
                "actual_environment_fingerprint",
                "admitted_at",
                "completed_at",
                "result",
                "redacted_output",
                "selected_version",
                "integrity_reference",
                "lock_references",
                "approval_reference",
            },
            "completion",
        )
        if data.get("type") != "completed":
            raise DependencyEvidenceError("completion.type must be completed")
        try:
            kind = CheckOperationKind(data.get("operation_kind"))
            result = CheckResult(data.get("result"))
        except (ValueError, TypeError) as exc:
            raise DependencyEvidenceError("completion enum value is invalid") from exc
        approval = data.get("approval_reference")
        if approval is not None:
            approval = _text(approval, "completion.approval_reference")
        refs = data.get("lock_references")
        if not isinstance(refs, list):
            raise DependencyEvidenceError("completion.lock_references must be a list")
        actual = EnvironmentIdentity.from_dict(
            data.get("actual_environment"), field="completion.actual_environment"
        )
        completion = cls(
            attempt_id=_text(data.get("attempt_id"), "completion.attempt_id"),
            dependency_id=_text(data.get("dependency_id"), "completion.dependency_id"),
            manifest_revision=_positive_int(
                data.get("manifest_revision"), "completion.manifest_revision"
            ),
            entry_revision=_fingerprint(
                data.get("entry_revision"), "completion.entry_revision"
            ),
            recipe_revision=_fingerprint(
                data.get("recipe_revision"), "completion.recipe_revision"
            ),
            exact_operation=_text(
                data.get("exact_operation"), "completion.exact_operation"
            ),
            operation_kind=kind,
            actual_environment=actual,
            actual_environment_fingerprint=_fingerprint(
                data.get("actual_environment_fingerprint"),
                "completion.actual_environment_fingerprint",
            ),
            admitted_at=_datetime(data.get("admitted_at"), "completion.admitted_at"),
            completed_at=_datetime(data.get("completed_at"), "completion.completed_at"),
            result=result,
            redacted_output=_text(
                data.get("redacted_output"),
                "completion.redacted_output",
                allow_empty=True,
            ),
            selected_version=_text(
                data.get("selected_version"), "completion.selected_version"
            ),
            integrity_reference=_text(
                data.get("integrity_reference"), "completion.integrity_reference"
            ),
            lock_references=tuple(
                _text(ref, "completion.lock_reference") for ref in refs
            ),
            approval_reference=approval,
        )
        if completion.completed_at < completion.admitted_at:
            raise DependencyEvidenceError("completion precedes admission")
        if completion.actual_environment_fingerprint != environment_fingerprint(actual):
            raise DependencyEvidenceError(
                "completion actual environment fingerprint is invalid"
            )
        _validate_approval_reference(kind, approval)
        return completion


@dataclass(frozen=True, slots=True)
class EvidenceAcceptance:
    dependency_id: str
    attempt_id: str
    entry_revision: str
    recipe_revision: str
    actual_environment_fingerprint: str

    def to_dict(self) -> dict[str, str]:
        return {
            "dependency_id": self.dependency_id,
            "attempt_id": self.attempt_id,
            "entry_revision": self.entry_revision,
            "recipe_revision": self.recipe_revision,
            "actual_environment_fingerprint": self.actual_environment_fingerprint,
        }

    @classmethod
    def from_dict(cls, raw: object) -> EvidenceAcceptance:
        data = _mapping(raw, "acceptance")
        _keys(
            data,
            {
                "dependency_id",
                "attempt_id",
                "entry_revision",
                "recipe_revision",
                "actual_environment_fingerprint",
            },
            "acceptance",
        )
        return cls(
            dependency_id=_text(data.get("dependency_id"), "acceptance.dependency_id"),
            attempt_id=_text(data.get("attempt_id"), "acceptance.attempt_id"),
            entry_revision=_fingerprint(
                data.get("entry_revision"), "acceptance.entry_revision"
            ),
            recipe_revision=_fingerprint(
                data.get("recipe_revision"), "acceptance.recipe_revision"
            ),
            actual_environment_fingerprint=_fingerprint(
                data.get("actual_environment_fingerprint"),
                "acceptance.actual_environment_fingerprint",
            ),
        )


@dataclass(frozen=True, slots=True)
class DependencyEvidenceSnapshot:
    snapshot_id: str
    manifest_revision: int
    created_at: datetime
    accepted: tuple[EvidenceAcceptance, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "manifest_revision": self.manifest_revision,
            "created_at": _timestamp(self.created_at),
            "accepted": [row.to_dict() for row in self.accepted],
        }

    @classmethod
    def from_dict(cls, raw: object) -> DependencyEvidenceSnapshot:
        data = _mapping(raw, "snapshot")
        _keys(
            data,
            {"snapshot_id", "manifest_revision", "created_at", "accepted"},
            "snapshot",
        )
        accepted = data.get("accepted")
        if not isinstance(accepted, list):
            raise DependencyEvidenceError("snapshot.accepted must be a list")
        rows = tuple(EvidenceAcceptance.from_dict(row) for row in accepted)
        if len({row.dependency_id for row in rows}) != len(rows):
            raise DependencyEvidenceError("snapshot dependency IDs must be unique")
        return cls(
            snapshot_id=_text(data.get("snapshot_id"), "snapshot.snapshot_id"),
            manifest_revision=_positive_int(
                data.get("manifest_revision"), "snapshot.manifest_revision"
            ),
            created_at=_datetime(data.get("created_at"), "snapshot.created_at"),
            accepted=rows,
        )


@dataclass(frozen=True, slots=True)
class ReadinessBlocker:
    dependency_id: str | None
    reason: str
    environment: dict[str, object] | None = None
    last_attempt: str | None = None
    next_action: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.reason,
            "dependency_id": self.dependency_id,
            "environment": self.environment,
            "last_attempt": self.last_attempt,
            "next_action": self.next_action,
        }


@dataclass(frozen=True, slots=True)
class DependencyEvidenceProjection:
    manifest_revision: int | None
    accepted: tuple[EvidenceAcceptance, ...]
    blockers: tuple[ReadinessBlocker, ...]

    @property
    def ready(self) -> bool:
        return not self.blockers


def evidence_path(epic_id: str, *, root: Path) -> Path:
    repo = manifest_path(epic_id, root=root).parents[4]
    return repo / _EVIDENCE_DIR / f"{epic_id}.json"


def entry_evidence_revision(entry: DependencyEntry) -> str:
    """Fingerprint evidence fields, excluding install-only operation and cleanup."""

    return _hash(
        {
            "dependency_id": entry.dependency_id,
            "requested_range": entry.requested_range,
            "resolved_version": entry.resolved_version,
            "source": entry.source,
            "integrity_reference": entry.integrity_reference,
            "lock_references": entry.lock_references,
            "target_environment": entry.target_environment.to_dict(),
            "install_scope": entry.install_scope,
            "install_destination": entry.install_destination,
            "expected_verification_result": entry.expected_verification_result,
            "feasibility_proof_requirements": entry.feasibility_proof_requirements,
            "feasibility_proof_references": entry.feasibility_proof_references,
        }
    )


def recipe_revision(entry: DependencyEntry) -> str:
    return _hash({"verification_recipe": entry.verification_recipe})


def environment_fingerprint(environment: EnvironmentIdentity) -> str:
    return _hash(environment.to_dict())


def admit_dependency_check(
    epic_id: str,
    dependency_id: str,
    *,
    root: Path,
    operation_kind: CheckOperationKind,
    exact_operation: str,
    approval_reference: str | None = None,
    lock_references: Sequence[str] = (),
    admitted_at: datetime | None = None,
) -> CheckAdmission:
    """Append an admission after binding it to the current entry and recipe."""

    manifest = require_dependency_manifest(epic_id, root=root)
    entry = _entry(manifest, dependency_id)
    try:
        kind = CheckOperationKind(operation_kind)
    except (ValueError, TypeError) as exc:
        raise DependencyEvidenceError("operation_kind is invalid") from exc
    operation = _text(exact_operation, "exact_operation")
    required_operation = (
        entry.verification_recipe
        if kind is CheckOperationKind.READ_ONLY
        else entry.operation
    )
    if operation != required_operation:
        raise DependencyEvidenceError(
            "exact operation does not match the current dependency entry"
        )
    _validate_approval_reference(kind, approval_reference)
    when = admitted_at or datetime.now(timezone.utc)
    _aware(when, "admitted_at")
    admission = CheckAdmission(
        attempt_id=f"attempt_{uuid.uuid4().hex}",
        dependency_id=dependency_id,
        manifest_revision=manifest.revision,
        entry_revision=entry_evidence_revision(entry),
        recipe_revision=recipe_revision(entry),
        exact_operation=operation,
        operation_kind=kind,
        target_environment_fingerprint=environment_fingerprint(
            entry.target_environment
        ),
        admitted_at=when,
        selected_version=entry.version,
        integrity_reference=entry.digest,
        lock_references=(
            tuple(_text(ref, "lock_reference") for ref in lock_references)
            or entry.lock_references
        ),
        approval_reference=approval_reference,
    )
    _append_event(epic_id, admission, root=root)
    return admission


def record_trusted_dependency_check_completion(
    epic_id: str,
    attempt_id: str,
    *,
    root: Path,
    actual_environment: EnvironmentIdentity,
    result: CheckResult,
    redacted_output: str,
    selected_version: str,
    integrity_reference: str,
    lock_references: Sequence[str] = (),
    completed_at: datetime | None = None,
) -> CheckCompletion:
    """Trusted recorder boundary; callers must not source environment from a request."""

    if not isinstance(actual_environment, EnvironmentIdentity):
        raise DependencyEvidenceError(
            "actual_environment must be trusted EnvironmentIdentity"
        )
    manifest = require_dependency_manifest(epic_id, root=root)
    events, _ = _read_store(epic_id, root=root)
    admissions = {
        event.attempt_id: event for event in events if isinstance(event, CheckAdmission)
    }
    completions = {
        event.attempt_id for event in events if isinstance(event, CheckCompletion)
    }
    admission = admissions.get(attempt_id)
    if admission is None:
        raise CheckAttemptNotFound(attempt_id)
    if attempt_id in completions:
        raise CheckAttemptAlreadyCompleted(attempt_id)
    entry = next(
        (
            row
            for row in manifest.dependencies
            if row.dependency_id == admission.dependency_id
        ),
        None,
    )
    completion_entry_revision = (
        entry_evidence_revision(entry)
        if entry is not None
        else _hash({"removed_dependency": admission.dependency_id})
    )
    completion_recipe_revision = (
        recipe_revision(entry)
        if entry is not None
        else _hash({"removed_recipe": admission.dependency_id})
    )
    try:
        check_result = CheckResult(result)
    except (ValueError, TypeError) as exc:
        raise DependencyEvidenceError("result is invalid") from exc
    when = completed_at or datetime.now(timezone.utc)
    _aware(when, "completed_at")
    completion = CheckCompletion(
        attempt_id=admission.attempt_id,
        dependency_id=admission.dependency_id,
        manifest_revision=manifest.revision,
        entry_revision=completion_entry_revision,
        recipe_revision=completion_recipe_revision,
        exact_operation=admission.exact_operation,
        operation_kind=admission.operation_kind,
        actual_environment=actual_environment,
        actual_environment_fingerprint=environment_fingerprint(actual_environment),
        admitted_at=admission.admitted_at,
        completed_at=when,
        result=check_result,
        redacted_output=_text(redacted_output, "redacted_output", allow_empty=True),
        selected_version=_text(selected_version, "selected_version"),
        integrity_reference=_text(integrity_reference, "integrity_reference"),
        lock_references=tuple(_text(ref, "lock_reference") for ref in lock_references),
        approval_reference=admission.approval_reference,
    )
    if when < admission.admitted_at:
        raise DependencyEvidenceError("completion precedes admission")
    _append_event(epic_id, completion, root=root)
    return completion


def read_dependency_check_history(
    epic_id: str, *, root: Path
) -> tuple[CheckAdmission | CheckCompletion, ...]:
    return _read_store(epic_id, root=root)[0]


def project_current_dependency_evidence(
    epic_id: str, *, root: Path
) -> DependencyEvidenceProjection:
    manifest = require_dependency_manifest(epic_id, root=root)
    if not manifest.is_current_schema:
        return DependencyEvidenceProjection(
            manifest.revision,
            (),
            (
                ReadinessBlocker(
                    None, "legacy_manifest", next_action="write_manifest_revision"
                ),
            ),
        )
    if manifest.none_required:
        return DependencyEvidenceProjection(manifest.revision, (), ())
    events, _ = _read_store(epic_id, root=root)
    admissions = {
        event.attempt_id: event for event in events if isinstance(event, CheckAdmission)
    }
    completed = [event for event in events if isinstance(event, CheckCompletion)]
    accepted: list[EvidenceAcceptance] = []
    blockers: list[ReadinessBlocker] = []
    for entry in manifest.dependencies:
        if not entry.target_environment.is_fully_specified:
            blockers.append(
                ReadinessBlocker(
                    entry.dependency_id,
                    "unknown_environment",
                    environment=entry.target_environment.to_dict(),
                    next_action="specify_target_environment",
                )
            )
            continue
        if (
            entry.feasibility_proof_requirements
            and not entry.feasibility_proof_references
        ):
            blockers.append(
                ReadinessBlocker(
                    entry.dependency_id,
                    "unresolved_feasibility",
                    environment=entry.target_environment.to_dict(),
                    next_action="record_feasibility_proof",
                )
            )
            continue
        current_entry = entry_evidence_revision(entry)
        current_recipe = recipe_revision(entry)
        candidates = [
            row for row in completed if row.dependency_id == entry.dependency_id
        ]
        chosen: CheckCompletion | None = None
        reasons: set[str] = set()
        for row in reversed(candidates):
            admission = admissions.get(row.attempt_id)
            reason = _completion_blocker(
                row, admission, entry, current_entry, current_recipe
            )
            if reason is None:
                chosen = row
                break
            reasons.add(reason)
        if chosen is None:
            reason = _preferred_blocker(reasons) if candidates else "missing_check"
            blockers.append(
                ReadinessBlocker(
                    entry.dependency_id,
                    reason,
                    environment=entry.target_environment.to_dict(),
                    last_attempt=(candidates[-1].attempt_id if candidates else None),
                    next_action=(
                        "run_dependency_check"
                        if not candidates
                        else "rerun_dependency_check"
                    ),
                )
            )
            continue
        accepted.append(
            EvidenceAcceptance(
                dependency_id=entry.dependency_id,
                attempt_id=chosen.attempt_id,
                entry_revision=current_entry,
                recipe_revision=current_recipe,
                actual_environment_fingerprint=chosen.actual_environment_fingerprint,
            )
        )
    return DependencyEvidenceProjection(
        manifest.revision, tuple(accepted), tuple(blockers)
    )


def compute_dependency_readiness(
    epic_id: str, *, root: Path
) -> DependencyEvidenceProjection:
    """Public fail-closed readiness projection used by planning entry points."""

    try:
        return project_current_dependency_evidence(epic_id, root=root)
    except DependencyManifestError as exc:
        code = (
            "missing_manifest"
            if type(exc).__name__ == "DependencyManifestNotFound"
            else "invalid_manifest"
        )
        return DependencyEvidenceProjection(
            None,
            (),
            (ReadinessBlocker(None, code, next_action="write_dependency_manifest"),),
        )
    except DependencyEvidenceError:
        return DependencyEvidenceProjection(
            None,
            (),
            (
                ReadinessBlocker(
                    None, "invalid_evidence", next_action="repair_dependency_evidence"
                ),
            ),
        )


def dependency_evidence_snapshot_is_current(
    epic_id: str, snapshot_id: str, *, root: Path
) -> bool:
    """Return whether an immutable snapshot still exactly represents readiness."""

    snapshot = next(
        (
            row
            for row in read_dependency_evidence_snapshots(epic_id, root=root)
            if row.snapshot_id == snapshot_id
        ),
        None,
    )
    if snapshot is None:
        return False
    readiness = compute_dependency_readiness(epic_id, root=root)
    # Manifest revision is audit context, not an invalidation key.  Entry and
    # recipe fingerprints selectively invalidate only evidence that changed.
    return readiness.ready and snapshot.accepted == readiness.accepted


def create_dependency_evidence_snapshot(
    epic_id: str,
    *,
    root: Path,
    created_at: datetime | None = None,
) -> DependencyEvidenceSnapshot:
    projection = project_current_dependency_evidence(epic_id, root=root)
    if not projection.ready:
        details = ", ".join(
            f"{row.dependency_id}:{row.reason}" for row in projection.blockers
        )
        raise DependencyReadinessError(f"dependency evidence is not current: {details}")
    when = created_at or datetime.now(timezone.utc)
    _aware(when, "created_at")
    snapshot = DependencyEvidenceSnapshot(
        snapshot_id=f"evidence_{uuid.uuid4().hex}",
        manifest_revision=projection.manifest_revision,
        created_at=when,
        accepted=projection.accepted,
    )
    _append_snapshot(epic_id, snapshot, root=root)
    return snapshot


def read_dependency_evidence_snapshots(
    epic_id: str, *, root: Path
) -> tuple[DependencyEvidenceSnapshot, ...]:
    return _read_store(epic_id, root=root)[1]


def _completion_blocker(
    completion: CheckCompletion,
    admission: CheckAdmission | None,
    entry: DependencyEntry,
    current_entry: str,
    current_recipe: str,
) -> str | None:
    if (
        admission is None
        or completion.entry_revision != admission.entry_revision
        or completion.recipe_revision != admission.recipe_revision
    ):
        return "stale_admission"
    if (
        completion.entry_revision != current_entry
        or completion.recipe_revision != current_recipe
    ):
        return "stale_check"
    if completion.result is not CheckResult.SUCCEEDED:
        return "check_failed"
    if not set(entry.feasibility_proof_references).issubset(completion.lock_references):
        return "unresolved_feasibility"
    if not _environment_complete(completion.actual_environment):
        return "unknown_environment"
    if not environment_identities_match(
        entry.target_environment, completion.actual_environment
    ):
        return "mismatched_environment"
    if (
        completion.selected_version != entry.version
        or completion.integrity_reference != entry.digest
    ):
        return "stale_check"
    expected = entry.expected_verification_result.strip()
    if (
        expected.casefold() not in {"success", "succeeded"}
        and expected not in completion.redacted_output
    ):
        return "unexpected_result"
    return None


def _preferred_blocker(reasons: set[str]) -> str:
    for reason in (
        "unknown_environment",
        "mismatched_environment",
        "stale_admission",
        "stale_check",
        "check_failed",
        "unresolved_feasibility",
        "unexpected_result",
    ):
        if reason in reasons:
            return reason
    return "missing_check"


def _environment_complete(environment: EnvironmentIdentity) -> bool:
    return environment.is_fully_specified


def _entry(manifest: DependencyManifestSnapshot, dependency_id: str) -> DependencyEntry:
    for entry in manifest.dependencies:
        if entry.dependency_id == dependency_id:
            return entry
    raise DependencyEvidenceError(
        f"dependency {dependency_id!r} is not in the current manifest"
    )


def _append_event(
    epic_id: str, event: CheckAdmission | CheckCompletion, *, root: Path
) -> None:
    with process_lock:
        events, snapshots = _read_store(epic_id, root=root)
        if isinstance(event, CheckAdmission) and any(
            row.attempt_id == event.attempt_id for row in events
        ):
            raise DependencyEvidenceError("attempt ID already exists")
        _write_store(
            epic_id,
            (*events, event),
            snapshots,
            root=root,
            message=f"docs: record {epic_id} dependency check {event.attempt_id}",
        )


def _append_snapshot(
    epic_id: str, snapshot: DependencyEvidenceSnapshot, *, root: Path
) -> None:
    with process_lock:
        events, snapshots = _read_store(epic_id, root=root)
        if any(row.snapshot_id == snapshot.snapshot_id for row in snapshots):
            raise DependencyEvidenceError("snapshot ID already exists")
        _write_store(
            epic_id,
            events,
            (*snapshots, snapshot),
            root=root,
            message=f"docs: snapshot {epic_id} dependency evidence",
        )


def _read_store(
    epic_id: str, *, root: Path
) -> tuple[
    tuple[CheckAdmission | CheckCompletion, ...], tuple[DependencyEvidenceSnapshot, ...]
]:
    path = evidence_path(epic_id, root=root)
    if not path.is_file():
        return (), ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyEvidenceError(
            f"cannot read dependency evidence for {epic_id}"
        ) from exc
    data = _mapping(raw, "evidence store")
    _keys(data, {"version", "epic_id", "events", "snapshots"}, "evidence store")
    if data.get("version") != _SCHEMA_VERSION or data.get("epic_id") != epic_id:
        raise DependencyEvidenceError(
            "dependency evidence identity or schema is invalid"
        )
    event_rows = data.get("events")
    snapshot_rows = data.get("snapshots")
    if not isinstance(event_rows, list) or not isinstance(snapshot_rows, list):
        raise DependencyEvidenceError("evidence events and snapshots must be lists")
    events: list[CheckAdmission | CheckCompletion] = []
    admitted: set[str] = set()
    completed: set[str] = set()
    for row in event_rows:
        row_type = row.get("type") if isinstance(row, Mapping) else None
        event = (
            CheckAdmission.from_dict(row)
            if row_type == "admitted"
            else CheckCompletion.from_dict(row)
        )
        if isinstance(event, CheckAdmission):
            if event.attempt_id in admitted:
                raise DependencyEvidenceError("duplicate check admission")
            admitted.add(event.attempt_id)
        else:
            if event.attempt_id not in admitted or event.attempt_id in completed:
                raise DependencyEvidenceError("completion must follow one admission")
            admission = next(
                item for item in events if item.attempt_id == event.attempt_id
            )
            if (
                event.dependency_id != admission.dependency_id
                or event.exact_operation != admission.exact_operation
                or event.operation_kind != admission.operation_kind
                or event.approval_reference != admission.approval_reference
                or event.admitted_at != admission.admitted_at
            ):
                raise DependencyEvidenceError(
                    "completion identity does not match admission"
                )
            completed.add(event.attempt_id)
        events.append(event)
    snapshots = tuple(
        DependencyEvidenceSnapshot.from_dict(row) for row in snapshot_rows
    )
    if len({row.snapshot_id for row in snapshots}) != len(snapshots):
        raise DependencyEvidenceError("duplicate evidence snapshot ID")
    return tuple(events), snapshots


def _write_store(
    epic_id: str,
    events: Sequence[CheckAdmission | CheckCompletion],
    snapshots: Sequence[DependencyEvidenceSnapshot],
    *,
    root: Path,
    message: str,
) -> None:
    path = evidence_path(epic_id, root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "epic_id": epic_id,
        "events": [row.to_dict() for row in events],
        "snapshots": [row.to_dict() for row in snapshots],
    }
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary = handle.name
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    if has_git(path.parents[4]):
        commit_paths(path.parents[4], [path], message)
        from cascade.workspace.integration_worktree import invalidate_merged_board

        invalidate_merged_board(locate_trunk(path.parents[4]))


def _hash(value: object) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _validate_approval_reference(
    kind: CheckOperationKind, approval: str | None
) -> None:
    if kind is CheckOperationKind.READ_ONLY:
        if approval is not None:
            raise DependencyEvidenceError(
                "read-only checks do not accept installation approval"
            )
    elif approval is None or not isinstance(approval, str) or not approval.strip():
        raise DependencyEvidenceError(
            "installation and upgrade checks require an approval reference"
        )


def _timestamp(value: datetime) -> str:
    _aware(value, "timestamp")
    return value.astimezone(timezone.utc).isoformat()


def _datetime(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise DependencyEvidenceError(f"{field} must be a timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise DependencyEvidenceError(f"{field} is invalid") from exc
    _aware(parsed, field)
    return parsed


def _aware(value: datetime, field: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise DependencyEvidenceError(f"{field} must be timezone-aware")


def _mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise DependencyEvidenceError(f"{field} must be an object")
    return value


def _keys(data: Mapping[str, object], expected: set[str], field: str) -> None:
    if set(data) != expected:
        raise DependencyEvidenceError(f"{field} fields are invalid")


def _text(value: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise DependencyEvidenceError(f"{field} must be a string")
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DependencyEvidenceError(f"{field} must be a positive integer")
    return value


def _fingerprint(value: object, field: str) -> str:
    text = _text(value, field)
    if not text.startswith("sha256:") or len(text) != 71:
        raise DependencyEvidenceError(f"{field} must be a sha256 fingerprint")
    return text
