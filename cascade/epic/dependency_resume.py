"""Durable, deduplicated revalidation of blocked dependency bootstraps.

A human ping is only a stable request to inspect current state.  The request is
recorded in the existing lifecycle action journal, while dependency attempts
remain in the append-only evidence journal.  Planning is kicked off only after
the current manifest, scope, evidence, and separate feasibility projection all
agree that the bootstrap is ready.
"""

from __future__ import annotations

import hashlib
import json
import fcntl
import time
from contextlib import contextmanager
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    current_installation_approval,
    read_installation_approvals,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapBlocker,
    BootstrapState,
    clear_bootstrap_blockers,
    ensure_dependency_scope,
    project_bootstrap,
    read_bootstrap,
    record_bootstrap_blockers,
)
from cascade.epic.dependency_evidence import (
    DEFAULT_DEPENDENCY_EXECUTION_POLICY,
    CheckAdmission,
    CheckCompletion,
    CheckOperationKind,
    CheckResult,
    DependencyExecutionPolicy,
    project_current_dependency_evidence,
    read_dependency_check_history,
    record_trusted_dependency_check_completion,
)
from cascade.epic.dependency_manifests import require_dependency_manifest
from cascade.epic.dependency_runner import (
    BoundedOperationExecutor,
    DependencyRunResult,
    run_dependency_operation,
    run_feasibility_proof,
)
from cascade.epic.lifecycle_gate import LifecycleGate, lifecycle_gate
from cascade.task.action_recovery import (
    ActionContext,
    ActionFailure,
    ActionResult,
    create_or_load_action,
    resume_action,
)
from cascade.workspace.types import KickoffReason

_ACTION_KIND = "dependency_bootstrap_resume"


class DependencyResumeError(ValueError):
    """A resume request is malformed or conflicts with its durable identity."""


@dataclass(frozen=True, slots=True)
class DependencyResumeResult:
    action_id: str
    recovery_state: str
    ready: bool
    deduplicated: bool
    planning_resumed: bool
    blockers: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "recovery_state": self.recovery_state,
            "ready": self.ready,
            "deduplicated": self.deduplicated,
            "planning_resumed": self.planning_resumed,
            "blockers": list(self.blockers),
        }


@contextmanager
def _dependency_operation_lock(epic_id: str, *, root: Path):
    """Serialize team and UI execution without holding a metadata lock."""
    from cascade.epic.dependency_manifests import dependency_manifest_repository
    repo = dependency_manifest_repository(epic_id, root=root)
    home = repo / ".cascade" / "dependency_operation_locks"
    home.mkdir(parents=True, exist_ok=True)
    path = home / (hashlib.sha256(epic_id.encode()).hexdigest() + ".lock")
    with path.open("a") as handle:
        deadline = time.monotonic() + 1.0
        while True:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise DependencyResumeError("Dependency verification is already running; refresh its status shortly")
                time.sleep(0.05)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def resume_dependency_bootstrap(
    epic_id: str, request_id: str, *, executor: BoundedOperationExecutor,
    root: Path, **kwargs,
) -> DependencyResumeResult:
    """Serialize every team's or human's check/install/verify sequence per Epic."""
    with _dependency_operation_lock(epic_id, root=root):
        return _resume_dependency_bootstrap(
            epic_id, request_id, executor=executor, root=root, **kwargs,
        )


