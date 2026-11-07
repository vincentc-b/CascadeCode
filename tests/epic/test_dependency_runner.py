"""High-signal integration coverage for the bounded bootstrap runner."""

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
    BootstrapState,
    FeasibilityArtifact,
    authorize_feasibility,
    create_bootstrap,
    project_bootstrap,
)
from cascade.epic.dependency_evidence import (
    CheckOperationKind,
    CheckResult,
    project_current_dependency_evidence,
    read_dependency_check_history,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    write_dependency_manifest,
)
from cascade.epic.dependency_runner import (
    DependencyRunnerError,
    OperationFailure,
    OperationObservation,
    OperationRequest,
    run_dependency_operation,
    run_feasibility_proof,
)
from tests.support import add_doc, make_repo


class DeterministicExecutor:
    def __init__(self, *observations: OperationObservation) -> None:
        self.observations = list(observations)
        self.requests: list[OperationRequest] = []

    def execute(self, request: OperationRequest) -> OperationObservation:
        self.requests.append(request)
        return self.observations.pop(0)


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    return root


@pytest.fixture(params=("local", "container"))
def environment(request: pytest.FixtureRequest) -> EnvironmentIdentity:
    kind = str(request.param)
    return EnvironmentIdentity(
        f"{kind}-runner",
        kind,
        "linux",
        "x86_64",
        runner=f"deterministic-{kind}",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="owned-worktree" if kind == "local" else "container",
        runtime="python-3.12",
        container_digest=(
            "not_applicable" if kind == "local" else "sha256:runner-pinned"
        ),
    )


def dependency(environment: EnvironmentIdentity, **changes: object) -> DependencyEntry:
    entry = DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/releases/1.2.3/tool.tgz",
        digest="sha256:tool-pinned",
        target_environment=environment,
        install_scope="project-local .tools/tool",
        install_destination=".tools/tool",
        operation="install tool 1.2.3 into .tools/tool",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
        expected_verification_result="tool 1.2.3",
        feasibility_proof_requirements=("adapter_probe",),
        feasibility_proof_references=("adapter_probe",),
        lock_references=("adapter_probe",),
    )
    return replace(entry, **changes)


def prepare(
    board: Path,
    environment: EnvironmentIdentity,
    entry: DependencyEntry,
    *,
    approve_install: bool = True,
) -> tuple[int, str | None]:
    manifest = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, False, (entry,)),
        root=board,
        expected_revision=0,
    )
    created = create_bootstrap(
        "epic_001",
        BootstrapScope(
            manifest_revision=manifest.revision,
            entries=(
                BootstrapEntryScope(
                    dependency_id=entry.dependency_id,
                    source=entry.source,
                    integrity_reference=entry.integrity_reference or entry.digest,
                    setup_operation=entry.operation,
                    check_operation=entry.verification_recipe,
                    paths=(entry.install_destination or entry.install_scope,),
                    destination=entry.install_destination or entry.install_scope,
                    cleanup=entry.cleanup_plan,
                ),
            ),
            feasibility_artifacts=(
                FeasibilityArtifact(
                    artifact_id="adapter_probe",
                    operation="python bootstrap/adapter_probe.py",
                    target_environment=environment,
                    input_paths=("bootstrap/adapter_probe.py",),
                    output_paths=(".cascade/bootstrap/adapter-result.json",),
                    cleanup="remove probe and result",
                ),
            ),
            limits=BootstrapLimits(10, 3, 96, memory_bytes=64 * 1024 * 1024),
        ),
        root=board,
    )
    authorized = authorize_feasibility(
        "epic_001",
        ("adapter_probe",),
        authorizer=AuthenticatedHuman("reviewer@example.test"),
        root=board,
        expected_revision=created.revision,
    )
    approval_id = None
    if approve_install:
        approval_id = approve_dependency_installations(
            "epic_001",
            (entry.dependency_id,),
            approver=AuthenticatedHuman("installer@example.test"),
            approved_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
            root=board,
        )[0].approval_id
    return authorized.revision, approval_id


def observation(
    environment: EnvironmentIdentity,
    *,
    output: str = "tool 1.2.3",
    failure: OperationFailure | None = None,
    digest: str = "sha256:tool-pinned",
) -> OperationObservation:
    return OperationObservation(
        actual_environment=environment,
        exit_code=0 if failure is None else 1,
        output=output,
        selected_version="1.2.3",
        integrity_reference=digest,
        failure=failure,
    )


