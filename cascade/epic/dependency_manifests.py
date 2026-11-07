"""Revisioned dependency manifests owned by an epic's planning repository.

This module deliberately only persists declarations.  It does not install or
check dependencies; later slices consume these contracts at those boundaries.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

from cascade.board.context import resolve_tracking_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import commit_paths, has_git
from cascade.board.lock import process_lock
from cascade.board.store import read_doc
from cascade.workspace.doc_root import resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk

_SIDECAR_DIR = Path("docs") / "epics" / "2_active" / "_dependency_manifests"
_SCHEMA_VERSION = 2
_LEGACY_SCHEMA_VERSION = 1
_UNKNOWN_VALUES = frozenset({"unknown", "unspecified", "pending", "unresolved"})
_DEPENDENCY_ID_RE = re.compile(r"^dep_[a-z0-9][a-z0-9_-]*$")


class DependencyManifestError(ValueError):
    """Base error for an invalid dependency manifest operation."""


class DependencyManifestNotFound(DependencyManifestError):
    """No manifest has been supplied for the epic yet."""


class InvalidDependencyManifest(DependencyManifestError):
    """A manifest or stored snapshot violates the public schema."""


class StaleDependencyManifestRevision(DependencyManifestError):
    """The writer's expected revision is not current."""


@dataclass(frozen=True, slots=True)
class EnvironmentIdentity:
    """Stable identity for either a desired or observed execution environment."""

    environment_id: str
    kind: str
    platform: str
    architecture: str
    runner: str | None = None
    repository: str | None = None
    worktree: str | None = None
    sandbox: str | None = None
    runtime: str | None = None
    container_digest: str | None = None

    def __post_init__(self) -> None:
        for field in ("environment_id", "kind", "platform", "architecture"):
            _require_text(getattr(self, field), f"environment.{field}")
        # The first four fields are retained as source-compatible labels for the
        # slice-A API.  New records persist the execution identity explicitly.
        defaults = {
            "runner": self.environment_id,
            "repository": "current-repository",
            "worktree": self.environment_id,
            "sandbox": self.kind,
            "runtime": f"{self.platform}/{self.architecture}",
            "container_digest": (
                "unknown" if self.kind.casefold() == "container" else "not_applicable"
            ),
        }
        for field, default in defaults.items():
            value = getattr(self, field)
            if value is None:
                object.__setattr__(self, field, default)
            else:
                _require_text(value, f"environment.{field}")

    def to_dict(self) -> dict[str, str]:
        return {
            "environment_id": self.environment_id,
            "kind": self.kind,
            "platform": self.platform,
            "architecture": self.architecture,
            "runner": self.runner,
            "repository": self.repository,
            "worktree": self.worktree,
            "sandbox": self.sandbox,
            "runtime": self.runtime,
            "container_digest": self.container_digest,
        }

    @classmethod
    def from_dict(
        cls, raw: object, *, field: str = "environment"
    ) -> EnvironmentIdentity:
        data = _require_mapping(raw, field)
        legacy = {"environment_id", "kind", "platform", "architecture"}
        current = legacy | {
            "runner",
            "repository",
            "worktree",
            "sandbox",
            "runtime",
            "container_digest",
        }
        if set(data) not in (legacy, current):
            _require_exact_keys(data, current, field)
        return cls(
            environment_id=_required_string(data, "environment_id", field),
            kind=_required_string(data, "kind", field),
            platform=_required_string(data, "platform", field),
            architecture=_required_string(data, "architecture", field),
            runner=_optional_string(data, "runner", field),
            repository=_optional_string(data, "repository", field),
            worktree=_optional_string(data, "worktree", field),
            sandbox=_optional_string(data, "sandbox", field),
            runtime=_optional_string(data, "runtime", field),
            container_digest=_optional_string(data, "container_digest", field),
        )

    @property
    def is_fully_specified(self) -> bool:
        values = (
            self.runner,
            self.repository,
            self.worktree,
            self.sandbox,
            self.runtime,
            self.container_digest,
        )
        if not all(
            isinstance(value, str) and value.strip().casefold() not in _UNKNOWN_VALUES
            for value in values
        ):
            return False
        return not (
            self.kind.casefold() == "container"
            and self.container_digest.strip().casefold()
            in {"not_applicable", "not applicable", "n/a"}
        )