def _resume_dependency_bootstrap(
    epic_id: str,
    request_id: str,
    *,
    executor: BoundedOperationExecutor,
    root: Path,
    approval_references: Mapping[str, str] | None = None,
    execution_policy: DependencyExecutionPolicy = DEFAULT_DEPENDENCY_EXECUTION_POLICY,
    reclaim_running: bool = False,
    gate: LifecycleGate | None = None,
    quiesce_timeout: float = 0.0,
    kickoff: Callable[[KickoffReason], None] | None = None,
    requester: AuthenticatedHuman | None = None,
    coordinate_planning: bool = True,
) -> DependencyResumeResult:
    """Revalidate one human ping without treating it as authority or evidence.

    ``request_id`` is the delivery/idempotency identity.  Repeated or concurrent
    delivery shares one durable action.  A supervisor may set ``reclaim_running``
    only after a process restart; live duplicate delivery must leave it false.
    """

    if not isinstance(request_id, str) or not request_id.strip():
        raise DependencyResumeError("request_id must be non-blank text")
    if not isinstance(epic_id, str) or not epic_id.strip():
        raise DependencyResumeError("epic_id must be non-blank text")
    bootstrap = ensure_dependency_scope(epic_id, root=root)
    approvals = dict(approval_references or {})
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in approvals.items()
    ):
        raise DependencyResumeError(
            "approval references must map dependency IDs to approval IDs"
        )

    if requester is not None and not isinstance(requester, AuthenticatedHuman):
        raise DependencyResumeError("requester must be an authenticated human")
    requester_id = requester.subject if requester is not None else ("epic_team" if not coordinate_planning else "human")
    action_id = _action_id(epic_id, request_id)
    action = create_or_load_action(
        action_id,
        _ACTION_KIND,
        root=root,
        attempt_bound=bootstrap.scope.limits.max_attempts,
        metadata={
            "epic_id": epic_id,
            "request_id": request_id,
            "scope_fingerprint": bootstrap.scope.fingerprint,
            "manifest_revision": bootstrap.scope.manifest_revision,
        },
        lifecycle_state="dependency_revalidation_requested",
        owning_team={"kind": "epic_team", "work_id": epic_id},
        provenance={"actor": requester_id, "request_id": request_id},
    )
    before_attempts = int(action.get("attempt_count") or 0)
    planning_resumed = False
    executed = False

    def execute(context: ActionContext) -> ActionResult:
        nonlocal executed
        executed = True
        return _execute_revalidation(
            epic_id,
            action,
            context,
            executor=executor,
            root=root,
            approval_references=approvals,
            execution_policy=execution_policy,
        )

    if not coordinate_planning:
        # A tool cannot quiesce its own turn. Automatic HTTP continuation also
        # verifies without stopping planning, then queues its own continuation.
        # The outer operation lock serializes both paths, and mutation admission
        # still rechecks current human installation authority.
        action = resume_action(action_id, root=root, execute=execute,
                               reclaim_running=reclaim_running)
    else:
        lifecycle = gate or lifecycle_gate()
        with lifecycle.transition(epic_id, (epic_id,), timeout=quiesce_timeout) as quiesced:
            if quiesced:
                action = resume_action(
                    action_id, root=root, execute=execute,
                    reclaim_running=reclaim_running,
                )

    projection = project_bootstrap(epic_id, root=root)
    ready = projection.state is BootstrapState.READY
    if coordinate_planning and executed and action.get("recovery_state") == "completed" and ready:
        (kickoff or _kickoff_planning)(
            KickoffReason(
                kind="human_message",
                work_id=epic_id,
                by=requester_id,
                root=root,
                message={
                    "role": "human",
                    "id": request_id,
                    "content": "Dependency revalidation is current; resume planning.",
                },
            )
        )
        planning_resumed = True
    return DependencyResumeResult(
        action_id=action_id,
        recovery_state=str(action.get("recovery_state") or "pending"),
        ready=ready,
        deduplicated=(not executed or before_attempts > 0),
        planning_resumed=planning_resumed,
        blockers=projection.blockers,
    )


