"""Integration coverage for authority at dependency mutation boundaries."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    InstallationApprovalDenied,
    approve_dependency_installations,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapEntryScope,
    BootstrapLimits,
    BootstrapScope,
    create_bootstrap,
)
from cascade.epic.dependency_evidence import (
    CheckOperationKind,
    CheckResult,
    DependencyExecutionPolicy,
    DependencyEvidenceError,
    admit_dependency_check,
    dispatch_dependency_mutation,
    project_current_dependency_evidence,
    read_dependency_check_history,
    record_trusted_dependency_check_completion,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    write_dependency_manifest,
)
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


@pytest.fixture
def environment() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        "owned-worktree",
        "container",
        "linux",
        "x86_64",
        runner="codex-yolo",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="owned-worktree",
        runtime="python-3.12",
        container_digest="sha256:runner",
    )


def dependency(
    environment: EnvironmentIdentity,
    *,
    operation: str = "install tool 1.2.3 into .tools/tool",
    scope: str = "project-local .tools/tool",
) -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/releases/1.2.3",
        digest="sha256:tool-1.2.3",
        target_environment=environment,
        install_scope=scope,
        install_destination=scope,
        operation=operation,
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
    )


def prepare(
    board: Path,
    environment: EnvironmentIdentity,
    entry: DependencyEntry,
) -> int:
    manifest = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, False, (entry,)),
        root=board,
        expected_revision=0,
    )
    bootstrap = create_bootstrap(
        "epic_001",
        BootstrapScope(
            manifest_revision=manifest.revision,
            entries=(
                BootstrapEntryScope(
                    dependency_id=entry.dependency_id,
                    source=entry.source,
                    integrity_reference=entry.integrity_reference,
                    setup_operation=entry.operation,
                    check_operation=entry.verification_recipe,
                    paths=(entry.install_destination,),
                    destination=entry.install_destination,
                    cleanup=entry.cleanup_plan,
                ),
            ),
            feasibility_artifacts=(),
            limits=BootstrapLimits(60, 2, 4096),
        ),
        root=board,
    )
    return bootstrap.revision


def approve(board: Path) -> str:
    return approve_dependency_installations(
        "epic_001",
        ("dep_tool",),
        approver=AuthenticatedHuman("reviewer@example.test"),
        approved_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
        root=board,
    )[0].approval_id


@pytest.mark.parametrize(
    "kind",
    (
        CheckOperationKind.INSTALL,
        CheckOperationKind.UPGRADE,
        CheckOperationKind.IMPLICIT_PULL,
    ),
)
def test_capability_plan_signoff_and_ping_never_grant_mutation_authority(
    board: Path,
    environment: EnvironmentIdentity,
    kind: CheckOperationKind,
) -> None:
    entry = dependency(environment)
    bootstrap_revision = prepare(board, environment, entry)
    capabilities = {"provider": "yolo", "worktree": "owned", "plan": "approved"}
    assert capabilities["provider"] == "yolo"

    for non_authority in (None, "epic-signoff", "human-ping"):
        with pytest.raises(InstallationApprovalDenied):
            admit_dependency_check(
                "epic_001",
                entry.dependency_id,
                root=board,
                operation_kind=kind,
                exact_operation=entry.operation,
                approval_reference=non_authority,
                bootstrap_revision=bootstrap_revision,
            )
    assert read_dependency_check_history("epic_001", root=board) == ()


def test_approved_operation_is_rechecked_at_dispatch_and_completion(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    bootstrap_revision = prepare(board, environment, entry)
    approval_id = approve(board)
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.INSTALL,
        exact_operation=entry.operation,
        approval_reference=approval_id,
        bootstrap_revision=bootstrap_revision,
    )
    mutations: list[str] = []
    with pytest.raises(DependencyEvidenceError, match="policy revision is stale"):
        dispatch_dependency_mutation(
            "epic_001",
            admission.attempt_id,
            lambda: mutations.append("wrong-policy"),
            root=board,
            execution_policy=DependencyExecutionPolicy(revision="policy-v2"),
        )
    assert mutations == []
    assert (
        dispatch_dependency_mutation(
            "epic_001",
            admission.attempt_id,
            lambda: mutations.append("installed") or "ok",
            root=board,
        )
        == "ok"
    )
    assert mutations == ["installed"]

    revised = replace(entry, digest="sha256:changed-after-dispatch")
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, False, (revised,)),
        root=board,
        expected_revision=1,
    )
    completion = record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=board,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="installed",
        selected_version=entry.version,
        integrity_reference=entry.digest,
    )
    assert not completion.authority_current
    assert (
        project_current_dependency_evidence("epic_001", root=board).blockers[0].reason
        == "stale_authority"
    )


def test_stale_admission_is_denied_before_provider_dispatch(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    bootstrap_revision = prepare(board, environment, entry)
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.IMPLICIT_PULL,
        exact_operation=entry.operation,
        approval_reference=approve(board),
        bootstrap_revision=bootstrap_revision,
    )
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(
            environment,
            None,
            False,
            (replace(entry, source="https://mirror.test/tool"),),
        ),
        root=board,
        expected_revision=1,
    )
    mutations: list[str] = []
    with pytest.raises(DependencyEvidenceError, match="stale|bound"):
        dispatch_dependency_mutation(
            "epic_001",
            admission.attempt_id,
            lambda: mutations.append("pulled"),
            root=board,
        )
    assert mutations == []


@pytest.mark.parametrize(
    ("operation", "scope", "denial"),
    (
        ("install tool", "system /usr/local/bin", "system mutation"),
        ("sudo install tool into .tools", "project-local .tools", "sudo"),
        ("set tool as the default runtime", "project-local .tools", "default"),
        (
            "prompt for credential then install tool",
            "project-local .tools",
            "credential",
        ),
        (
            "accept license agreement then install tool",
            "project-local .tools",
            "license",
        ),
    ),
)
def test_current_policy_fails_closed_before_unsafe_mutation_admission(
    board: Path,
    environment: EnvironmentIdentity,
    operation: str,
    scope: str,
    denial: str,
) -> None:
    entry = dependency(environment, operation=operation, scope=scope)
    bootstrap_revision = prepare(board, environment, entry)
    with pytest.raises(DependencyEvidenceError, match=denial):
        admit_dependency_check(
            "epic_001",
            entry.dependency_id,
            root=board,
            operation_kind=CheckOperationKind.INSTALL,
            exact_operation=entry.operation,
            approval_reference=approve(board),
            bootstrap_revision=bootstrap_revision,
        )
    assert read_dependency_check_history("epic_001", root=board) == ()


def test_read_only_discovery_needs_neither_bootstrap_revision_nor_approval(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    prepare(board, environment, entry)
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
    )
    assert admission.approval_reference is None
    assert admission.bootstrap_revision is None
