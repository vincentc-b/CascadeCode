"""Epic-scoped canonical dependency-manifest read and write operations.

This service only declares dependency requirements.  It deliberately exposes
no installation, approval, check, or execution capability.
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

    repo = dependency_manifest_repository(epic_id, root=Path(root).resolve())
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

    repo = dependency_manifest_repository(epic_id, root=Path(root).resolve())
    with dependency_state_lock(root=repo):
        snapshot = write_canonical_manifest(
            epic_id,
            draft,
            root=repo,
            expected_revision=expected_revision,
        )
        return _result(epic_id, snapshot, root=repo)


def _result(
    epic_id: str,
    snapshot: DependencyManifestSnapshot | None,
    *,
    root: Path,
) -> dict[str, Any]:
    """Build one JSON-safe response while the dependency lock is held."""

    software_status = project_dependency_status(epic_id, root=root)
    return {
        "manifest": snapshot.to_dict() if snapshot is not None else None,
        "manifest_revision": snapshot.revision if snapshot is not None else 0,
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