@dataclass(frozen=True, slots=True)
class DependencyEntry:
    """One independently identifiable, approvable software dependency."""

    dependency_id: str
    version: str
    source: str
    digest: str
    target_environment: EnvironmentIdentity
    install_scope: str
    operation: str
    cleanup_plan: str
    verification_recipe: str
    requested_range: str | None = None
    resolved_version: str | None = None
    expected_verification_result: str = "success"
    feasibility_proof_requirements: tuple[str, ...] = ()
    feasibility_proof_references: tuple[str, ...] = ()
    install_destination: str | None = None
    lock_references: tuple[str, ...] = ()
    integrity_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.dependency_id, str) or not _DEPENDENCY_ID_RE.fullmatch(
            self.dependency_id
        ):
            raise InvalidDependencyManifest(
                "dependency_id must match 'dep_[a-z0-9][a-z0-9_-]*'"
            )
        for field in (
            "version",
            "source",
            "digest",
            "install_scope",
            "operation",
            "cleanup_plan",
            "verification_recipe",
        ):
            _require_text(getattr(self, field), f"dependency.{field}")
        if not isinstance(self.target_environment, EnvironmentIdentity):
            raise InvalidDependencyManifest(
                "dependency.target_environment must be an EnvironmentIdentity"
            )
        derived = {
            "requested_range": self.version,
            "resolved_version": self.version,
            "install_destination": self.install_scope,
            "integrity_reference": self.digest,
        }
        for field, default in derived.items():
            value = getattr(self, field)
            if value is None:
                object.__setattr__(self, field, default)
            else:
                _require_text(value, f"dependency.{field}")
        _require_text(
            self.expected_verification_result,
            "dependency.expected_verification_result",
        )
        for field in (
            "feasibility_proof_requirements",
            "feasibility_proof_references",
            "lock_references",
        ):
            value = getattr(self, field)
            if not isinstance(value, tuple) or not all(
                isinstance(item, str) and item.strip() for item in value
            ):
                raise InvalidDependencyManifest(
                    f"dependency.{field} must be a tuple of strings"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "dependency_id": self.dependency_id,
            "version": self.version,
            "source": self.source,
            "digest": self.digest,
            "target_environment": self.target_environment.to_dict(),
            "install_scope": self.install_scope,
            "operation": self.operation,
            "cleanup_plan": self.cleanup_plan,
            "verification_recipe": self.verification_recipe,
            "requested_range": self.requested_range or self.version,
            "resolved_version": self.resolved_version or self.version,
            "expected_verification_result": self.expected_verification_result,
            "feasibility_proof_requirements": list(self.feasibility_proof_requirements),
            "feasibility_proof_references": list(self.feasibility_proof_references),
            "install_destination": self.install_destination or self.install_scope,
            "lock_references": list(self.lock_references),
            "integrity_reference": self.integrity_reference or self.digest,
        }

    @classmethod
    def from_dict(cls, raw: object) -> DependencyEntry:
        data = _require_mapping(raw, "dependency")
        fields = {
            "dependency_id",
            "version",
            "source",
            "digest",
            "target_environment",
            "install_scope",
            "operation",
            "cleanup_plan",
            "verification_recipe",
        }
        legacy = set(data) == fields
        current_fields = fields | {
            "requested_range",
            "resolved_version",
            "expected_verification_result",
            "feasibility_proof_requirements",
            "feasibility_proof_references",
            "install_destination",
            "lock_references",
            "integrity_reference",
        }
        if not legacy:
            _require_exact_keys(data, current_fields, "dependency")
        requirements = data.get("feasibility_proof_requirements", [])
        references = data.get("feasibility_proof_references", [])
        locks = data.get("lock_references", [])
        for value, name in (
            (requirements, "feasibility_proof_requirements"),
            (references, "feasibility_proof_references"),
            (locks, "lock_references"),
        ):
            if not isinstance(value, list):
                raise InvalidDependencyManifest(f"dependency.{name} must be a list")
        return cls(
            dependency_id=_required_string(data, "dependency_id", "dependency"),
            version=_required_string(data, "version", "dependency"),
            source=_required_string(data, "source", "dependency"),
            digest=_required_string(data, "digest", "dependency"),
            target_environment=EnvironmentIdentity.from_dict(
                data.get("target_environment"), field="dependency.target_environment"
            ),
            install_scope=_required_string(data, "install_scope", "dependency"),
            operation=_required_string(data, "operation", "dependency"),
            cleanup_plan=_required_string(data, "cleanup_plan", "dependency"),
            verification_recipe=_required_string(
                data, "verification_recipe", "dependency"
            ),
            requested_range=(
                None
                if legacy
                else _required_string(data, "requested_range", "dependency")
            ),
            resolved_version=(
                None
                if legacy
                else _required_string(data, "resolved_version", "dependency")
            ),
            expected_verification_result=(
                "success"
                if legacy
                else _required_string(
                    data, "expected_verification_result", "dependency"
                )
            ),
            feasibility_proof_requirements=tuple(
                _require_text(row, "dependency.feasibility_proof_requirement")
                for row in requirements
            ),
            feasibility_proof_references=tuple(
                _require_text(row, "dependency.feasibility_proof_reference")
                for row in references
            ),
            install_destination=(
                None
                if legacy
                else _required_string(data, "install_destination", "dependency")
            ),
            lock_references=tuple(
                _require_text(row, "dependency.lock_reference") for row in locks
            ),
            integrity_reference=(
                None
                if legacy
                else _required_string(data, "integrity_reference", "dependency")
            ),
        )


