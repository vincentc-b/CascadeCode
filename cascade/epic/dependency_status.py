"""Live dependency/bootstrap read model shared by War Room and agent turns.

This module is deliberately a projection.  The manifest, bootstrap journal,
installation approvals, and check evidence remain the only authorities.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cascade.epic.dependency_approvals import (
    DependencyApprovalError,
    read_installation_approvals,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapBlocker,
    DependencyBootstrapError,
    project_bootstrap,
    read_bootstrap,
)
from cascade.epic.dependency_evidence import (
    CheckAdmission,
    CheckCompletion,
    DependencyEvidenceError,
    compute_dependency_readiness,
    read_dependency_check_history,
)
from cascade.epic.dependency_manifests import (
    DependencyManifestError,
    InstallationBinding,
    environment_identities_match,
    installation_approval_is_valid,
    read_dependency_manifest,
)

_UNKNOWN = frozenset(
    {"unknown", "unspecified", "unresolved", "pending", "n/a", "not applicable"}
)


def project_dependency_status(epic_id: str, *, root: Path) -> dict[str, Any]:
    """Build the complete current read model without creating authority.

    Read failures are data in this model rather than exceptions.  That keeps a
    malformed sidecar visible in the War Room and causes the projection to fail
    closed instead of making the whole board route unavailable.
    """

    repo = Path(root).resolve()
    try:
        manifest = read_dependency_manifest(epic_id, root=repo)
    except DependencyManifestError as exc:
        return _unavailable(epic_id, "invalid_manifest", str(exc), root=repo)
    if manifest is None:
        return _unavailable(
            epic_id,
            "missing_manifest",
            "The owning Epic Manager or Architect must call read_dependency_manifest then write_dependency_manifest with expected_revision=0. Declare none_required=true and dependencies=[] with a complete target environment when no dependencies are needed. Declaration does not authorize installation.",
            root=repo,
        )

    readiness = compute_dependency_readiness(epic_id, root=repo)
    evidence_blockers = {row.dependency_id: row for row in readiness.blockers}
    accepted = {row.dependency_id: row for row in readiness.accepted}

    errors: list[dict[str, str]] = []
    try:
        approvals = read_installation_approvals(epic_id, root=repo)
    except DependencyApprovalError as exc:
        approvals = ()
        errors.append({"code": "invalid_installation_approvals", "detail": str(exc)})
    try:
        attempts = read_dependency_check_history(epic_id, root=repo)
    except DependencyEvidenceError as exc:
        attempts = ()
        errors.append({"code": "invalid_check_evidence", "detail": str(exc)})

    bootstrap = None
    bootstrap_projection = None
    try:
        bootstrap = read_bootstrap(epic_id, root=repo)
        if bootstrap is not None:
            bootstrap_projection = project_bootstrap(epic_id, root=repo)
    except (DependencyBootstrapError, DependencyManifestError) as exc:
        errors.append({"code": "invalid_bootstrap", "detail": str(exc)})

    dependency_rows = []
    for entry in manifest.dependencies:
        entry_approvals = tuple(
            row for row in approvals if row.binding.dependency_id == entry.dependency_id
        )
        current = tuple(
            row
            for row in entry_approvals
            if row.schema_version == 2
            and installation_approval_is_valid(row, entry)
        )
        entry_attempts = tuple(
            row for row in attempts if row.dependency_id == entry.dependency_id
        )
        completion = next(
            (row for row in reversed(entry_attempts) if isinstance(row, CheckCompletion)),
            None,
        )
        last_check = entry_attempts[-1] if entry_attempts else None
        recorded_blocker = _recorded_blocker(bootstrap, entry.dependency_id)
        evidence_blocker = evidence_blockers.get(entry.dependency_id)
        scope = _entry_scope(bootstrap, entry.dependency_id)
        approval_state = "current" if current else ("stale" if entry_approvals else "missing")
        evidence_state = "current" if entry.dependency_id in accepted else (
            evidence_blocker.reason if evidence_blocker is not None else "unknown"
        )
        dependency_rows.append(
            {
                "dependency_id": entry.dependency_id,
                "status": "ready" if evidence_state == "current" else "blocked",
                "responsible_actor": _responsible_actor(
                    evidence_state, approval_state, recorded_blocker
                ),
                "binding": InstallationBinding.from_entry(entry).to_dict(),
                "requested_range": entry.requested_range,
                "resolved_version": entry.resolved_version,
                "lock_references": list(entry.lock_references),
                "integrity_reference": entry.integrity_reference,
                "why_needed": list(entry.feasibility_proof_requirements)
                or ["declared_in_canonical_manifest"],
                "bootstrap_scope": scope.to_dict() if scope else None,
                "actual_environment": (
                    completion.actual_environment.to_dict() if completion else None
                ),
                "environment_matches_target": (
                    environment_identities_match(
                        entry.target_environment, completion.actual_environment
                    )
                    if completion
                    else None
                ),
                "last_check": _last_check(last_check),
                "evidence": {
                    "state": evidence_state,
                    "accepted_attempt_id": (
                        accepted[entry.dependency_id].attempt_id
                        if entry.dependency_id in accepted
                        else None
                    ),
                    "failure": (
                        recorded_blocker.redacted_output
                        if recorded_blocker is not None
                        else evidence_state if evidence_state != "current" else None
                    ),
                    "next_action": (
                        evidence_blocker.next_action if evidence_blocker else None
                    ),
                },
                "guidance": {
                    "investigation": (
                        recorded_blocker.investigation_steps
                        if recorded_blocker is not None
                        else _known(entry.verification_recipe)
                    ),
                    "investigation_known": (
                        recorded_blocker.investigation_steps is not None
                        if recorded_blocker is not None
                        else _known(entry.verification_recipe) is not None
                    ),
                    "setup": (
                        recorded_blocker.install_steps
                        if recorded_blocker is not None
                        else _known(scope.setup_operation if scope else entry.operation)
                    ),
                    "expected_verification": entry.expected_verification_result,
                    "verification_operation": entry.verification_recipe,
                    "owned_artifact_cleanup": (
                        scope.cleanup if scope else entry.cleanup_plan
                    ),
                },
                "installation_approval": {
                    "state": approval_state,
                    "current": [_approval_summary(row) for row in current],
                    "stale": [
                        _approval_summary(row)
                        for row in entry_approvals
                        if row not in current
                    ],
                },
            }
        )

    if errors:
        status = "blocked"
    elif bootstrap_projection is not None:
        status = bootstrap_projection.state.value
    elif manifest.none_required:
        status = "ready"
    else:
        status = "unchecked"

    scope_revision = bootstrap.scope.manifest_revision if bootstrap else None
    bootstrap_current = scope_revision == manifest.revision if bootstrap else None
    return {
        "epic_id": epic_id,
        "status": status,
        "responsible_actor": _overall_actor(status, dependency_rows),
        "explicit_no_dependencies": manifest.none_required,
        "manifest": {
            "revision": manifest.revision,
            "recorded_at": manifest.recorded_at.isoformat(),
            "schema_current": manifest.is_current_schema,
            "target_environment": manifest.target_environment.to_dict(),
            "declared_actual_environment": (
                manifest.actual_environment.to_dict()
                if manifest.actual_environment is not None
                else None
            ),
        },
        "bootstrap": {
            "state": (
                bootstrap_projection.state.value
                if bootstrap_projection is not None
                else "not_required" if manifest.none_required else "missing"
            ),
            "revision": bootstrap.revision if bootstrap else None,
            "scope_manifest_revision": scope_revision,
            "scope_current": bootstrap_current,
            "scope_fingerprint": bootstrap.scope.fingerprint if bootstrap else None,
            "scope": bootstrap.scope.to_dict() if bootstrap else None,
            "authorization_state": _bootstrap_authorization_state(bootstrap),
            "authorization": (
                bootstrap.authorization.to_dict()
                if bootstrap and bootstrap.authorization is not None
                else None
            ),
            "blockers": (
                [row.to_dict() for row in bootstrap.blockers] if bootstrap else []
            ),
            "projection_blockers": (
                list(bootstrap_projection.blockers) if bootstrap_projection else []
            ),
        },
        "planning_readiness": _planning_readiness(epic_id, root=repo),
        "dependencies": dependency_rows,
        "errors": errors,
    }


def dependency_status_chat_summary(epic_id: str, *, root: Path) -> str:
    """Return a compact, machine-readable live summary for an agent prompt."""

    projection = project_dependency_status(epic_id, root=root)
    return "Live dependency/bootstrap state (canonical projection):\n" + json.dumps(
        projection, sort_keys=True, separators=(",", ":")
    )


def _unavailable(epic_id: str, code: str, detail: str, *, root: Path) -> dict[str, Any]:
    return {
        "epic_id": epic_id,
        "status": "blocked",
        "responsible_actor": "agent",
        "explicit_no_dependencies": False,
        "manifest": None,
        "bootstrap": None,
        "planning_readiness": _planning_readiness(epic_id, root=root),
        "dependencies": [],
        "errors": [{"code": code, "detail": detail}],
    }


def _planning_readiness(epic_id: str, *, root: Path) -> dict[str, object] | None:
    try:
        from cascade.epic.plan_readiness import (
            compute_epic_plan_readiness,
            epic_plan_readiness_to_dict,
        )

        readiness = compute_epic_plan_readiness(epic_id, root=root)
        return epic_plan_readiness_to_dict(readiness) if readiness else None
    except Exception as exc:  # a read model must expose corrupt sidecars, not hide the row
        return {"status": "unavailable", "error": type(exc).__name__}


def _entry_scope(bootstrap: Any, dependency_id: str) -> Any:
    if bootstrap is None:
        return None
    return next(
        (row for row in bootstrap.scope.entries if row.dependency_id == dependency_id),
        None,
    )


def _recorded_blocker(bootstrap: Any, dependency_id: str) -> BootstrapBlocker | None:
    if bootstrap is None:
        return None
    return next(
        (row for row in reversed(bootstrap.blockers) if row.dependency_id == dependency_id),
        None,
    )


def _last_check(row: CheckAdmission | CheckCompletion | None) -> dict[str, object] | None:
    if row is None:
        return None
    completion = row if isinstance(row, CheckCompletion) else None
    return {
        "attempt_id": row.attempt_id,
        "operation": row.exact_operation,
        "operation_kind": row.operation_kind.value,
        "admitted_at": row.admitted_at.isoformat(),
        "completed_at": completion.completed_at.isoformat() if completion else None,
        "result": completion.result.value if completion else "in_progress",
        "redacted_output": completion.redacted_output if completion else None,
        "approval_reference": row.approval_reference,
    }


def _approval_summary(approval: Any) -> dict[str, object]:
    return {
        "approval_id": approval.approval_id,
        "approver_id": approval.approver_id,
        "approved_at": approval.approved_at.isoformat(),
        "reviewed_manifest_revision": approval.reviewed_manifest_revision,
        "binding": approval.binding.to_dict(),
    }


def _known(value: str | None) -> str | None:
    if value is None or value.strip().casefold() in _UNKNOWN:
        return None
    return value


def _responsible_actor(
    evidence_state: str, approval_state: str, blocker: BootstrapBlocker | None
) -> str | None:
    if blocker is not None:
        return blocker.actor
    if evidence_state == "current":
        return None
    return "agent"


def _overall_actor(status: str, dependencies: list[dict[str, Any]]) -> str | None:
    if status == "ready":
        return None
    actors = {row["responsible_actor"] for row in dependencies if row["responsible_actor"]}
    if "human" in actors:
        return "human"
    if actors:
        return sorted(actors)[0]
    return "agent"


def _bootstrap_authorization_state(bootstrap: Any) -> str:
    if bootstrap is None or not bootstrap.scope.feasibility_artifacts:
        return "not_required"
    authorization = bootstrap.authorization
    if authorization is None:
        return "missing"
    if authorization.scope_fingerprint != bootstrap.scope.fingerprint:
        return "stale"
    expected = {row.artifact_id for row in bootstrap.scope.feasibility_artifacts}
    return "current" if set(authorization.artifact_ids) == expected else "stale"