def _execute_revalidation(
    epic_id: str,
    action: Mapping[str, object],
    context: ActionContext,
    *,
    executor: BoundedOperationExecutor,
    root: Path,
    approval_references: Mapping[str, str],
    execution_policy: DependencyExecutionPolicy,
) -> ActionResult:
    bootstrap = read_bootstrap(epic_id, root=root)
    manifest = require_dependency_manifest(epic_id, root=root)
    metadata = action.get("metadata")
    if not isinstance(metadata, Mapping):
        raise ActionFailure(
            "terminal_blocker", metadata={"reason": "invalid_request_record"}
        )
    if (
        bootstrap is None
        or metadata.get("scope_fingerprint") != bootstrap.scope.fingerprint
        or metadata.get("manifest_revision") != manifest.revision
        or bootstrap.scope.manifest_revision != manifest.revision
    ):
        raise ActionFailure(
            "human_gate",
            metadata={
                "reason": "stale_bootstrap_scope",
                "required_action": "review the current manifest and bootstrap scope, then send a new ping",
            },
        )

    readiness = project_current_dependency_evidence(epic_id, root=root)
    blocked_ids = {row.dependency_id for row in readiness.blockers if row.dependency_id}
    for entry in manifest.dependencies:
        if entry.dependency_id not in blocked_ids:
            continue
        dangling = _unfinished_attempts(epic_id, entry.dependency_id, root=root)
        try:
            inspected = _run_dependency(
                epic_id,
                entry.dependency_id,
                phase="inspect",
                context=context,
                operation_kind=CheckOperationKind.READ_ONLY,
                executor=executor,
                root=root,
                execution_policy=execution_policy,
            )
        except Exception as exc:
            _persist_dependency_blocker_from_error(
                epic_id,
                entry.dependency_id,
                entry.verification_recipe,
                entry.cleanup_plan,
                exc,
                root=root,
            )
            continue
        _reconcile_unfinished(
            epic_id,
            dangling,
            inspected.completion,
            root=root,
            execution_policy=execution_policy,
        )
        if _dependency_is_ready(epic_id, entry.dependency_id, root=root):
            _clear_dependency_blocker(epic_id, entry.dependency_id, root=root)
            continue

        approval_id = approval_references.get(
            entry.dependency_id
        ) or _latest_current_approval(epic_id, entry.dependency_id, root=root)
        if approval_id is None:
            _persist_dependency_blocker(
                epic_id,
                entry.dependency_id,
                inspected,
                "record a current per-entry installation approval or install it manually, then ping again",
                root=root,
            )
            continue
        try:
            setup = _run_dependency(
                epic_id,
                entry.dependency_id,
                phase="setup",
                context=context,
                operation_kind=CheckOperationKind.INSTALL,
                executor=executor,
                root=root,
                approval_reference=approval_id,
                bootstrap_revision=read_bootstrap(epic_id, root=root).revision,  # type: ignore[union-attr]
                execution_policy=execution_policy,
            )
        except Exception as exc:
            _persist_dependency_blocker_from_error(
                epic_id,
                entry.dependency_id,
                entry.operation,
                entry.cleanup_plan,
                exc,
                root=root,
            )
            continue
        if (
            setup.completion.result is CheckResult.FAILED
            or setup.blocker is not None
            or not setup.completion.authority_current
        ):
            _persist_dependency_blocker(
                epic_id,
                entry.dependency_id,
                setup,
                setup.blocker.next_action if setup.blocker else "inspect setup failure",
                root=root,
            )
            continue
        try:
            verified = _run_dependency(
                epic_id,
                entry.dependency_id,
                phase="verify",
                context=context,
                operation_kind=CheckOperationKind.READ_ONLY,
                executor=executor,
                root=root,
                execution_policy=execution_policy,
            )
        except Exception as exc:
            _persist_dependency_blocker_from_error(
                epic_id,
                entry.dependency_id,
                entry.verification_recipe,
                entry.cleanup_plan,
                exc,
                root=root,
            )
            continue
        if _dependency_is_ready(epic_id, entry.dependency_id, root=root):
            _clear_dependency_blocker(epic_id, entry.dependency_id, root=root)
        else:
            _persist_dependency_blocker(
                epic_id,
                entry.dependency_id,
                verified,
                "resolve verification failure and ping again",
                root=root,
            )

    bootstrap = read_bootstrap(epic_id, root=root)
    assert bootstrap is not None
    results = {row.artifact_id: row for row in bootstrap.feasibility_results}
    for artifact in bootstrap.scope.feasibility_artifacts:
        result = results.get(artifact.artifact_id)
        if result is not None and result.outcome.value == "succeeded":
            continue
        try:
            run_feasibility_proof(
                epic_id, artifact.artifact_id, executor=executor, root=root
            )
        except Exception as exc:
            _persist_feasibility_error(epic_id, artifact.artifact_id, exc, root=root)

    projection = project_bootstrap(epic_id, root=root)
    if projection.state is BootstrapState.READY:
        return ActionResult(
            metadata={"ready": True, "request_id": context.idempotency_key}
        )
    raise ActionFailure(
        "human_gate",
        metadata={
            "ready": False,
            "blockers": list(projection.blockers),
            "required_action": "follow the persisted blocker guidance, then send a new ping",
        },
    )


