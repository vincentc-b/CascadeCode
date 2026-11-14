"""Epic-scoped canonical dependency-manifest read and write operations.

Declarations trigger bounded verification. They never grant installation
authority; setup requires a separate, current human approval.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cascade.epic.dependency_lock import dependency_state_lock
from cascade.epic.dependency_manifests import (
    DependencyManifestSnapshot,
    InvalidDependencyManifest,
    dependency_manifest_repository,
    read_dependency_manifest as read_canonical_manifest,
    validate_dependency_manifest,
    write_dependency_manifest as write_canonical_manifest,
)
from cascade.epic.dependency_status import project_dependency_status

_MANIFEST_KEYS = frozenset(
    {"target_environment", "actual_environment", "none_required", "dependencies"}
)
_ENVIRONMENT_KEYS = frozenset(
    {
        "environment_id",
        "kind",
        "platform",
        "architecture",
        "runner",
        "repository",
        "worktree",
        "sandbox",
        "runtime",
        "container_digest",
    }
)
_DEPENDENCY_KEYS = frozenset(
    {
        "dependency_id",
        "version",
        "source",
        "digest",
        "target_environment",
        "install_scope",
        "operation",
        "cleanup_plan",
        "verification_recipe",
        "requested_range",
        "resolved_version",
        "expected_verification_result",
        "feasibility_proof_requirements",
        "feasibility_proof_references",
        "install_destination",
        "lock_references",
        "integrity_reference",
    }
)


def read_dependency_manifest(*, epic_id: str, root: Path) -> dict[str, Any]:
    """Return the current canonical snapshot, or an explicit revision-zero miss."""

    repo = _owned_repository(epic_id, root)
    with dependency_state_lock(root=repo):
        snapshot = read_canonical_manifest(epic_id, root=repo)
        return _result(epic_id, snapshot, root=repo)


def write_dependency_manifest(
    manifest: object,
    expected_revision: object,
    *,
    epic_id: str,
    root: Path,
) -> dict[str, Any]:
    """Validate and append a canonical snapshot with optimistic concurrency."""

    if (
        isinstance(expected_revision, bool)
        or not isinstance(expected_revision, int)
        or expected_revision < 0
    ):
        raise InvalidDependencyManifest(
            "expected_revision must be a non-negative integer"
        )

    # Validate raw public data before compatibility constructors can fill in
    # legacy environment identity fields.  The canonical persistence reader
    # remains backwards compatible; new authoring is current-schema only.
    _validate_public_manifest_shape(manifest)
    draft = validate_dependency_manifest(manifest)
    environments = [draft.target_environment, draft.actual_environment,
                    *(entry.target_environment for entry in draft.dependencies)]
    if any(env is not None and not env.is_fully_specified for env in environments):
        raise InvalidDependencyManifest("complete environment identities are required")

    repo = _owned_repository(epic_id, root)
    with dependency_state_lock(root=repo):
        snapshot = write_canonical_manifest(
            epic_id,
            draft,
            root=repo,
            expected_revision=expected_revision,
        )
    # Never hold the state lock across subprocess execution. Revalidation
    # re-reads the manifest and checks installation authority at dispatch.
    verification = None
    if snapshot.dependencies:
        from cascade.epic.dependency_checks import run_dependency_check
        from cascade.epic.dependency_resume import DependencyResumeError

        try:
            verification = run_dependency_check(epic_id=epic_id, root=root)
        except DependencyResumeError as exc:
            # The manifest is already durable; a concurrent check must not
            # make the successful write look like a revision-conflict retry.
            verification = {"pending": True, "detail": str(exc)}
    with dependency_state_lock(root=repo):
        result = _result(epic_id, read_canonical_manifest(epic_id, root=repo), root=repo)
    result["verification"] = verification
    return result


def _result(
    epic_id: str,
    snapshot: DependencyManifestSnapshot | None,
    *,
    root: Path,
) -> dict[str, Any]:
    """Build one JSON-safe response while the dependency lock is held."""

    software_status = project_dependency_status(epic_id, root=root)
    from cascade.epic.dependency_declaration import authoring_context
    authoring = authoring_context(epic_id, root=root)
    return {
        "manifest": snapshot.to_dict() if snapshot is not None else None,
        "manifest_revision": snapshot.revision if snapshot is not None else 0,
        "authoring": authoring,
        "software_dependency_status": software_status,
        "plan_readiness": software_status["planning_readiness"],
    }


def _validate_public_manifest_shape(raw: object) -> None:
    manifest = _exact_mapping(raw, _MANIFEST_KEYS, "manifest")
    _exact_mapping(
        manifest.get("target_environment"),
        _ENVIRONMENT_KEYS,
        "manifest.target_environment",
    )
    actual = manifest.get("actual_environment")
    if actual is not None:
        _exact_mapping(
            actual,
            _ENVIRONMENT_KEYS,
            "manifest.actual_environment",
        )

    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, list):
        raise InvalidDependencyManifest("manifest.dependencies must be a list")
    for index, raw_entry in enumerate(dependencies):
        field = f"manifest.dependencies[{index}]"
        entry = _exact_mapping(raw_entry, _DEPENDENCY_KEYS, field)
        _exact_mapping(
            entry.get("target_environment"),
            _ENVIRONMENT_KEYS,
            f"{field}.target_environment",
        )


def _exact_mapping(
    raw: object, expected: frozenset[str], field: str
) -> Mapping[str, object]:
    if not isinstance(raw, Mapping) or not all(
        isinstance(key, str) for key in raw
    ):
        raise InvalidDependencyManifest(f"{field} must be an object")
    keys = set(raw)
    missing = expected - keys
    unknown = keys - expected
    if missing:
        raise InvalidDependencyManifest(
            f"{field} is missing required field(s): {', '.join(sorted(missing))}"
        )
    if unknown:
        raise InvalidDependencyManifest(
            f"{field} has unknown field(s): {', '.join(sorted(unknown))}"
        )
    return raw


def _owned_repository(epic_id: str, root: Path) -> Path:
    from cascade.board.store import read_doc
    from cascade.workspace.integration_worktree import get_integration_worktree, locate_trunk
    from cascade.board.context import resolve_tracking_root

    trunk = locate_trunk(resolve_tracking_root(root))
    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        raise PermissionError("owning Epic integration worktree unavailable")
    repo = dependency_manifest_repository(epic_id, root=trunk)
    doc = read_doc(epic_id, root=repo)
    if doc.meta.tier != "epic" or doc.meta.status != "active":
        raise PermissionError("manifest authoring requires an active owned Epic")
    path = repo / "docs/epics/2_active/_dependency_manifests" / f"{epic_id}.json"
    if not path.resolve().is_relative_to(repo.resolve()) or any(p.is_symlink() for p in [path, *path.parents] if p != repo.parent):
        raise PermissionError("manifest path escape denied")
    return repo