def test_local_and_container_setup_check_and_independent_feasibility(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    bootstrap_revision, approval_id = prepare(board, environment, entry)
    executor = DeterministicExecutor(
        observation(environment, output="installed token=super-secret"),
        observation(environment),
        OperationObservation(environment, 0, "adapter render succeeded"),
    )

    setup = run_dependency_operation(
        "epic_001",
        entry.dependency_id,
        operation_kind=CheckOperationKind.INSTALL,
        executor=executor,
        root=board,
        approval_reference=approval_id,
        bootstrap_revision=bootstrap_revision,
    )
    assert setup.completion.result is CheckResult.SUCCEEDED
    assert setup.completion.approval_reference == approval_id
    assert "super-secret" not in setup.completion.redacted_output
    # Installation is not the separately authorized adapter proof.
    assert project_bootstrap("epic_001", root=board).state is not BootstrapState.READY

    checked = run_dependency_operation(
        "epic_001",
        entry.dependency_id,
        operation_kind=CheckOperationKind.READ_ONLY,
        executor=executor,
        root=board,
    )
    assert checked.completion.actual_environment == environment
    assert project_bootstrap("epic_001", root=board).state is not BootstrapState.READY

    feasibility = run_feasibility_proof(
        "epic_001", "adapter_probe", executor=executor, root=board
    )
    assert feasibility.blocker is None
    assert project_bootstrap("epic_001", root=board).state is BootstrapState.READY
    assert executor.requests[0].limits.timeout_seconds == 10
    assert executor.requests[0].destination == ".tools/tool"
    assert executor.requests[2].operation == "python bootstrap/adapter_probe.py"


@pytest.mark.parametrize(
    "failure",
    (
        OperationFailure.OFFLINE_SOURCE,
        OperationFailure.PROMPT_UNSUPPORTED,
        OperationFailure.TIMEOUT,
    ),
)
def test_setup_failure_paths_are_completed_with_actionable_bounded_evidence(
    board: Path, environment: EnvironmentIdentity, failure: OperationFailure
) -> None:
    entry = dependency(environment)
    bootstrap_revision, approval_id = prepare(board, environment, entry)
    noisy = "password=hunter2 " + ("x" * 300)
    executor = DeterministicExecutor(
        observation(environment, output=noisy, failure=failure)
    )

    result = run_dependency_operation(
        "epic_001",
        entry.dependency_id,
        operation_kind=CheckOperationKind.INSTALL,
        executor=executor,
        root=board,
        approval_reference=approval_id,
        bootstrap_revision=bootstrap_revision,
    )

    assert result.completion.result is CheckResult.FAILED
    assert result.blocker is not None and result.blocker.code is failure
    assert result.blocker.next_action
    assert "hunter2" not in result.completion.redacted_output
    assert len(result.completion.redacted_output.encode()) <= 96
    assert len(read_dependency_check_history("epic_001", root=board)) == 2


def test_checksum_and_wrong_environment_are_not_current_readiness(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    prepare(board, environment, entry, approve_install=False)
    wrong = replace(environment, runtime="python-3.11")
    executor = DeterministicExecutor(
        observation(environment, digest="sha256:tampered"),
        observation(wrong),
    )

    checksum = run_dependency_operation(
        "epic_001",
        entry.dependency_id,
        operation_kind=CheckOperationKind.READ_ONLY,
        executor=executor,
        root=board,
    )
    mismatched = run_dependency_operation(
        "epic_001",
        entry.dependency_id,
        operation_kind=CheckOperationKind.READ_ONLY,
        executor=executor,
        root=board,
    )

    assert checksum.blocker is not None
    assert checksum.blocker.code is OperationFailure.CHECKSUM_MISMATCH
    assert mismatched.blocker is not None
    assert mismatched.blocker.code is OperationFailure.WRONG_ENVIRONMENT
    assert project_current_dependency_evidence("epic_001", root=board).ready is False


def test_implicit_pull_never_reaches_executor_without_exact_approval(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    bootstrap_revision, _ = prepare(board, environment, entry)
    executor = DeterministicExecutor(observation(environment))

    with pytest.raises(InstallationApprovalDenied):
        run_dependency_operation(
            "epic_001",
            entry.dependency_id,
            operation_kind=CheckOperationKind.IMPLICIT_PULL,
            executor=executor,
            root=board,
            bootstrap_revision=bootstrap_revision,
        )
    assert executor.requests == []


def test_moving_reference_is_rejected_before_admission_or_execution(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(
        environment,
        version="latest",
        source="https://tool.example/releases/latest/tool.tgz",
    )
    prepare(board, environment, entry, approve_install=False)
    executor = DeterministicExecutor(observation(environment))

    with pytest.raises(DependencyRunnerError, match="moving latest"):
        run_dependency_operation(
            "epic_001",
            entry.dependency_id,
            operation_kind=CheckOperationKind.READ_ONLY,
            executor=executor,
            root=board,
        )
    assert executor.requests == []
    assert read_dependency_check_history("epic_001", root=board) == ()
