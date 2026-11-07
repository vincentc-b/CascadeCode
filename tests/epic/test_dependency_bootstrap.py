"""Integration coverage for epic-owned bootstrap persistence and gating."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    read_installation_approvals,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapBlocker,
    BootstrapEntryScope,
    BootstrapLimits,
    BootstrapScope,
    BootstrapState,
    DependencyBootstrapError,
    FeasibilityArtifact,
    FeasibilityOutcome,
    authorize_feasibility,
    create_bootstrap,
    project_bootstrap,
    read_bootstrap,
    read_bootstrap_history,
    record_bootstrap_blockers,
    record_feasibility_result,
    set_bootstrap_checking,
)
from cascade.epic.dependency_evidence import (
    CheckOperationKind,
    CheckResult,
    admit_dependency_check,
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
        "ci-linux",
        "container",
        "linux",
        "x86_64",
        runner="local-container",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:runner",
    )


def dependency(environment: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/1.2.3",
        digest="sha256:tool",
        target_environment=environment,
        install_scope="epic worktree",
        install_destination=".tools/tool",
        operation="install tool 1.2.3 into .tools/tool",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
        feasibility_proof_requirements=("adapter_probe",),
        feasibility_proof_references=("adapter_probe",),
    )


def scope(environment: EnvironmentIdentity) -> BootstrapScope:
    return BootstrapScope(
        manifest_revision=1,
        entries=(
            BootstrapEntryScope(
                dependency_id="dep_tool",
                source="https://tool.example/1.2.3",
                integrity_reference="sha256:tool",
                setup_operation="install tool 1.2.3 into .tools/tool",
                check_operation=".tools/tool --version",
                paths=(".tools/tool", "bootstrap/adapter_probe.py"),
                destination=".tools/tool",
                cleanup="remove .tools/tool",
            ),
        ),
        feasibility_artifacts=(
            FeasibilityArtifact(
                artifact_id="adapter_probe",
                operation="python bootstrap/adapter_probe.py",
                target_environment=environment,
                input_paths=("bootstrap/adapter_probe.py",),
                output_paths=(".cascade/bootstrap/adapter-result.json",),
                cleanup="remove bootstrap/adapter_probe.py and its result",
            ),
        ),
        limits=BootstrapLimits(
            timeout_seconds=30,
            max_attempts=2,
            max_output_bytes=4096,
            memory_bytes=128 * 1024 * 1024,
        ),
    )


def write_manifest(board: Path, environment: EnvironmentIdentity) -> None:
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, False, (dependency(environment),)),
        root=board,
        expected_revision=0,
    )


def test_scope_authorization_result_and_actionable_blocker_persist_independently(
    board: Path, environment: EnvironmentIdentity
) -> None:
    write_manifest(board, environment)
    created = create_bootstrap("epic_001", scope(environment), root=board)

    assert (
        project_bootstrap("epic_001", root=board).state
        is BootstrapState.AWAITING_AUTHORIZATION
    )
    assert read_installation_approvals("epic_001", root=board) == ()
    assert read_dependency_check_history("epic_001", root=board) == ()

    with pytest.raises(DependencyBootstrapError, match="authenticated human"):
        authorize_feasibility(
            "epic_001",
            ("adapter_probe",),
            authorizer="plan-approved",  # type: ignore[arg-type]
            root=board,
            expected_revision=created.revision,
        )

    authorized = authorize_feasibility(
        "epic_001",
        ("adapter_probe",),
        authorizer=AuthenticatedHuman("human-42@example.test"),
        root=board,
        expected_revision=created.revision,
        authorized_at=datetime(2026, 11, 7, 12, tzinfo=timezone.utc),
    )
    checking = set_bootstrap_checking(
        "epic_001", root=board, expected_revision=authorized.revision
    )
    assert project_bootstrap("epic_001", root=board).state is BootstrapState.CHECKING

    checked = record_feasibility_result(
        "epic_001",
        "adapter_probe",
        environment=environment,
        outcome=FeasibilityOutcome.FAILED,
        redacted_output="adapter could not render the model",
        root=board,
        expected_revision=checking.revision,
        checked_at=datetime(2026, 11, 7, 12, 5, tzinfo=timezone.utc),
    )
    blocked = record_bootstrap_blockers(
        "epic_001",
        (
            BootstrapBlocker(
                dependency_id="dep_tool",
                artifact_id="adapter_probe",
                actor="human",
                last_checked_at=datetime(2026, 11, 7, 12, 5, tzinfo=timezone.utc),
                failed_operation="python bootstrap/adapter_probe.py",
                environment="ci-linux container sha256:runner",
                redacted_output="adapter could not render the model",
                investigation_steps="inspect the supported input format",
                install_steps=None,
                expected_verification="probe exits 0 and writes adapter-result.json",
                cleanup="remove bootstrap/adapter_probe.py and its result",
                ping_action="ping team after the input decision is recorded",
            ),
        ),
        root=board,
        expected_revision=checked.revision,
    )

    reloaded = read_bootstrap("epic_001", root=board)
    assert reloaded == blocked
    assert len(read_bootstrap_history("epic_001", root=board)) == 5
    assert reloaded.authorization.actor == "human-42@example.test"
    assert (
        reloaded.feasibility_results[0].authorization_id
        == reloaded.authorization.authorization_id
    )
    assert reloaded.blockers[0].ping_action.startswith("ping team")
    assert (
        project_bootstrap("epic_001", root=board).state
        is BootstrapState.DEPENDENCY_BLOCKED
    )
    assert read_installation_approvals("epic_001", root=board) == ()
    epic = read_doc("epic_001", root=board)
    assert epic.meta.tier == "epic"
    assert epic.meta.status == "active"


def test_circular_feasibility_must_be_in_scope_authorized_and_successful_before_ready(
    board: Path, environment: EnvironmentIdentity
) -> None:
    write_manifest(board, environment)
    invalid = BootstrapScope(
        manifest_revision=1,
        entries=scope(environment).entries,
        feasibility_artifacts=(),
        limits=scope(environment).limits,
    )
    with pytest.raises(DependencyBootstrapError, match="outside bootstrap scope"):
        create_bootstrap("epic_001", invalid, root=board)

    created = create_bootstrap("epic_001", scope(environment), root=board)
    authorized = authorize_feasibility(
        "epic_001",
        ("adapter_probe",),
        authorizer=AuthenticatedHuman("human-42@example.test"),
        root=board,
        expected_revision=created.revision,
    )
    wrong_environment = EnvironmentIdentity(
        "developer-host",
        "host",
        "linux",
        "x86_64",
        runner="developer-shell",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="host",
        runtime="python-3.12",
        container_digest="not_applicable",
    )
    with pytest.raises(DependencyBootstrapError, match="environment does not match"):
        record_feasibility_result(
            "epic_001",
            "adapter_probe",
            environment=wrong_environment,
            outcome=FeasibilityOutcome.SUCCEEDED,
            redacted_output="host-only result",
            root=board,
            expected_revision=authorized.revision,
        )
    successful = record_feasibility_result(
        "epic_001",
        "adapter_probe",
        environment=environment,
        outcome=FeasibilityOutcome.SUCCEEDED,
        redacted_output="adapter proof succeeded",
        root=board,
        expected_revision=authorized.revision,
    )
    assert successful.authorization is not None
    assert (
        project_bootstrap("epic_001", root=board).state
        is BootstrapState.DEPENDENCY_BLOCKED
    )

    admission = admit_dependency_check(
        "epic_001",
        "dep_tool",
        root=board,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=".tools/tool --version",
        lock_references=("adapter_probe",),
    )
    record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=board,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="tool 1.2.3",
        selected_version="1.2.3",
        integrity_reference="sha256:tool",
        lock_references=("adapter_probe",),
    )

    projection = project_bootstrap("epic_001", root=board)
    assert projection.state is BootstrapState.READY
    assert projection.blockers == ()
