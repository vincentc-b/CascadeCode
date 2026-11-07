"""Durable epic-owned bootstrap scope and feasibility state.

The bootstrap is a sidecar of an active epic, not a feature or another board
tier.  Its human review authorizes only the bounded feasibility artifacts in
the scope.  In particular, nothing in this module grants dependency
installation authority; setup runners must independently use
``dependency_approvals`` at their mutation boundary.
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
from cascade.board.store import read_doc
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.epic.dependency_evidence import compute_dependency_readiness
from cascade.epic.dependency_manifests import (
    DependencyManifestSnapshot,
    EnvironmentIdentity,
    environment_identities_match,
    manifest_path,
    require_dependency_manifest,
)
from cascade.workspace.integration_worktree import locate_trunk

_BOOTSTRAP_DIR = "_dependency_bootstrap"
_SCHEMA_VERSION = 1


class DependencyBootstrapError(ValueError):
    """A bootstrap record or state transition is invalid."""


class StaleBootstrapRevision(DependencyBootstrapError):
    """The writer did not base its update on the current bootstrap revision."""


class BootstrapState(StrEnum):
    UNCHECKED = "unchecked"
    AWAITING_AUTHORIZATION = "awaiting_authorization"
    CHECKING = "checking"
    DEPENDENCY_BLOCKED = "dependency_blocked"
    READY = "ready"


class FeasibilityOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class BootstrapLimits:
    timeout_seconds: int
    max_attempts: int
    max_output_bytes: int
    memory_bytes: int | None = None

    def __post_init__(self) -> None:
        for name in ("timeout_seconds", "max_attempts", "max_output_bytes"):
            _positive_int(getattr(self, name), f"limits.{name}")
        if self.memory_bytes is not None:
            _positive_int(self.memory_bytes, "limits.memory_bytes")

    def to_dict(self) -> dict[str, int | None]:
        return {
            "timeout_seconds": self.timeout_seconds,
            "max_attempts": self.max_attempts,
            "max_output_bytes": self.max_output_bytes,
            "memory_bytes": self.memory_bytes,
        }

    @classmethod
    def from_dict(cls, raw: object) -> BootstrapLimits:
        data = _mapping(raw, "limits")
        _keys(
            data,
            {"timeout_seconds", "max_attempts", "max_output_bytes", "memory_bytes"},
            "limits",
        )
        memory = data.get("memory_bytes")
        return cls(
            timeout_seconds=_positive_int(
                data.get("timeout_seconds"), "limits.timeout_seconds"
            ),
            max_attempts=_positive_int(data.get("max_attempts"), "limits.max_attempts"),
            max_output_bytes=_positive_int(
                data.get("max_output_bytes"), "limits.max_output_bytes"
            ),
            memory_bytes=(
                None if memory is None else _positive_int(memory, "limits.memory_bytes")
            ),
        )


@dataclass(frozen=True, slots=True)
class BootstrapEntryScope:
    dependency_id: str
    source: str
    integrity_reference: str
    setup_operation: str
    check_operation: str
    paths: tuple[str, ...]
    destination: str
    cleanup: str

    def __post_init__(self) -> None:
        for name in (
            "dependency_id",
            "source",
            "integrity_reference",
            "setup_operation",
            "check_operation",
            "destination",
            "cleanup",
        ):
            _text(getattr(self, name), f"entry.{name}")
        _texts(self.paths, "entry.paths")
        if not self.paths:
            raise DependencyBootstrapError(
                "entry.paths must identify at least one bounded path"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "dependency_id": self.dependency_id,
            "source": self.source,
            "integrity_reference": self.integrity_reference,
            "setup_operation": self.setup_operation,
            "check_operation": self.check_operation,
            "paths": list(self.paths),
            "destination": self.destination,
            "cleanup": self.cleanup,
        }

    @classmethod
    def from_dict(cls, raw: object) -> BootstrapEntryScope:
        data = _mapping(raw, "entry")
        _keys(
            data,
            {
                "dependency_id",
                "source",
                "integrity_reference",
                "setup_operation",
                "check_operation",
                "paths",
                "destination",
                "cleanup",
            },
            "entry",
        )
        return cls(
            dependency_id=_text(data.get("dependency_id"), "entry.dependency_id"),
            source=_text(data.get("source"), "entry.source"),
            integrity_reference=_text(
                data.get("integrity_reference"), "entry.integrity_reference"
            ),
            setup_operation=_text(data.get("setup_operation"), "entry.setup_operation"),
            check_operation=_text(data.get("check_operation"), "entry.check_operation"),
            paths=_string_list(data.get("paths"), "entry.paths"),
            destination=_text(data.get("destination"), "entry.destination"),
            cleanup=_text(data.get("cleanup"), "entry.cleanup"),
        )


@dataclass(frozen=True, slots=True)
class FeasibilityArtifact:
    artifact_id: str
    operation: str
    target_environment: EnvironmentIdentity
    input_paths: tuple[str, ...]
    output_paths: tuple[str, ...]
    cleanup: str

    def __post_init__(self) -> None:
        for name in ("artifact_id", "operation", "cleanup"):
            _text(getattr(self, name), f"artifact.{name}")
        if not isinstance(self.target_environment, EnvironmentIdentity):
            raise DependencyBootstrapError(
                "artifact.target_environment must be an EnvironmentIdentity"
            )
        if not self.target_environment.is_fully_specified:
            raise DependencyBootstrapError(
                "artifact.target_environment must be fully specified"
            )
        _texts(self.input_paths, "artifact.input_paths")
        _texts(self.output_paths, "artifact.output_paths")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "operation": self.operation,
            "target_environment": self.target_environment.to_dict(),
            "input_paths": list(self.input_paths),
            "output_paths": list(self.output_paths),
            "cleanup": self.cleanup,
        }

    @classmethod
    def from_dict(cls, raw: object) -> FeasibilityArtifact:
        data = _mapping(raw, "artifact")
        _keys(
            data,
            {
                "artifact_id",
                "operation",
                "target_environment",
                "input_paths",
                "output_paths",
                "cleanup",
            },
            "artifact",
        )
        return cls(
            artifact_id=_text(data.get("artifact_id"), "artifact.artifact_id"),
            operation=_text(data.get("operation"), "artifact.operation"),
            target_environment=EnvironmentIdentity.from_dict(
                data.get("target_environment"), field="artifact.target_environment"
            ),
            input_paths=_string_list(data.get("input_paths"), "artifact.input_paths"),
            output_paths=_string_list(
                data.get("output_paths"), "artifact.output_paths"
            ),
            cleanup=_text(data.get("cleanup"), "artifact.cleanup"),
        )


@dataclass(frozen=True, slots=True)
class BootstrapScope:
    manifest_revision: int
    entries: tuple[BootstrapEntryScope, ...]
    feasibility_artifacts: tuple[FeasibilityArtifact, ...]
    limits: BootstrapLimits

    def __post_init__(self) -> None:
        _positive_int(self.manifest_revision, "scope.manifest_revision")
        if not isinstance(self.limits, BootstrapLimits):
            raise DependencyBootstrapError("scope.limits must be BootstrapLimits")
        if not isinstance(self.entries, tuple) or not all(
            isinstance(row, BootstrapEntryScope) for row in self.entries
        ):
            raise DependencyBootstrapError(
                "scope.entries must be bootstrap entry scopes"
            )
        if not isinstance(self.feasibility_artifacts, tuple) or not all(
            isinstance(row, FeasibilityArtifact) for row in self.feasibility_artifacts
        ):
            raise DependencyBootstrapError(
                "scope.feasibility_artifacts must be feasibility artifacts"
            )
        _unique((row.dependency_id for row in self.entries), "scope dependency IDs")
        _unique(
            (row.artifact_id for row in self.feasibility_artifacts),
            "feasibility artifact IDs",
        )

    @property
    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.to_dict(), sort_keys=True, separators=(",", ":")
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "manifest_revision": self.manifest_revision,
            "entries": [row.to_dict() for row in self.entries],
            "feasibility_artifacts": [
                row.to_dict() for row in self.feasibility_artifacts
            ],
            "limits": self.limits.to_dict(),
        }

    @classmethod
    def from_dict(cls, raw: object) -> BootstrapScope:
        data = _mapping(raw, "scope")
        _keys(
            data,
            {"manifest_revision", "entries", "feasibility_artifacts", "limits"},
            "scope",
        )
        return cls(
            manifest_revision=_positive_int(
                data.get("manifest_revision"), "scope.manifest_revision"
            ),
            entries=tuple(
                BootstrapEntryScope.from_dict(row)
                for row in _list(data.get("entries"), "scope.entries")
            ),
            feasibility_artifacts=tuple(
                FeasibilityArtifact.from_dict(row)
                for row in _list(
                    data.get("feasibility_artifacts"), "scope.feasibility_artifacts"
                )
            ),
            limits=BootstrapLimits.from_dict(data.get("limits")),
        )


@dataclass(frozen=True, slots=True)
class FeasibilityAuthorization:
    authorization_id: str
    scope_fingerprint: str
    artifact_ids: tuple[str, ...]
    actor: str
    authorized_at: datetime

    def __post_init__(self) -> None:
        for name in ("authorization_id", "scope_fingerprint", "actor"):
            _text(getattr(self, name), f"authorization.{name}")
        _texts(self.artifact_ids, "authorization.artifact_ids")
        _unique(self.artifact_ids, "authorized artifact IDs")
        _aware(self.authorized_at, "authorization.authorized_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "authorization_id": self.authorization_id,
            "scope_fingerprint": self.scope_fingerprint,
            "artifact_ids": list(self.artifact_ids),
            "actor": self.actor,
            "authorized_at": _timestamp(self.authorized_at),
        }

    @classmethod
    def from_dict(cls, raw: object) -> FeasibilityAuthorization:
        data = _mapping(raw, "authorization")
        _keys(
            data,
            {
                "authorization_id",
                "scope_fingerprint",
                "artifact_ids",
                "actor",
                "authorized_at",
            },
            "authorization",
        )
        return cls(
            authorization_id=_text(
                data.get("authorization_id"), "authorization.authorization_id"
            ),
            scope_fingerprint=_text(
                data.get("scope_fingerprint"), "authorization.scope_fingerprint"
            ),
            artifact_ids=_string_list(
                data.get("artifact_ids"), "authorization.artifact_ids"
            ),
            actor=_text(data.get("actor"), "authorization.actor"),
            authorized_at=_datetime(
                data.get("authorized_at"), "authorization.authorized_at"
            ),
        )


@dataclass(frozen=True, slots=True)
class FeasibilityResult:
    artifact_id: str
    authorization_id: str
    checked_at: datetime
    environment: EnvironmentIdentity
    outcome: FeasibilityOutcome
    redacted_output: str

    def __post_init__(self) -> None:
        _text(self.artifact_id, "result.artifact_id")
        _text(self.authorization_id, "result.authorization_id")
        _aware(self.checked_at, "result.checked_at")
        if not isinstance(self.environment, EnvironmentIdentity):
            raise DependencyBootstrapError(
                "result.environment must be an EnvironmentIdentity"
            )
        if not isinstance(self.outcome, FeasibilityOutcome):
            raise DependencyBootstrapError(
                "result.outcome must be a FeasibilityOutcome"
            )
        _text(self.redacted_output, "result.redacted_output", allow_empty=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "authorization_id": self.authorization_id,
            "checked_at": _timestamp(self.checked_at),
            "environment": self.environment.to_dict(),
            "outcome": self.outcome.value,
            "redacted_output": self.redacted_output,
        }

    @classmethod
    def from_dict(cls, raw: object) -> FeasibilityResult:
        data = _mapping(raw, "result")
        _keys(
            data,
            {
                "artifact_id",
                "authorization_id",
                "checked_at",
                "environment",
                "outcome",
                "redacted_output",
            },
            "result",
        )
        try:
            outcome = FeasibilityOutcome(data.get("outcome"))
        except (TypeError, ValueError) as exc:
            raise DependencyBootstrapError("result.outcome is invalid") from exc
        return cls(
            artifact_id=_text(data.get("artifact_id"), "result.artifact_id"),
            authorization_id=_text(
                data.get("authorization_id"), "result.authorization_id"
            ),
            checked_at=_datetime(data.get("checked_at"), "result.checked_at"),
            environment=EnvironmentIdentity.from_dict(
                data.get("environment"), field="result.environment"
            ),
            outcome=outcome,
            redacted_output=_text(
                data.get("redacted_output"), "result.redacted_output", allow_empty=True
            ),
        )


@dataclass(frozen=True, slots=True)
class BootstrapBlocker:
    dependency_id: str | None
    artifact_id: str | None
    actor: str
    last_checked_at: datetime | None
    failed_operation: str
    environment: str
    redacted_output: str
    investigation_steps: str | None
    install_steps: str | None
    expected_verification: str
    cleanup: str
    ping_action: str

    def __post_init__(self) -> None:
        if self.dependency_id is None and self.artifact_id is None:
            raise DependencyBootstrapError(
                "a blocker must identify a dependency or feasibility artifact"
            )
        for name in (
            "actor",
            "failed_operation",
            "environment",
            "expected_verification",
            "cleanup",
            "ping_action",
        ):
            _text(getattr(self, name), f"blocker.{name}")
        _text(self.redacted_output, "blocker.redacted_output", allow_empty=True)
        for name in (
            "dependency_id",
            "artifact_id",
            "investigation_steps",
            "install_steps",
        ):
            value = getattr(self, name)
            if value is not None:
                _text(value, f"blocker.{name}")
        if self.last_checked_at is not None:
            _aware(self.last_checked_at, "blocker.last_checked_at")

    def to_dict(self) -> dict[str, object]:
        return {
            "dependency_id": self.dependency_id,
            "artifact_id": self.artifact_id,
            "actor": self.actor,
            "last_checked_at": None
            if self.last_checked_at is None
            else _timestamp(self.last_checked_at),
            "failed_operation": self.failed_operation,
            "environment": self.environment,
            "redacted_output": self.redacted_output,
            "investigation_steps": self.investigation_steps,
            "install_steps": self.install_steps,
            "expected_verification": self.expected_verification,
            "cleanup": self.cleanup,
            "ping_action": self.ping_action,
        }

    @classmethod
    def from_dict(cls, raw: object) -> BootstrapBlocker:
        data = _mapping(raw, "blocker")
        fields = {
            "dependency_id",
            "artifact_id",
            "actor",
            "last_checked_at",
            "failed_operation",
            "environment",
            "redacted_output",
            "investigation_steps",
            "install_steps",
            "expected_verification",
            "cleanup",
            "ping_action",
        }
        _keys(data, fields, "blocker")
        return cls(
            dependency_id=_optional_text(
                data.get("dependency_id"), "blocker.dependency_id"
            ),
            artifact_id=_optional_text(data.get("artifact_id"), "blocker.artifact_id"),
            actor=_text(data.get("actor"), "blocker.actor"),
            last_checked_at=None
            if data.get("last_checked_at") is None
            else _datetime(data.get("last_checked_at"), "blocker.last_checked_at"),
            failed_operation=_text(
                data.get("failed_operation"), "blocker.failed_operation"
            ),
            environment=_text(data.get("environment"), "blocker.environment"),
            redacted_output=_text(
                data.get("redacted_output"), "blocker.redacted_output", allow_empty=True
            ),
            investigation_steps=_optional_text(
                data.get("investigation_steps"), "blocker.investigation_steps"
            ),
            install_steps=_optional_text(
                data.get("install_steps"), "blocker.install_steps"
            ),
            expected_verification=_text(
                data.get("expected_verification"), "blocker.expected_verification"
            ),
            cleanup=_text(data.get("cleanup"), "blocker.cleanup"),
            ping_action=_text(data.get("ping_action"), "blocker.ping_action"),
        )


@dataclass(frozen=True, slots=True)
class BootstrapSnapshot:
    revision: int
    recorded_at: datetime
    scope: BootstrapScope
    authorization: FeasibilityAuthorization | None
    checking: bool
    feasibility_results: tuple[FeasibilityResult, ...]
    blockers: tuple[BootstrapBlocker, ...]

    def __post_init__(self) -> None:
        _positive_int(self.revision, "snapshot.revision")
        _aware(self.recorded_at, "snapshot.recorded_at")
        if not isinstance(self.scope, BootstrapScope):
            raise DependencyBootstrapError("snapshot.scope must be a BootstrapScope")
        if self.authorization is not None and not isinstance(
            self.authorization, FeasibilityAuthorization
        ):
            raise DependencyBootstrapError(
                "snapshot.authorization must be a FeasibilityAuthorization or null"
            )
        if not isinstance(self.checking, bool):
            raise DependencyBootstrapError("snapshot.checking must be a boolean")
        if not isinstance(self.feasibility_results, tuple) or not all(
            isinstance(row, FeasibilityResult) for row in self.feasibility_results
        ):
            raise DependencyBootstrapError(
                "snapshot.feasibility_results must be feasibility results"
            )
        if not isinstance(self.blockers, tuple) or not all(
            isinstance(row, BootstrapBlocker) for row in self.blockers
        ):
            raise DependencyBootstrapError(
                "snapshot.blockers must be bootstrap blockers"
            )
        _unique(
            (row.artifact_id for row in self.feasibility_results),
            "feasibility result artifact IDs",
        )

    @property
    def state(self) -> BootstrapState:
        if self.authorization is None and self.scope.feasibility_artifacts:
            return BootstrapState.AWAITING_AUTHORIZATION
        if self.checking:
            return BootstrapState.CHECKING
        if self.blockers:
            return BootstrapState.DEPENDENCY_BLOCKED
        return BootstrapState.UNCHECKED

    def to_dict(self) -> dict[str, object]:
        return {
            "revision": self.revision,
            "recorded_at": _timestamp(self.recorded_at),
            "scope": self.scope.to_dict(),
            "authorization": None
            if self.authorization is None
            else self.authorization.to_dict(),
            "checking": self.checking,
            "feasibility_results": [row.to_dict() for row in self.feasibility_results],
            "blockers": [row.to_dict() for row in self.blockers],
        }

    @classmethod
    def from_dict(cls, raw: object) -> BootstrapSnapshot:
        data = _mapping(raw, "snapshot")
        _keys(
            data,
            {
                "revision",
                "recorded_at",
                "scope",
                "authorization",
                "checking",
                "feasibility_results",
                "blockers",
            },
            "snapshot",
        )
        authorization = data.get("authorization")
        checking = data.get("checking")
        if not isinstance(checking, bool):
            raise DependencyBootstrapError("snapshot.checking must be a boolean")
        return cls(
            revision=_positive_int(data.get("revision"), "snapshot.revision"),
            recorded_at=_datetime(data.get("recorded_at"), "snapshot.recorded_at"),
            scope=BootstrapScope.from_dict(data.get("scope")),
            authorization=None
            if authorization is None
            else FeasibilityAuthorization.from_dict(authorization),
            checking=checking,
            feasibility_results=tuple(
                FeasibilityResult.from_dict(row)
                for row in _list(
                    data.get("feasibility_results"), "snapshot.feasibility_results"
                )
            ),
            blockers=tuple(
                BootstrapBlocker.from_dict(row)
                for row in _list(data.get("blockers"), "snapshot.blockers")
            ),
        )


@dataclass(frozen=True, slots=True)
class BootstrapProjection:
    state: BootstrapState
    snapshot: BootstrapSnapshot
    blockers: tuple[str, ...]


def bootstrap_path(epic_id: str, *, root: Path) -> Path:
    manifests = manifest_path(epic_id, root=root).parent
    return manifests.parent / _BOOTSTRAP_DIR / f"{epic_id}.json"


def read_bootstrap_history(
    epic_id: str, *, root: Path
) -> tuple[BootstrapSnapshot, ...]:
    path = bootstrap_path(epic_id, root=root)
    if not path.is_file():
        return ()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DependencyBootstrapError(
            f"cannot read dependency bootstrap for {epic_id}"
        ) from exc
    data = _mapping(raw, "bootstrap store")
    _keys(data, {"version", "epic_id", "snapshots"}, "bootstrap store")
    if data.get("version") != _SCHEMA_VERSION or data.get("epic_id") != epic_id:
        raise DependencyBootstrapError(
            "dependency bootstrap identity or schema is invalid"
        )
    history = tuple(
        BootstrapSnapshot.from_dict(row)
        for row in _list(data.get("snapshots"), "bootstrap snapshots")
    )
    if tuple(row.revision for row in history) != tuple(range(1, len(history) + 1)):
        raise DependencyBootstrapError(
            "bootstrap revisions must be contiguous and append-only"
        )
    return history


def read_bootstrap(epic_id: str, *, root: Path) -> BootstrapSnapshot | None:
    history = read_bootstrap_history(epic_id, root=root)
    return history[-1] if history else None


def create_bootstrap(
    epic_id: str,
    scope: BootstrapScope,
    *,
    root: Path,
    expected_revision: int = 0,
    recorded_at: datetime | None = None,
) -> BootstrapSnapshot:
    manifest = require_dependency_manifest(epic_id, root=root)
    _validate_scope(scope, manifest)
    current = read_bootstrap(epic_id, root=root)
    if current is not None and current.scope == scope:
        if expected_revision != current.revision:
            raise StaleBootstrapRevision(
                f"stale bootstrap revision for {epic_id}: current is "
                f"{current.revision}, expected {expected_revision}"
            )
        return current
    snapshot = BootstrapSnapshot(
        revision=(current.revision + 1 if current else 1),
        recorded_at=recorded_at or datetime.now(timezone.utc),
        scope=scope,
        authorization=None,
        checking=False,
        feasibility_results=(),
        blockers=(),
    )
    return _append(epic_id, snapshot, root=root, expected_revision=expected_revision)


def authorize_feasibility(
    epic_id: str,
    artifact_ids: Sequence[str],
    *,
    authorizer: AuthenticatedHuman,
    root: Path,
    expected_revision: int,
    authorized_at: datetime | None = None,
) -> BootstrapSnapshot:
    current = _require_bootstrap(epic_id, root=root)
    if not isinstance(authorizer, AuthenticatedHuman):
        raise DependencyBootstrapError(
            "an authenticated human must authorize feasibility scope"
        )
    ids = tuple(_text(row, "artifact_id") for row in artifact_ids)
    _unique(ids, "authorized artifact IDs")
    permitted = {row.artifact_id for row in current.scope.feasibility_artifacts}
    if set(ids) != permitted:
        raise DependencyBootstrapError(
            "authorization must bind every and only the current scope's feasibility artifacts"
        )
    authorization = FeasibilityAuthorization(
        authorization_id=f"feasibility_{uuid.uuid4().hex}",
        scope_fingerprint=current.scope.fingerprint,
        artifact_ids=ids,
        actor=authorizer.subject,
        authorized_at=authorized_at or datetime.now(timezone.utc),
    )
    return _replace(
        current,
        authorization=authorization,
        checking=False,
        feasibility_results=(),
        blockers=(),
        epic_id=epic_id,
        root=root,
        expected_revision=expected_revision,
    )


def set_bootstrap_checking(
    epic_id: str, *, root: Path, expected_revision: int
) -> BootstrapSnapshot:
    current = _require_bootstrap(epic_id, root=root)
    if current.scope.feasibility_artifacts and not _authorization_is_current(current):
        raise DependencyBootstrapError(
            "feasibility checking requires current human scope authorization"
        )
    return _replace(
        current,
        checking=True,
        epic_id=epic_id,
        root=root,
        expected_revision=expected_revision,
    )


def record_feasibility_result(
    epic_id: str,
    artifact_id: str,
    *,
    environment: EnvironmentIdentity,
    outcome: FeasibilityOutcome,
    redacted_output: str,
    root: Path,
    expected_revision: int,
    checked_at: datetime | None = None,
) -> BootstrapSnapshot:
    current = _require_bootstrap(epic_id, root=root)
    if not _authorization_is_current(current):
        raise DependencyBootstrapError(
            "feasibility result requires current human scope authorization"
        )
    authorization = current.authorization
    assert authorization is not None
    artifact_id = _text(artifact_id, "artifact_id")
    if artifact_id not in authorization.artifact_ids:
        raise DependencyBootstrapError(
            "feasibility artifact is not authorized by the current scope"
        )
    artifact = next(
        row
        for row in current.scope.feasibility_artifacts
        if row.artifact_id == artifact_id
    )
    if not environment_identities_match(artifact.target_environment, environment):
        raise DependencyBootstrapError(
            "feasibility result environment does not match its authorized scope"
        )
    result = FeasibilityResult(
        artifact_id=artifact_id,
        authorization_id=authorization.authorization_id,
        checked_at=checked_at or datetime.now(timezone.utc),
        environment=environment,
        outcome=FeasibilityOutcome(outcome),
        redacted_output=_text(redacted_output, "redacted_output", allow_empty=True),
    )
    results = tuple(
        row for row in current.feasibility_results if row.artifact_id != artifact_id
    ) + (result,)
    return _replace(
        current,
        checking=False,
        feasibility_results=results,
        epic_id=epic_id,
        root=root,
        expected_revision=expected_revision,
    )


def record_bootstrap_blockers(
    epic_id: str,
    blockers: Sequence[BootstrapBlocker],
    *,
    root: Path,
    expected_revision: int,
) -> BootstrapSnapshot:
    current = _require_bootstrap(epic_id, root=root)
    rows = tuple(blockers)
    if not rows or not all(isinstance(row, BootstrapBlocker) for row in rows):
        raise DependencyBootstrapError(
            "at least one actionable bootstrap blocker is required"
        )
    return _replace(
        current,
        checking=False,
        blockers=rows,
        epic_id=epic_id,
        root=root,
        expected_revision=expected_revision,
    )


def project_bootstrap(epic_id: str, *, root: Path) -> BootstrapProjection:
    current = _require_bootstrap(epic_id, root=root)
    manifest = require_dependency_manifest(epic_id, root=root)
    reasons: list[str] = []
    if current.scope.manifest_revision != manifest.revision:
        reasons.append("stale_manifest_scope")
    if current.scope.feasibility_artifacts and not _authorization_is_current(current):
        return BootstrapProjection(
            BootstrapState.AWAITING_AUTHORIZATION,
            current,
            ("feasibility_authorization_required", *reasons),
        )
    if current.checking:
        return BootstrapProjection(BootstrapState.CHECKING, current, tuple(reasons))
    reasons.extend(
        f"recorded_blocker:{index}" for index, _ in enumerate(current.blockers, 1)
    )
    results = {row.artifact_id: row for row in current.feasibility_results}
    for artifact in current.scope.feasibility_artifacts:
        result = results.get(artifact.artifact_id)
        if result is None:
            reasons.append(f"missing_feasibility_result:{artifact.artifact_id}")
        elif result.outcome is not FeasibilityOutcome.SUCCEEDED:
            reasons.append(f"failed_feasibility:{artifact.artifact_id}")
    readiness = compute_dependency_readiness(epic_id, root=root)
    reasons.extend(
        f"dependency:{row.dependency_id or 'manifest'}:{row.reason}"
        for row in readiness.blockers
    )
    state = BootstrapState.READY if not reasons else BootstrapState.DEPENDENCY_BLOCKED
    return BootstrapProjection(state, current, tuple(reasons))


def _validate_scope(
    scope: BootstrapScope, manifest: DependencyManifestSnapshot
) -> None:
    if not isinstance(scope, BootstrapScope):
        raise DependencyBootstrapError("scope must be a BootstrapScope")
    if scope.manifest_revision != manifest.revision:
        raise DependencyBootstrapError(
            "bootstrap scope must bind the current manifest revision"
        )
    entries = {row.dependency_id: row for row in scope.entries}
    if set(entries) != {row.dependency_id for row in manifest.dependencies}:
        raise DependencyBootstrapError(
            "bootstrap scope dependency IDs must exactly match the manifest"
        )
    for dependency in manifest.dependencies:
        scoped = entries[dependency.dependency_id]
        expected = (
            dependency.source,
            dependency.integrity_reference,
            dependency.operation,
            dependency.verification_recipe,
            dependency.install_destination,
            dependency.cleanup_plan,
        )
        actual = (
            scoped.source,
            scoped.integrity_reference,
            scoped.setup_operation,
            scoped.check_operation,
            scoped.destination,
            scoped.cleanup,
        )
        if actual != expected:
            raise DependencyBootstrapError(
                f"bootstrap entry {dependency.dependency_id} does not exactly bind the current manifest"
            )
    artifact_ids = {row.artifact_id for row in scope.feasibility_artifacts}
    required = {
        requirement
        for row in manifest.dependencies
        for requirement in row.feasibility_proof_requirements
    }
    if not required.issubset(artifact_ids):
        missing = ", ".join(sorted(required - artifact_ids))
        raise DependencyBootstrapError(
            f"required feasibility artifacts are outside bootstrap scope: {missing}"
        )


def _authorization_is_current(snapshot: BootstrapSnapshot) -> bool:
    authorization = snapshot.authorization
    return (
        authorization is not None
        and authorization.scope_fingerprint == snapshot.scope.fingerprint
        and set(authorization.artifact_ids)
        == {row.artifact_id for row in snapshot.scope.feasibility_artifacts}
    )


def _replace(
    current: BootstrapSnapshot,
    *,
    epic_id: str,
    root: Path,
    expected_revision: int,
    **changes: object,
) -> BootstrapSnapshot:
    values: dict[str, object] = {
        "revision": current.revision + 1,
        "recorded_at": datetime.now(timezone.utc),
        "scope": current.scope,
        "authorization": current.authorization,
        "checking": current.checking,
        "feasibility_results": current.feasibility_results,
        "blockers": current.blockers,
    }
    values.update(changes)
    return _append(
        epic_id,
        BootstrapSnapshot(**values),
        root=root,
        expected_revision=expected_revision,
    )  # type: ignore[arg-type]


def _require_bootstrap(epic_id: str, *, root: Path) -> BootstrapSnapshot:
    snapshot = read_bootstrap(epic_id, root=root)
    if snapshot is None:
        raise DependencyBootstrapError(f"{epic_id} has no bootstrap record")
    return snapshot


def _append(
    epic_id: str, snapshot: BootstrapSnapshot, *, root: Path, expected_revision: int
) -> BootstrapSnapshot:
    _aware(snapshot.recorded_at, "snapshot.recorded_at")
    path = bootstrap_path(epic_id, root=root)
    repo = path.parents[4]
    doc = read_doc(epic_id, root=repo)
    if doc.meta.tier != "epic" or doc.meta.path.parent.name != "2_active":
        raise DependencyBootstrapError(
            "bootstrap records can only be written for active epics"
        )
    with process_lock:
        history = read_bootstrap_history(epic_id, root=repo)
        revision = history[-1].revision if history else 0
        if revision != expected_revision:
            raise StaleBootstrapRevision(
                f"stale bootstrap revision for {epic_id}: current is {revision}, expected {expected_revision}"
            )
        if snapshot.revision != revision + 1:
            raise DependencyBootstrapError(
                "bootstrap snapshot revision is not contiguous"
            )
        _write(path, epic_id, (*history, snapshot))
        if has_git(repo):
            from cascade.workspace.integration_worktree import (
                git_root_for_path,
                invalidate_merged_board,
            )

            commit_root = git_root_for_path(path)
            commit_paths(
                commit_root,
                [path],
                f"docs: record {epic_id} dependency bootstrap revision {snapshot.revision}",
            )
            invalidate_merged_board(locate_trunk(repo))
    return snapshot


def _write(path: Path, epic_id: str, snapshots: Sequence[BootstrapSnapshot]) -> None:
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


def _mapping(raw: object, field: str) -> Mapping[str, object]:
    if not isinstance(raw, Mapping) or not all(isinstance(key, str) for key in raw):
        raise DependencyBootstrapError(f"{field} must be an object")
    return raw


def _keys(data: Mapping[str, object], required: set[str], field: str) -> None:
    if set(data) != required:
        raise DependencyBootstrapError(f"{field} has invalid fields")


def _list(raw: object, field: str) -> list[object]:
    if not isinstance(raw, list):
        raise DependencyBootstrapError(f"{field} must be a list")
    return raw


def _string_list(raw: object, field: str) -> tuple[str, ...]:
    return tuple(_text(row, field) for row in _list(raw, field))


def _texts(raw: object, field: str) -> None:
    if not isinstance(raw, tuple) or not all(
        isinstance(row, str) and row.strip() for row in raw
    ):
        raise DependencyBootstrapError(f"{field} must be a tuple of non-blank strings")


def _unique(values: Sequence[str] | object, field: str) -> None:
    rows = tuple(values)  # type: ignore[arg-type]
    if len(rows) != len(set(rows)):
        raise DependencyBootstrapError(f"{field} must be unique")


def _text(raw: object, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(raw, str) or (not allow_empty and not raw.strip()):
        raise DependencyBootstrapError(
            f"{field} must be a {'string' if allow_empty else 'non-blank string'}"
        )
    return raw


def _optional_text(raw: object, field: str) -> str | None:
    return None if raw is None else _text(raw, field)


def _positive_int(raw: object, field: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int) or raw < 1:
        raise DependencyBootstrapError(f"{field} must be a positive integer")
    return raw


def _aware(raw: object, field: str) -> datetime:
    if not isinstance(raw, datetime) or raw.tzinfo is None:
        raise DependencyBootstrapError(f"{field} must be timezone-aware")
    return raw


def _timestamp(value: datetime) -> str:
    return _aware(value, "timestamp").astimezone(timezone.utc).isoformat()


def _datetime(raw: object, field: str) -> datetime:
    if not isinstance(raw, str):
        raise DependencyBootstrapError(f"{field} must be a timestamp")
    try:
        return _aware(datetime.fromisoformat(raw.replace("Z", "+00:00")), field)
    except ValueError as exc:
        raise DependencyBootstrapError(f"{field} is invalid") from exc
