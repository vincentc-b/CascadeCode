"""Focused service coverage for scoped dependency-manifest authoring."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

from cascade.epic.dependency_manifest_authoring import (
    read_dependency_manifest,
    write_dependency_manifest,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    EnvironmentIdentity,
    InvalidDependencyManifest,
    StaleDependencyManifestRevision,
    read_dependency_manifest_history,
)
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


def environment(name: str) -> EnvironmentIdentity:
    return EnvironmentIdentity(
        environment_id=name,
        kind="container",
        platform="linux",
        architecture="x86_64",
        runner=f"runner-{name}",
        repository="example/cascade",
        worktree=f"/work/{name}",
        sandbox="container",
        runtime="python-3.12",
        container_digest=f"sha256:{name}",
    )


def entry(dependency_id: str, target: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id=dependency_id,
        version="1.2.3",
        source=f"https://packages.example/{dependency_id}",
        digest=f"sha256:{dependency_id}",
        target_environment=target,
        install_scope="epic",
        operation=f"install {dependency_id}",
        cleanup_plan=f"remove {dependency_id}",
        verification_recipe=f"check {dependency_id}",
    )


def manifest(*dependencies: DependencyEntry) -> dict[str, object]:
    return {
        "target_environment": environment("display").to_dict(),
        "actual_environment": None,
        "none_required": not dependencies,
        "dependencies": [row.to_dict() for row in dependencies],
    }


def test_read_missing_and_write_return_coherent_json_safe_projections(
    board: Path,
) -> None:
    missing = read_dependency_manifest(epic_id="epic_001", root=board)
    assert missing["manifest"] is None
    assert missing["manifest_revision"] == 0
    assert missing["software_dependency_status"]["errors"][0]["code"] == (
        "missing_manifest"
    )
    json.dumps(missing)

    created = write_dependency_manifest(
        manifest(), 0, epic_id="epic_001", root=board
    )
    assert created["manifest_revision"] == 1
    assert created["manifest"]["none_required"] is True
    assert created["software_dependency_status"]["manifest"]["revision"] == 1
    assert created["plan_readiness"] == created["software_dependency_status"][
        "planning_readiness"
    ]
    json.dumps(created)


def test_write_preserves_independent_targets_and_revision_semantics(
    board: Path,
) -> None:
    request = manifest(
        entry("dep_python", environment("python")),
        entry("dep_node", environment("node")),
    )
    first = write_dependency_manifest(request, 0, epic_id="epic_001", root=board)
    replay = write_dependency_manifest(request, 1, epic_id="epic_001", root=board)
    assert replay["manifest"] == first["manifest"]
    assert replay["manifest_revision"] == 1
    targets = [
        row["target_environment"]["environment_id"]
        for row in replay["manifest"]["dependencies"]
    ]
    assert targets == ["python", "node"]

    changed = deepcopy(request)
    changed["dependencies"][0]["version"] = "1.2.4"
    changed["dependencies"][0]["resolved_version"] = "1.2.4"
    changed["dependencies"][0]["digest"] = "sha256:python-1.2.4"
    changed["dependencies"][0]["integrity_reference"] = "sha256:python-1.2.4"
    second = write_dependency_manifest(
        changed, 1, epic_id="epic_001", root=board
    )
    assert second["manifest_revision"] == 2

    with pytest.raises(StaleDependencyManifestRevision, match="current is 2"):
        write_dependency_manifest(request, 1, epic_id="epic_001", root=board)


@pytest.mark.parametrize("revision", [None, True, -1, 0.5, "0"])
def test_write_rejects_invalid_expected_revision_without_mutation(
    board: Path, revision: object
) -> None:
    with pytest.raises(InvalidDependencyManifest, match="non-negative integer"):
        write_dependency_manifest(
            manifest(), revision, epic_id="epic_001", root=board
        )
    assert read_dependency_manifest_history("epic_001", root=board) == ()


def test_write_rejects_legacy_identity_unknown_fields_and_duplicates_before_mutation(
    board: Path,
) -> None:
    dependency = entry("dep_python", environment("python"))
    legacy_identity = manifest(dependency)
    del legacy_identity["target_environment"]["runner"]
    with pytest.raises(InvalidDependencyManifest, match="runner"):
        write_dependency_manifest(
            legacy_identity, 0, epic_id="epic_001", root=board
        )

    unknown = manifest(dependency)
    unknown["unexpected"] = True
    with pytest.raises(InvalidDependencyManifest, match="unknown field"):
        write_dependency_manifest(unknown, 0, epic_id="epic_001", root=board)

    duplicate = manifest(dependency, deepcopy(dependency))
    with pytest.raises(InvalidDependencyManifest, match="must be unique"):
        write_dependency_manifest(duplicate, 0, epic_id="epic_001", root=board)

    assert read_dependency_manifest_history("epic_001", root=board) == ()