def _run_dependency(
    epic_id: str,
    dependency_id: str,
    *,
    phase: str,
    context: ActionContext,
    operation_kind: CheckOperationKind,
    executor: BoundedOperationExecutor,
    root: Path,
    execution_policy: DependencyExecutionPolicy,
    approval_reference: str | None = None,
    bootstrap_revision: int | None = None,
) -> DependencyRunResult:
    return run_dependency_operation(
        epic_id,
        dependency_id,
        operation_kind=operation_kind,
        executor=executor,
        root=root,
        approval_reference=approval_reference,
        bootstrap_revision=bootstrap_revision,
        execution_policy=execution_policy,
        attempt_id=_attempt_id(context, dependency_id, phase),
    )


def _unfinished_attempts(
    epic_id: str, dependency_id: str, *, root: Path
) -> tuple[CheckAdmission, ...]:
    events = read_dependency_check_history(epic_id, root=root)
    completed = {row.attempt_id for row in events if isinstance(row, CheckCompletion)}
    return tuple(
        row
        for row in events
        if isinstance(row, CheckAdmission)
        and row.dependency_id == dependency_id
        and row.attempt_id not in completed
    )


def _reconcile_unfinished(
    epic_id: str,
    admissions: tuple[CheckAdmission, ...],
    observation: CheckCompletion,
    *,
    root: Path,
    execution_policy: DependencyExecutionPolicy,
) -> None:
    for admission in admissions:
        record_trusted_dependency_check_completion(
            epic_id,
            admission.attempt_id,
            root=root,
            actual_environment=observation.actual_environment,
            result=observation.result,
            redacted_output="reconciled after interruption: "
            + observation.redacted_output,
            selected_version=observation.selected_version,
            integrity_reference=observation.integrity_reference,
            lock_references=observation.lock_references,
            execution_policy=execution_policy,
        )


def _latest_current_approval(
    epic_id: str, dependency_id: str, *, root: Path
) -> str | None:
    for approval in reversed(read_installation_approvals(epic_id, root=root)):
        if (
            current_installation_approval(
                epic_id, dependency_id, approval.approval_id, root=root
            )
            is not None
        ):
            return approval.approval_id
    return None


def _dependency_is_ready(epic_id: str, dependency_id: str, *, root: Path) -> bool:
    projection = project_current_dependency_evidence(epic_id, root=root)
    return any(row.dependency_id == dependency_id for row in projection.accepted)


def _persist_dependency_blocker(
    epic_id: str,
    dependency_id: str,
    result: DependencyRunResult,
    next_action: str,
    *,
    root: Path,
) -> None:
    manifest = require_dependency_manifest(epic_id, root=root)
    entry = next(
        row for row in manifest.dependencies if row.dependency_id == dependency_id
    )
    _replace_dependency_blocker(
        epic_id,
        BootstrapBlocker(
            dependency_id=dependency_id,
            artifact_id=None,
            actor="human",
            last_checked_at=result.completion.completed_at,
            failed_operation=result.completion.exact_operation,
            environment=json.dumps(
                result.completion.actual_environment.to_dict(), sort_keys=True
            ),
            redacted_output=result.completion.redacted_output,
            investigation_steps=next_action,
            install_steps=entry.operation,
            expected_verification=entry.expected_verification_result,
            cleanup=entry.cleanup_plan,
            ping_action="ping the team after resolving this blocker",
        ),
        root=root,
    )