@dataclass(frozen=True, slots=True)
class DependencyManifestDraft:
    """Validated content supplied by a planner before persistence assigns a revision."""

    target_environment: EnvironmentIdentity
    actual_environment: EnvironmentIdentity | None
    none_required: bool
    dependencies: tuple[DependencyEntry, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.target_environment, EnvironmentIdentity):
            raise InvalidDependencyManifest(
                "target_environment must be an EnvironmentIdentity"
            )
        if self.actual_environment is not None and not isinstance(
            self.actual_environment, EnvironmentIdentity
        ):
            raise InvalidDependencyManifest(
                "actual_environment must be an EnvironmentIdentity or null"
            )
        if not isinstance(self.none_required, bool):
            raise InvalidDependencyManifest("none_required must be a boolean")
        if not isinstance(self.dependencies, tuple) or not all(
            isinstance(row, DependencyEntry) for row in self.dependencies
        ):
            raise InvalidDependencyManifest("dependencies must be dependency entries")
        if self.none_required and self.dependencies:
            raise InvalidDependencyManifest(
                "none_required manifests cannot contain dependencies"
            )
        if not self.none_required and not self.dependencies:
            raise InvalidDependencyManifest(
                "an empty manifest must explicitly set none_required to true"
            )
        ids = [row.dependency_id for row in self.dependencies]
        if len(ids) != len(set(ids)):
            raise InvalidDependencyManifest("dependency_id values must be unique")
        # The top-level target is a compatibility/display default only.  Current
        # authority is always the per-entry target, so entries may differ.

    def to_dict(self) -> dict[str, object]:
        return {
            "target_environment": self.target_environment.to_dict(),
            "actual_environment": (
                self.actual_environment.to_dict() if self.actual_environment else None
            ),
            "none_required": self.none_required,
            "dependencies": [row.to_dict() for row in self.dependencies],
        }

    @classmethod
    def from_dict(cls, raw: object) -> DependencyManifestDraft:
        data = _require_mapping(raw, "manifest")
        _require_exact_keys(
            data,
            {
                "target_environment",
                "actual_environment",
                "none_required",
                "dependencies",
            },
            "manifest",
        )
        rows = data.get("dependencies")
        if not isinstance(rows, list):
            raise InvalidDependencyManifest("manifest.dependencies must be a list")
        none_required = data.get("none_required")
        if not isinstance(none_required, bool):
            raise InvalidDependencyManifest("manifest.none_required must be a boolean")
        actual_raw = data.get("actual_environment")
        return cls(
            target_environment=EnvironmentIdentity.from_dict(
                data.get("target_environment"), field="manifest.target_environment"
            ),
            actual_environment=(
                None
                if actual_raw is None
                else EnvironmentIdentity.from_dict(
                    actual_raw, field="manifest.actual_environment"
                )
            ),
            none_required=none_required,
            dependencies=tuple(DependencyEntry.from_dict(row) for row in rows),
        )


