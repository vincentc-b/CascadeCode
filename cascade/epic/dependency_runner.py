"""Bounded execution of reviewed dependency and feasibility operations.

The runner is intentionally provider-neutral.  A provider supplies a
``BoundedOperationExecutor`` which must enforce the request's process/container
limits and report the environment it actually observed.  This module owns the
trusted orchestration boundary: it rechecks scope and authority, bounds and
redacts evidence, and persists outcomes through the slice-A contracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import urlsplit

from cascade.epic.dependency_bootstrap import (
    BootstrapBlocker,
    BootstrapLimits,
    BootstrapSnapshot,
    FeasibilityArtifact,
    FeasibilityOutcome,
    clear_bootstrap_blockers,
    read_bootstrap,
    record_bootstrap_blockers,
    record_feasibility_result,
    set_bootstrap_checking,
)
from cascade.epic.dependency_evidence import (
    DEFAULT_DEPENDENCY_EXECUTION_POLICY,
    CheckAdmission,
    CheckCompletion,
    CheckOperationKind,
    CheckResult,
    DependencyExecutionPolicy,
    admit_dependency_check,
    dispatch_dependency_mutation,
    entry_evidence_revision,
    read_dependency_check_history,
    record_trusted_dependency_check_completion,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    EnvironmentIdentity,
    environment_identities_match,
    require_dependency_manifest,
)


class DependencyRunnerError(ValueError):
    """The requested operation cannot be safely admitted or executed."""


class OperationFailure(StrEnum):
    OFFLINE_SOURCE = "offline_source"
    CHECKSUM_MISMATCH = "checksum_mismatch"
    WRONG_ENVIRONMENT = "wrong_environment"
    PROMPT_UNSUPPORTED = "prompt_unsupported"
    TIMEOUT = "timeout"
    COMMAND_FAILED = "command_failed"
    CLEANUP_FAILED = "cleanup_failed"
    VERSION_MISMATCH = "version_mismatch"


@dataclass(frozen=True, slots=True)
class OperationRequest:
    """Exact, reviewed operation passed to an environment-specific executor."""

    operation: str
    operation_kind: CheckOperationKind | None
    target_environment: EnvironmentIdentity
    source: str | None
    selected_version: str | None
    integrity_reference: str | None
    allowed_paths: tuple[str, ...]
    destination: str | None
    cleanup: str
    limits: BootstrapLimits


@dataclass(frozen=True, slots=True)
class OperationObservation:
    """Trusted observation returned by a bounded provider implementation."""

    actual_environment: EnvironmentIdentity
    exit_code: int
    output: str
    selected_version: str | None = None
    integrity_reference: str | None = None
    failure: OperationFailure | None = None
    cleanup_complete: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.actual_environment, EnvironmentIdentity):
            raise DependencyRunnerError(
                "executor must report a trusted actual environment identity"
            )
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise DependencyRunnerError("executor exit_code must be an integer")
        if not isinstance(self.output, str):
            raise DependencyRunnerError("executor output must be text")
        if self.failure is not None and not isinstance(self.failure, OperationFailure):
            raise DependencyRunnerError("executor failure classification is invalid")
        if not isinstance(self.cleanup_complete, bool):
            raise DependencyRunnerError("executor cleanup status must be a boolean")


class BoundedOperationExecutor(Protocol):
    """Provider contract; implementations enforce timeout and resource limits."""

    def execute(self, request: OperationRequest) -> OperationObservation: ...


@dataclass(frozen=True, slots=True)
class ActionableRunnerBlocker:
    code: OperationFailure
    failed_operation: str
    actual_environment: EnvironmentIdentity
    redacted_output: str
    next_action: str


@dataclass(frozen=True, slots=True)
class DependencyRunResult:
    admission: CheckAdmission
    completion: CheckCompletion
    blocker: ActionableRunnerBlocker | None


@dataclass(frozen=True, slots=True)
class FeasibilityRunResult:
    snapshot: BootstrapSnapshot
    blocker: ActionableRunnerBlocker | None


def run_dependency_operation(
    epic_id: str,
    dependency_id: str,
    *,
    operation_kind: CheckOperationKind,
    executor: BoundedOperationExecutor,
    root: Path,
    approval_reference: str | None = None,
    bootstrap_revision: int | None = None,
    execution_policy: DependencyExecutionPolicy = DEFAULT_DEPENDENCY_EXECUTION_POLICY,
    attempt_id: str | None = None,
) -> DependencyRunResult:
    """Run one exact setup/check operation and append its bounded evidence."""

    bootstrap, entry, scoped = _dependency_context(epic_id, dependency_id, root=root)
    kind = _operation_kind(operation_kind)
    operation = (
        scoped.check_operation
        if kind is CheckOperationKind.READ_ONLY
        else scoped.setup_operation
    )
    existing_completion = _completion_for_attempt(epic_id, attempt_id, root=root)
    if existing_completion is None:
        _require_attempt_available(
            epic_id,
            entry,
            kind,
            operation,
            bootstrap.scope.limits,
            root=root,
            attempt_id=attempt_id,
        )
    _require_executor(executor)
    admission = admit_dependency_check(
        epic_id,
        dependency_id,
        root=root,
        operation_kind=kind,
        exact_operation=operation,
        approval_reference=approval_reference,
        bootstrap_revision=bootstrap_revision,
        execution_policy=execution_policy,
        attempt_id=attempt_id,
    )
    if existing_completion is not None:
        blocker = None
        if existing_completion.result is CheckResult.FAILED:
            blocker = _blocker(
                OperationFailure.COMMAND_FAILED,
                operation,
                existing_completion.actual_environment,
                existing_completion.redacted_output,
            )
        return DependencyRunResult(admission, existing_completion, blocker)
    request = OperationRequest(
        operation=operation,
        operation_kind=kind,
        target_environment=entry.target_environment,
        source=entry.source,
        selected_version=entry.version,
        integrity_reference=entry.digest,
        allowed_paths=scoped.paths,
        destination=scoped.destination,
        cleanup=scoped.cleanup,
        limits=bootstrap.scope.limits,
    )
    if kind is CheckOperationKind.READ_ONLY:
        observation = executor.execute(request)
    else:
        # This is the final authority recheck immediately before any mutation,
        # including an executor operation which can implicitly pull an image.
        observation = dispatch_dependency_mutation(
            epic_id,
            admission.attempt_id,
            lambda: executor.execute(request),
            root=root,
            execution_policy=execution_policy,
        )
    observation = _observation(observation)
    output = _redacted_bounded_output(
        observation.output, bootstrap.scope.limits.max_output_bytes
    )
    failure = _dependency_failure(entry, observation)
    completion = record_trusted_dependency_check_completion(
        epic_id,
        admission.attempt_id,
        root=root,
        actual_environment=observation.actual_environment,
        result=CheckResult.SUCCEEDED if failure is None else CheckResult.FAILED,
        redacted_output=output,
        selected_version=observation.selected_version or "unreported",
        integrity_reference=observation.integrity_reference or "unreported",
        lock_references=entry.lock_references,
        execution_policy=execution_policy,
    )
    blocker = (
        None
        if failure is None
        else _blocker(failure, operation, observation.actual_environment, output)
    )
    return DependencyRunResult(admission, completion, blocker)


def run_feasibility_proof(
    epic_id: str,
    artifact_id: str,
    *,
    executor: BoundedOperationExecutor,
    root: Path,
) -> FeasibilityRunResult:
    """Run a separately authorized feasibility artifact in its exact environment."""

    bootstrap = _bootstrap(epic_id, root=root)
    artifact = next(
        (
            row
            for row in bootstrap.scope.feasibility_artifacts
            if row.artifact_id == artifact_id
        ),
        None,
    )
    if artifact is None:
        raise DependencyRunnerError("feasibility artifact is outside reviewed scope")
    authorization = bootstrap.authorization
    if (
        authorization is None
        or authorization.scope_fingerprint != bootstrap.scope.fingerprint
        or artifact_id not in authorization.artifact_ids
    ):
        raise DependencyRunnerError(
            "feasibility proof requires current independent human authorization"
        )
    attempts = sum(
        snapshot.checking for snapshot in _bootstrap_history(epic_id, root=root)
    )
    if attempts >= bootstrap.scope.limits.max_attempts:
        raise DependencyRunnerError("feasibility attempt limit reached")
    _require_executor(executor)
    checking = set_bootstrap_checking(
        epic_id, root=root, expected_revision=bootstrap.revision
    )
    request = OperationRequest(
        operation=artifact.operation,
        operation_kind=None,
        target_environment=artifact.target_environment,
        source=None,
        selected_version=None,
        integrity_reference=None,
        allowed_paths=(*artifact.input_paths, *artifact.output_paths),
        destination=None,
        cleanup=artifact.cleanup,
        limits=checking.scope.limits,
    )
    observation = _observation(executor.execute(request))
    output = _redacted_bounded_output(
        observation.output, checking.scope.limits.max_output_bytes
    )
    failure = _generic_failure(artifact.target_environment, observation)
    blocker = (
        None
        if failure is None
        else _blocker(
            failure, artifact.operation, observation.actual_environment, output
        )
    )
    if failure is OperationFailure.WRONG_ENVIRONMENT:
        # A mismatched observation is retained as blocker history, never as a
        # current result for the authorized target environment.
        retained = tuple(
            row for row in checking.blockers if row.artifact_id != artifact.artifact_id
        )
        snapshot = record_bootstrap_blockers(
            epic_id,
            (*retained, _bootstrap_blocker(artifact, blocker)),
            root=root,
            expected_revision=checking.revision,
        )
        return FeasibilityRunResult(snapshot, blocker)
    snapshot = record_feasibility_result(
        epic_id,
        artifact_id,
        environment=observation.actual_environment,
        outcome=(
            FeasibilityOutcome.SUCCEEDED
            if failure is None
            else FeasibilityOutcome.FAILED
        ),
        redacted_output=output,
        root=root,
        expected_revision=checking.revision,
    )
    if blocker is not None:
        retained = tuple(
            row for row in snapshot.blockers if row.artifact_id != artifact.artifact_id
        )
        snapshot = record_bootstrap_blockers(
            epic_id,
            (*retained, _bootstrap_blocker(artifact, blocker)),
            root=root,
            expected_revision=snapshot.revision,
        )
    elif any(row.artifact_id == artifact.artifact_id for row in snapshot.blockers):
        snapshot = clear_bootstrap_blockers(
            epic_id,
            artifact_id=artifact.artifact_id,
            root=root,
            expected_revision=snapshot.revision,
        )
    return FeasibilityRunResult(snapshot, blocker)


def _dependency_context(epic_id: str, dependency_id: str, *, root: Path):
    manifest = require_dependency_manifest(epic_id, root=root)
    bootstrap = _bootstrap(epic_id, root=root)
    if bootstrap.scope.manifest_revision != manifest.revision:
        raise DependencyRunnerError("bootstrap scope is stale for the current manifest")
    entry = next(
        (row for row in manifest.dependencies if row.dependency_id == dependency_id),
        None,
    )
    scoped = next(
        (row for row in bootstrap.scope.entries if row.dependency_id == dependency_id),
        None,
    )
    if entry is None or scoped is None:
        raise DependencyRunnerError("dependency is outside reviewed bootstrap scope")
    if (
        scoped.source != entry.source
        or scoped.integrity_reference != entry.integrity_reference
        or scoped.setup_operation != entry.operation
        or scoped.check_operation != entry.verification_recipe
        or scoped.destination != entry.install_destination
        or scoped.cleanup != entry.cleanup_plan
    ):
        raise DependencyRunnerError(
            "dependency operation no longer matches reviewed scope"
        )
    if scoped.destination not in scoped.paths:
        raise DependencyRunnerError("reviewed destination is outside allowed paths")
    for path in scoped.paths:
        _require_bounded_path(path)
    _require_pinned(entry)
    return bootstrap, entry, scoped


def _require_pinned(entry: DependencyEntry) -> None:
    moving = re.compile(r"(^|[/_.-])latest($|[/_.-])", re.IGNORECASE)
    if moving.search(entry.version) or moving.search(entry.source):
        raise DependencyRunnerError("moving latest references are not permitted")
    parsed = urlsplit(entry.source)
    if parsed.username is not None or parsed.password is not None:
        raise DependencyRunnerError("dependency sources must not embed credentials")
    integrity = entry.integrity_reference or entry.digest
    if moving.search(integrity) or ":" not in integrity:
        raise DependencyRunnerError("an immutable integrity reference is required")
    if entry.target_environment.kind.casefold() == "container" and not (
        entry.target_environment.container_digest or ""
    ).startswith("sha256:"):
        raise DependencyRunnerError("container execution requires an immutable digest")


def _require_bounded_path(value: str) -> None:
    path = PurePosixPath(value)
    if ".." in path.parts or value.strip() in {"", ".", "/"}:
        raise DependencyRunnerError("reviewed operation contains an unbounded path")


def _require_attempt_available(
    epic_id: str,
    entry: DependencyEntry,
    kind: CheckOperationKind,
    operation: str,
    limits: BootstrapLimits,
    *,
    root: Path,
    attempt_id: str | None = None,
) -> None:
    revision = entry_evidence_revision(entry)
    attempts = sum(
        isinstance(row, CheckAdmission)
        and row.dependency_id == entry.dependency_id
        and row.entry_revision == revision
        and row.operation_kind is kind
        and row.exact_operation == operation
        for row in read_dependency_check_history(epic_id, root=root)
    )
    existing_ids = {
        row.attempt_id
        for row in read_dependency_check_history(epic_id, root=root)
        if isinstance(row, CheckAdmission)
    }
    if attempt_id not in existing_ids and attempts >= limits.max_attempts:
        raise DependencyRunnerError("dependency attempt limit reached")


def _completion_for_attempt(
    epic_id: str, attempt_id: str | None, *, root: Path
) -> CheckCompletion | None:
    if attempt_id is None:
        return None
    return next(
        (
            row
            for row in read_dependency_check_history(epic_id, root=root)
            if isinstance(row, CheckCompletion) and row.attempt_id == attempt_id
        ),
        None,
    )


def _dependency_failure(
    entry: DependencyEntry, observation: OperationObservation
) -> OperationFailure | None:
    failure = _generic_failure(entry.target_environment, observation)
    if failure is not None:
        return failure
    if observation.selected_version not in (None, entry.version):
        return OperationFailure.VERSION_MISMATCH
    if observation.selected_version is None:
        return OperationFailure.VERSION_MISMATCH
    if observation.integrity_reference is None:
        return OperationFailure.CHECKSUM_MISMATCH
    if observation.integrity_reference != entry.digest:
        return OperationFailure.CHECKSUM_MISMATCH
    return None


def _generic_failure(
    target: EnvironmentIdentity, observation: OperationObservation
) -> OperationFailure | None:
    if not environment_identities_match(target, observation.actual_environment):
        return OperationFailure.WRONG_ENVIRONMENT
    if observation.failure is not None:
        return observation.failure
    if not observation.cleanup_complete:
        return OperationFailure.CLEANUP_FAILED
    if observation.exit_code != 0:
        return OperationFailure.COMMAND_FAILED
    return None


_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/-]+=*"),
    re.compile(r"(?i)\b(token|password|passwd|secret|api[_-]?key)\s*[:=]\s*[^\s,;]+"),
    re.compile(r"(?i)(https?://)[^/@\s:]+:[^/@\s]+@"),
)


def _redacted_bounded_output(output: str, max_bytes: int) -> str:
    redacted = output
    redacted = _SECRET_PATTERNS[0].sub(r"\1 [REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[1].sub(r"\1=[REDACTED]", redacted)
    redacted = _SECRET_PATTERNS[2].sub(r"\1[REDACTED]@", redacted)
    encoded = redacted.encode("utf-8")
    if len(encoded) <= max_bytes:
        return redacted
    suffix = b"\n[output truncated]"
    if max_bytes <= len(suffix):
        return suffix[:max_bytes].decode("utf-8", errors="ignore")
    available = max(0, max_bytes - len(suffix))
    return (encoded[:available] + suffix).decode("utf-8", errors="ignore")


def _blocker(
    failure: OperationFailure,
    operation: str,
    environment: EnvironmentIdentity,
    output: str,
) -> ActionableRunnerBlocker:
    actions = {
        OperationFailure.OFFLINE_SOURCE: "restore access to the pinned source and retry",
        OperationFailure.CHECKSUM_MISMATCH: "verify the authoritative digest before retrying",
        OperationFailure.WRONG_ENVIRONMENT: "run in the exact reviewed environment",
        OperationFailure.PROMPT_UNSUPPORTED: "provide a non-interactive recipe without credentials or license prompts",
        OperationFailure.TIMEOUT: "review the bounded recipe or authorize a revised timeout",
        OperationFailure.COMMAND_FAILED: "inspect the redacted output and correct the pinned recipe",
        OperationFailure.CLEANUP_FAILED: "complete the reviewed cleanup before retrying",
        OperationFailure.VERSION_MISMATCH: "select the exact reviewed version",
    }
    return ActionableRunnerBlocker(
        failure, operation, environment, output, actions[failure]
    )


def _bootstrap_blocker(
    artifact: FeasibilityArtifact, blocker: ActionableRunnerBlocker | None
) -> BootstrapBlocker:
    assert blocker is not None
    return BootstrapBlocker(
        dependency_id=None,
        artifact_id=artifact.artifact_id,
        actor="human",
        last_checked_at=None,
        failed_operation=artifact.operation,
        environment=str(blocker.actual_environment.to_dict()),
        redacted_output=blocker.redacted_output,
        investigation_steps=blocker.next_action,
        install_steps=None,
        expected_verification="operation exits successfully in the reviewed environment",
        cleanup=artifact.cleanup,
        ping_action="ping the team after resolving the blocker",
    )


def _bootstrap(epic_id: str, *, root: Path) -> BootstrapSnapshot:
    bootstrap = read_bootstrap(epic_id, root=root)
    if bootstrap is None:
        raise DependencyRunnerError(f"{epic_id} has no reviewed bootstrap scope")
    return bootstrap


def _bootstrap_history(epic_id: str, *, root: Path):
    from cascade.epic.dependency_bootstrap import read_bootstrap_history

    return read_bootstrap_history(epic_id, root=root)


def _operation_kind(value: CheckOperationKind) -> CheckOperationKind:
    try:
        return CheckOperationKind(value)
    except (TypeError, ValueError) as exc:
        raise DependencyRunnerError("operation kind is invalid") from exc


def _require_executor(executor: BoundedOperationExecutor) -> None:
    if not callable(getattr(executor, "execute", None)):
        raise DependencyRunnerError("executor must implement bounded execute(request)")


def _observation(value: OperationObservation) -> OperationObservation:
    if not isinstance(value, OperationObservation):
        raise DependencyRunnerError("executor returned an invalid observation")
    return value