def _persist_dependency_blocker_from_error(
    epic_id: str,
    dependency_id: str,
    operation: str,
    cleanup: str,
    error: Exception,
    *,
    root: Path,
) -> None:
    entry = next(
        row
        for row in require_dependency_manifest(epic_id, root=root).dependencies
        if row.dependency_id == dependency_id
    )
    _replace_dependency_blocker(
        epic_id,
        BootstrapBlocker(
            dependency_id=dependency_id,
            artifact_id=None,
            actor="human",
            last_checked_at=None,
            failed_operation=operation,
            environment=json.dumps(entry.target_environment.to_dict(), sort_keys=True),
            redacted_output=_safe_error(error),
            investigation_steps="refresh approval, scope, policy, or recipe before retrying",
            install_steps=operation,
            expected_verification=entry.expected_verification_result,
            cleanup=cleanup,
            ping_action="ping the team after resolving this blocker",
        ),
        root=root,
    )


def _replace_dependency_blocker(
    epic_id: str, blocker: BootstrapBlocker, *, root: Path
) -> None:
    bootstrap = read_bootstrap(epic_id, root=root)
    assert bootstrap is not None
    retained = tuple(
        row for row in bootstrap.blockers if row.dependency_id != blocker.dependency_id
    )
    record_bootstrap_blockers(
        epic_id, (*retained, blocker), root=root, expected_revision=bootstrap.revision
    )


def _clear_dependency_blocker(epic_id: str, dependency_id: str, *, root: Path) -> None:
    bootstrap = read_bootstrap(epic_id, root=root)
    assert bootstrap is not None
    if any(row.dependency_id == dependency_id for row in bootstrap.blockers):
        clear_bootstrap_blockers(
            epic_id,
            dependency_id=dependency_id,
            root=root,
            expected_revision=bootstrap.revision,
        )


def _persist_feasibility_error(
    epic_id: str, artifact_id: str, error: Exception, *, root: Path
) -> None:
    bootstrap = read_bootstrap(epic_id, root=root)
    assert bootstrap is not None
    artifact = next(
        row
        for row in bootstrap.scope.feasibility_artifacts
        if row.artifact_id == artifact_id
    )
    retained = tuple(
        row for row in bootstrap.blockers if row.artifact_id != artifact_id
    )
    record_bootstrap_blockers(
        epic_id,
        (
            *retained,
            BootstrapBlocker(
                dependency_id=None,
                artifact_id=artifact_id,
                actor="human",
                last_checked_at=None,
                failed_operation=artifact.operation,
                environment=json.dumps(
                    artifact.target_environment.to_dict(), sort_keys=True
                ),
                redacted_output=_safe_error(error),
                investigation_steps="resolve the bounded feasibility failure",
                install_steps=None,
                expected_verification="operation exits successfully in the reviewed environment",
                cleanup=artifact.cleanup,
                ping_action="ping the team after resolving this blocker",
            ),
        ),
        root=root,
        expected_revision=bootstrap.revision,
    )


def _attempt_id(context: ActionContext, dependency_id: str, phase: str) -> str:
    raw = (
        f"{context.action_id}:{context.attempt_number}:{dependency_id}:{phase}".encode()
    )
    return "attempt_resume_" + hashlib.sha256(raw).hexdigest()


def _safe_error(error: Exception) -> str:
    """Persist an actionable class without leaking provider exception payloads."""

    return f"{type(error).__name__}: operation was refused or could not complete"


def _action_id(epic_id: str, request_id: str) -> str:
    digest = hashlib.sha256(f"{epic_id}:{request_id}".encode()).hexdigest()
    return f"{epic_id}:dependency_resume:{digest}"


def _kickoff_planning(reason: KickoffReason) -> None:
    from cascade.workspace.kickoff import kickoff_turn

    kickoff_turn(reason)