@dataclass(frozen=True, slots=True)
class DependencyManifestSnapshot:
    """Immutable content snapshot within an epic's append-only manifest history."""

    revision: int
    recorded_at: datetime
    target_environment: EnvironmentIdentity
    actual_environment: EnvironmentIdentity | None
    none_required: bool
    dependencies: tuple[DependencyEntry, ...]
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            isinstance(self.revision, bool)
            or not isinstance(self.revision, int)
            or self.revision < 1
        ):
            raise InvalidDependencyManifest(
                "manifest revision must be a positive integer"
            )
        if (
            not isinstance(self.recorded_at, datetime)
            or self.recorded_at.tzinfo is None
        ):
            raise InvalidDependencyManifest("recorded_at must be timezone-aware")
        DependencyManifestDraft(
            target_environment=self.target_environment,
            actual_environment=self.actual_environment,
            none_required=self.none_required,
            dependencies=self.dependencies,
        )

    @property
    def draft(self) -> DependencyManifestDraft:
        return DependencyManifestDraft(
            target_environment=self.target_environment,
            actual_environment=self.actual_environment,
            none_required=self.none_required,
            dependencies=self.dependencies,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "recorded_at": self.recorded_at.astimezone(timezone.utc).isoformat(),
            **self.draft.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, raw: object, *, schema_version: int = _SCHEMA_VERSION
    ) -> DependencyManifestSnapshot:
        data = _require_mapping(raw, "snapshot")
        _require_exact_keys(
            data,
            {
                "revision",
                "recorded_at",
                "target_environment",
                "actual_environment",
                "none_required",
                "dependencies",
            },
            "snapshot",
        )
        revision = data.get("revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise InvalidDependencyManifest("snapshot.revision must be an integer")
        recorded = data.get("recorded_at")
        if not isinstance(recorded, str):
            raise InvalidDependencyManifest("snapshot.recorded_at must be a string")
        try:
            when = datetime.fromisoformat(recorded.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidDependencyManifest("snapshot.recorded_at is invalid") from exc
        draft = DependencyManifestDraft.from_dict(
            {
                key: value
                for key, value in data.items()
                if key not in {"revision", "recorded_at"}
            }
        )
        return cls(
            revision=revision,
            recorded_at=when,
            schema_version=schema_version,
            **_draft_to_dict_for_init(draft),
        )

    @property
    def is_current_schema(self) -> bool:
        return self.schema_version == _SCHEMA_VERSION


def _draft_to_dict_for_init(draft: DependencyManifestDraft) -> dict[str, object]:
    return {
        "target_environment": draft.target_environment,
        "actual_environment": draft.actual_environment,
        "none_required": draft.none_required,
        "dependencies": draft.dependencies,
    }


@dataclass(frozen=True, slots=True)
class InstallationBinding:
    """Fields that must remain unchanged for per-dependency install authority."""

    dependency_id: str
    version: str
    source: str
    digest: str
    target_environment: EnvironmentIdentity
    install_scope: str
    install_destination: str
    operation: str
    cleanup_plan: str

    def __post_init__(self) -> None:
        if not isinstance(self.dependency_id, str) or not _DEPENDENCY_ID_RE.fullmatch(
            self.dependency_id
        ):
            raise InvalidDependencyManifest("approval binding dependency_id is invalid")
        for field in (
            "version",
            "source",
            "digest",
            "install_scope",
            "install_destination",
            "operation",
            "cleanup_plan",
        ):
            _require_text(getattr(self, field), f"approval.binding.{field}")
        if not isinstance(self.target_environment, EnvironmentIdentity):
            raise InvalidDependencyManifest(
                "approval.binding.target_environment must be an EnvironmentIdentity"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "dependency_id": self.dependency_id,
            "version": self.version,
            "source": self.source,
            "digest": self.digest,
            "target_environment": self.target_environment.to_dict(),
            "install_scope": self.install_scope,
            "install_destination": self.install_destination,
            "operation": self.operation,
            "cleanup_plan": self.cleanup_plan,
        }

    @classmethod
    def from_dict(cls, raw: object) -> InstallationBinding:
        data = _require_mapping(raw, "approval.binding")
        fields = {
            "dependency_id",
            "version",
            "source",
            "digest",
            "target_environment",
            "install_scope",
            "operation",
            "cleanup_plan",
        }
        legacy = set(data) == fields
        fields.add("install_destination")
        if not legacy:
            _require_exact_keys(data, fields, "approval.binding")
        dependency_id = _required_string(data, "dependency_id", "approval.binding")
        if not _DEPENDENCY_ID_RE.fullmatch(dependency_id):
            raise InvalidDependencyManifest("approval.binding.dependency_id is invalid")
        return cls(
            dependency_id=dependency_id,
            version=_required_string(data, "version", "approval.binding"),
            source=_required_string(data, "source", "approval.binding"),
            digest=_required_string(data, "digest", "approval.binding"),
            target_environment=EnvironmentIdentity.from_dict(
                data.get("target_environment"),
                field="approval.binding.target_environment",
            ),
            install_scope=_required_string(data, "install_scope", "approval.binding"),
            install_destination=(
                _required_string(data, "install_scope", "approval.binding")
                if legacy
                else _required_string(data, "install_destination", "approval.binding")
            ),
            operation=_required_string(data, "operation", "approval.binding"),
            cleanup_plan=_required_string(data, "cleanup_plan", "approval.binding"),
        )

    @classmethod
    def from_entry(cls, entry: DependencyEntry) -> InstallationBinding:
        return cls(
            dependency_id=entry.dependency_id,
            version=entry.version,
            source=entry.source,
            digest=entry.digest,
            target_environment=entry.target_environment,
            install_scope=entry.install_scope,
            install_destination=entry.install_destination or entry.install_scope,
            operation=entry.operation,
            cleanup_plan=entry.cleanup_plan,
        )


@dataclass(frozen=True, slots=True)
class InstallationApproval:
    """Canonical approval record for slice B; persistence is intentionally deferred."""

    approval_id: str
    binding: InstallationBinding
    approver_id: str
    approved_at: datetime
    reviewed_manifest_revision: int
    reviewed_entry: DependencyEntry
    schema_version: int = _SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text(self.approval_id, "approval_id")
        _require_text(self.approver_id, "approver_id")
        if not isinstance(self.binding, InstallationBinding):
            raise InvalidDependencyManifest("binding must be an InstallationBinding")
        if (
            not isinstance(self.approved_at, datetime)
            or self.approved_at.tzinfo is None
        ):
            raise InvalidDependencyManifest("approved_at must be timezone-aware")
        if (
            isinstance(self.reviewed_manifest_revision, bool)
            or not isinstance(self.reviewed_manifest_revision, int)
            or self.reviewed_manifest_revision < 1
        ):
            raise InvalidDependencyManifest(
                "reviewed_manifest_revision must be positive"
            )
        if not isinstance(self.reviewed_entry, DependencyEntry):
            raise InvalidDependencyManifest("reviewed_entry must be a DependencyEntry")
        if self.binding != InstallationBinding.from_entry(self.reviewed_entry):
            raise InvalidDependencyManifest(
                "approval binding must match the reviewed entry snapshot"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "approval_id": self.approval_id,
            "binding": self.binding.to_dict(),
            "approver_id": self.approver_id,
            "approved_at": self.approved_at.astimezone(timezone.utc).isoformat(),
            "reviewed_manifest_revision": self.reviewed_manifest_revision,
            "reviewed_entry": self.reviewed_entry.to_dict(),
        }

    @classmethod
    def from_dict(
        cls, raw: object, *, schema_version: int = _SCHEMA_VERSION
    ) -> InstallationApproval:
        data = _require_mapping(raw, "approval")
        fields = {
            "approval_id",
            "binding",
            "approver_id",
            "approved_at",
            "reviewed_manifest_revision",
            "reviewed_entry",
        }
        legacy = set(data) == fields
        if not legacy:
            _require_exact_keys(data, fields | {"schema_version"}, "approval")
        approved_at = data.get("approved_at")
        if not isinstance(approved_at, str):
            raise InvalidDependencyManifest("approval.approved_at must be a string")
        try:
            when = datetime.fromisoformat(approved_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise InvalidDependencyManifest("approval.approved_at is invalid") from exc
        revision = data.get("reviewed_manifest_revision")
        if isinstance(revision, bool) or not isinstance(revision, int):
            raise InvalidDependencyManifest(
                "approval.reviewed_manifest_revision must be an integer"
            )
        return cls(
            approval_id=_required_string(data, "approval_id", "approval"),
            binding=InstallationBinding.from_dict(data.get("binding")),
            approver_id=_required_string(data, "approver_id", "approval"),
            approved_at=when,
            reviewed_manifest_revision=revision,
            reviewed_entry=DependencyEntry.from_dict(data.get("reviewed_entry")),
            schema_version=(
                schema_version
                if legacy
                else _positive_schema_version(
                    data.get("schema_version"), "approval.schema_version"
                )
            ),
        )


def installation_approval_is_valid(
    approval: InstallationApproval, entry: DependencyEntry
) -> bool:
    """Whole-manifest revisions do not revoke an unchanged entry binding."""

    return approval.binding == InstallationBinding.from_entry(entry)


def environment_identities_match(
    target: EnvironmentIdentity, actual: EnvironmentIdentity
) -> bool:
    """Match trusted execution identity field-by-field; unknown never matches."""

    if not target.is_fully_specified or not actual.is_fully_specified:
        return False
    return (
        target.runner,
        target.repository,
        target.worktree,
        target.sandbox,
        target.runtime,
        target.container_digest,
    ) == (
        actual.runner,
        actual.repository,
        actual.worktree,
        actual.sandbox,
        actual.runtime,
        actual.container_digest,
    )


def validate_dependency_manifest(raw: object) -> DependencyManifestDraft:
    """Validate an unrevisioned public payload and return its typed form."""

    if isinstance(raw, DependencyManifestDraft):
        # Canonicalize compatibility defaults before equality, fingerprinting,
        # or persistence so dataclass replacement cannot retain stale derived
        # values when a legacy field changes.
        return DependencyManifestDraft.from_dict(raw.to_dict())
    return DependencyManifestDraft.from_dict(raw)


def manifest_path(epic_id: str, *, root: Path) -> Path:
    """Resolve the epic-owned sidecar path in the tracking repository."""

    repo = _manifest_repo(epic_id, root=root)
    return repo / _SIDECAR_DIR / f"{epic_id}.json"


def read_dependency_manifest_history(
    epic_id: str, *, root: Path
) -> tuple[DependencyManifestSnapshot, ...]:
    """Read all immutable snapshots; absence is a distinct empty history."""

    path = manifest_path(epic_id, root=root)
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InvalidDependencyManifest(
            f"cannot read dependency manifest for {epic_id}"
        ) from exc
    data = _require_mapping(raw, "manifest history")
    _require_exact_keys(data, {"version", "epic_id", "snapshots"}, "manifest history")
    schema_version = data.get("version")
    if schema_version not in {_LEGACY_SCHEMA_VERSION, _SCHEMA_VERSION}:
        raise InvalidDependencyManifest(
            "unsupported dependency manifest schema version"
        )
    if data.get("epic_id") != epic_id:
        raise InvalidDependencyManifest(
            "dependency manifest epic_id does not match path"
        )
    rows = data.get("snapshots")
    if not isinstance(rows, list) or not rows:
        raise InvalidDependencyManifest(
            "persisted manifest history must contain a snapshot"
        )
    snapshots = tuple(
        DependencyManifestSnapshot.from_dict(row, schema_version=schema_version)
        for row in rows
    )
    expected = tuple(range(1, len(snapshots) + 1))
    if tuple(row.revision for row in snapshots) != expected:
        raise InvalidDependencyManifest(
            "dependency manifest revisions must be contiguous and append-only"
        )
    return snapshots


def read_dependency_manifest(
    epic_id: str, *, root: Path, revision: int | None = None
) -> DependencyManifestSnapshot | None:
    """Read the current snapshot, a named revision, or ``None`` when absent."""

    history = read_dependency_manifest_history(epic_id, root=root)
    if not history:
        return None
    if revision is None:
        return history[-1]
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
        raise InvalidDependencyManifest("revision must be a positive integer")
    try:
        return history[revision - 1]
    except IndexError:
        return None


def require_dependency_manifest(
    epic_id: str, *, root: Path
) -> DependencyManifestSnapshot:
    """Read the current snapshot and fail closed when the legacy state is absent."""

    manifest = read_dependency_manifest(epic_id, root=root)
    if manifest is None:
        raise DependencyManifestNotFound(
            f"{epic_id} must supply a dependency manifest before its next planning action"
        )
    return manifest


def write_dependency_manifest(
    epic_id: str,
    manifest: DependencyManifestDraft | Mapping[str, object],
    *,
    root: Path,
    expected_revision: int | None = None,
    recorded_at: datetime | None = None,
) -> DependencyManifestSnapshot:
    """Append a validated snapshot with optimistic revision protection.

    Re-submitting identical content is idempotent.  On first write callers may
    use ``expected_revision=0``; subsequent writes name the current revision.
    """

    draft = validate_dependency_manifest(manifest)
    repo = _manifest_repo(epic_id, root=root)
    doc = read_doc(epic_id, root=repo)
    if doc.meta.tier != "epic" or doc.meta.path.parent.name != "2_active":
        raise DependencyManifestError(
            "dependency manifests can only be written for active epics"
        )
    when = recorded_at or datetime.now(timezone.utc)
    if when.tzinfo is None:
        raise InvalidDependencyManifest("recorded_at must be timezone-aware")
    path = repo / _SIDECAR_DIR / f"{epic_id}.json"
    with process_lock:
        history = read_dependency_manifest_history(epic_id, root=repo)
        current_revision = history[-1].revision if history else 0
        if expected_revision is not None and expected_revision != current_revision:
            raise StaleDependencyManifestRevision(
                f"stale dependency manifest revision for {epic_id}: "
                f"current is {current_revision}, expected {expected_revision}"
            )
        if history and history[-1].draft == draft:
            return history[-1]
        snapshot = DependencyManifestSnapshot(
            revision=current_revision + 1,
            recorded_at=when,
            **_draft_to_dict_for_init(draft),
        )
        updated = (*history, snapshot)
        _write_history(path, epic_id, updated)
        if has_git(repo):
            from cascade.workspace.integration_worktree import (
                git_root_for_path,
                invalidate_merged_board,
            )

            commit_root = git_root_for_path(path)
            commit_paths(
                commit_root,
                [path],
                f"docs: {epic_id} dependency manifest revision {snapshot.revision}",
            )
            invalidate_merged_board(locate_trunk(repo))
    return snapshot


def _write_history(
    path: Path, epic_id: str, snapshots: Sequence[DependencyManifestSnapshot]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": _SCHEMA_VERSION,
        "epic_id": epic_id,
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


def _manifest_repo(epic_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_tracking_root(root))
    try:
        return resolve_doc_worktree(epic_id, root=trunk)
    except NotFound:
        return trunk


def _require_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidDependencyManifest(f"{field} must be a non-blank string")
    return value


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise InvalidDependencyManifest(f"{field} must be an object")
    if not all(isinstance(key, str) for key in value):
        raise InvalidDependencyManifest(f"{field} keys must be strings")
    return value


def _require_exact_keys(
    data: Mapping[str, object], required: set[str], field: str
) -> None:
    missing = required - set(data)
    unknown = set(data) - required
    if missing:
        raise InvalidDependencyManifest(
            f"{field} is missing required field(s): {', '.join(sorted(missing))}"
        )
    if unknown:
        raise InvalidDependencyManifest(
            f"{field} has unknown field(s): {', '.join(sorted(unknown))}"
        )


def _required_string(data: Mapping[str, object], key: str, field: str) -> str:
    return _require_text(data.get(key), f"{field}.{key}")


def _optional_string(data: Mapping[str, object], key: str, field: str) -> str | None:
    if key not in data:
        return None
    return _require_text(data.get(key), f"{field}.{key}")


def _positive_schema_version(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidDependencyManifest(f"{field} must be a positive integer")
    return value
