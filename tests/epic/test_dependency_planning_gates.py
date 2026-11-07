"""Lifecycle integration matrix for dependency-gated planning entry points."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from cascade.approvals import approve_epic_plan
from cascade.epic.dependency_approvals import (
    InstallationApprovalDenied,
    read_installation_approvals,
    require_installation_approval,
)
from cascade.epic.dependency_evidence import (
    CheckOperationKind,
    CheckResult,
    admit_dependency_check,
    compute_dependency_readiness,
    record_trusted_dependency_check_completion,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    manifest_path,
    write_dependency_manifest,
)
from cascade.epic.guard import EpicToolDenied
from cascade.epic.mint import mint_feature
from cascade.epic.planning_signoffs import (
    DependenciesNotReady,
    canonical_plan_revision,
    current_valid_sign_offs,
    sign_off_epic_plan,
)
from tests.support import add_doc, make_repo


def environment(name: str = "primary") -> EnvironmentIdentity:
    return EnvironmentIdentity(
        name,
        "container",
        "linux",
        "x86_64",
        runner=f"runner-{name}",
        repository="example/cascade",
        worktree=f"/work/{name}",
        sandbox="container",
        runtime="python-3.12",
        container_digest=f"sha256:{name}",
    )


def dependency(dependency_id: str, target: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id=dependency_id,
        version="1.2.3",
        requested_range="^1.2",
        resolved_version="1.2.3",
        source=f"https://packages.example/{dependency_id}",
        digest=f"sha256:{dependency_id}",
        integrity_reference=f"sha256:{dependency_id}",
        lock_references=(f"uv.lock:{dependency_id}",),
        target_environment=target,
        install_scope="epic",
        install_destination=f".tools/{dependency_id}",
        operation=f"install {dependency_id}",
        cleanup_plan=f"remove .tools/{dependency_id}",
        verification_recipe=f"check {dependency_id}",
        expected_verification_result=f"{dependency_id} ok",
    )


def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Planning", tier="epic", status="active")
    return root


def complete(root: Path, entry: DependencyEntry, actual: EnvironmentIdentity) -> None:
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=root,
        actual_environment=actual,
        result=CheckResult.SUCCEEDED,
        redacted_output=f"{entry.dependency_id} ok",
        selected_version=entry.resolved_version or entry.version,
        integrity_reference=entry.integrity_reference or entry.digest,
        lock_references=entry.lock_references,
    )


def test_absent_manifest_blocks_all_entry_points_and_none_required_passes(
    tmp_path: Path,
) -> None:
    root = board(tmp_path)
    revision = canonical_plan_revision("epic_001", root=root)
    assert revision is not None

    readiness = compute_dependency_readiness("epic_001", root=root)
    assert [row.reason for row in readiness.blockers] == ["missing_manifest"]
    with pytest.raises(EpicToolDenied, match="missing_manifest"):
        mint_feature("Blocked", epic_id="epic_001", root=root)
    with pytest.raises(DependenciesNotReady, match="missing_manifest"):
        sign_off_epic_plan("epic_001", "epic_manager", revision, root=root)

    target = environment("none")
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, True, ()),
        root=root,
        expected_revision=0,
    )
    feature_id = mint_feature("Allowed", epic_id="epic_001", root=root)
    assert feature_id.startswith("feat_001_")
    revision = canonical_plan_revision("epic_001", root=root)
    assert revision is not None
    sign_off_epic_plan("epic_001", "epic_manager", revision, root=root)
    sign_off_epic_plan("epic_001", "epic_architect", revision, root=root)
    assert approve_epic_plan("epic_001", root=root)["ok"] is True


def test_distinct_environments_feasibility_and_selective_invalidation(
    tmp_path: Path,
) -> None:
    root = board(tmp_path)
    python = dependency("dep_python", environment("python"))
    node = dependency("dep_node", environment("node"))
    unresolved = replace(
        python,
        feasibility_proof_requirements=("arm-build",),
        feasibility_proof_references=(),
    )
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(
            environment("display"), None, False, (unresolved, node)
        ),
        root=root,
        expected_revision=0,
    )
    assert [
        row.reason
        for row in compute_dependency_readiness("epic_001", root=root).blockers
    ] == [
        "unresolved_feasibility",
        "missing_check",
    ]

    python = replace(
        python,
        feasibility_proof_requirements=("arm-build",),
        feasibility_proof_references=("proof:arm-build",),
    )
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment("display"), None, False, (python, node)),
        root=root,
        expected_revision=1,
    )
    complete(root, python, python.target_environment)
    complete(root, node, node.target_environment)
    # The feasibility proof is independently attached to the trusted attempt.
    assert not compute_dependency_readiness("epic_001", root=root).ready
    admission = admit_dependency_check(
        "epic_001",
        python.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=python.verification_recipe,
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=root,
        actual_environment=python.target_environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="dep_python ok",
        selected_version="1.2.3",
        integrity_reference=python.integrity_reference or python.digest,
        lock_references=(*python.lock_references, "proof:arm-build"),
    )
    assert compute_dependency_readiness("epic_001", root=root).ready

    revision = canonical_plan_revision("epic_001", root=root)
    assert revision is not None
    sign_off_epic_plan("epic_001", "epic_manager", revision, root=root)
    sign_off_epic_plan("epic_001", "epic_architect", revision, root=root)
    assert set(current_valid_sign_offs("epic_001", root=root)) == {
        "epic_manager",
        "epic_architect",
    }

    changed = replace(python, verification_recipe="check dep_python --strict")
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment("display"), None, False, (changed, node)),
        root=root,
        expected_revision=2,
    )
    projection = compute_dependency_readiness("epic_001", root=root)
    assert [(row.dependency_id, row.reason) for row in projection.blockers] == [
        ("dep_python", "stale_check")
    ]
    assert [row.dependency_id for row in projection.accepted] == ["dep_node"]
    assert current_valid_sign_offs("epic_001", root=root) == {}


def test_plan_approval_never_creates_installation_authority(tmp_path: Path) -> None:
    root = board(tmp_path)
    entry = dependency("dep_python", environment())
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(entry.target_environment, None, False, (entry,)),
        root=root,
        expected_revision=0,
    )
    complete(root, entry, entry.target_environment)
    mint_feature("Child", epic_id="epic_001", root=root)
    revision = canonical_plan_revision("epic_001", root=root)
    assert revision is not None
    sign_off_epic_plan("epic_001", "epic_manager", revision, root=root)
    sign_off_epic_plan("epic_001", "epic_architect", revision, root=root)
    approve_epic_plan("epic_001", root=root)

    assert read_installation_approvals("epic_001", root=root) == ()
    with pytest.raises(InstallationApprovalDenied):
        require_installation_approval(
            "epic_001", "dep_python", None, entry.operation, root=root
        )


def test_legacy_v1_manifest_is_history_not_current_authority(tmp_path: Path) -> None:
    root = board(tmp_path)
    target = {
        "environment_id": "legacy",
        "kind": "container",
        "platform": "linux",
        "architecture": "x86_64",
    }
    path = manifest_path("epic_001", root=root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "epic_id": "epic_001",
                "snapshots": [
                    {
                        "revision": 1,
                        "recorded_at": "2026-11-07T00:00:00+00:00",
                        "target_environment": target,
                        "actual_environment": target,
                        "none_required": False,
                        "dependencies": [
                            {
                                "dependency_id": "dep_legacy",
                                "version": "1.0.0",
                                "source": "https://legacy.example/package",
                                "digest": "sha256:legacy",
                                "target_environment": target,
                                "install_scope": "epic",
                                "operation": "install legacy",
                                "cleanup_plan": "remove legacy",
                                "verification_recipe": "check legacy",
                            }
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )

    readiness = compute_dependency_readiness("epic_001", root=root)
    assert [row.reason for row in readiness.blockers] == ["legacy_manifest"]
    with pytest.raises(EpicToolDenied, match="legacy_manifest"):
        mint_feature("Still blocked", epic_id="epic_001", root=root)

    current = environment("current")
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(current, None, True, ()),
        root=root,
        expected_revision=1,
    )
    assert compute_dependency_readiness("epic_001", root=root).ready
