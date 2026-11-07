"""Integration coverage for deduplicated dependency resume and recovery."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from cascade.epic.dependency_approvals import (
    AuthenticatedHuman,
    approve_dependency_installations,
)
from cascade.epic.dependency_bootstrap import (
    BootstrapEntryScope,
    BootstrapLimits,
    BootstrapScope,
    FeasibilityArtifact,
    authorize_feasibility,
    create_bootstrap,
)
from cascade.epic.dependency_evidence import (
    CheckAdmission,
    CheckCompletion,
    CheckOperationKind,
    CheckResult,
    admit_dependency_check,
    read_dependency_check_history,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    write_dependency_manifest,
)
from cascade.epic.dependency_resume import resume_dependency_bootstrap
from cascade.epic.dependency_runner import (
    OperationFailure,
    OperationObservation,
    OperationRequest,
)
from tests.support import add_doc, make_repo


class Executor:
    def __init__(self, *observations: OperationObservation) -> None:
        self.observations = list(observations)
        self.requests: list[OperationRequest] = []

    def execute(self, request: OperationRequest) -> OperationObservation:
        self.requests.append(request)
        return self.observations.pop(0)


class BlockingExecutor(Executor):
    def __init__(self, *observations: OperationObservation) -> None:
        super().__init__(*observations)
        self.started = Event()
        self.release = Event()

    def execute(self, request: OperationRequest) -> OperationObservation:
        if not self.requests:
            self.started.set()
            assert self.release.wait(5)
        return super().execute(request)


def environment() -> EnvironmentIdentity:
    return EnvironmentIdentity(
        "resume-ci",
        "container",
        "linux",
        "x86_64",
        runner="resume-runner",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:resume-runner",
    )


def dependency(target: EnvironmentIdentity) -> DependencyEntry:
    return DependencyEntry(
        dependency_id="dep_tool",
        version="1.2.3",
        source="https://tool.example/1.2.3/tool.tgz",
        digest="sha256:tool",
        target_environment=target,
        install_scope="project-local",
        install_destination=".tools/tool",
        operation="install tool 1.2.3 into .tools/tool",
        cleanup_plan="remove .tools/tool",
        verification_recipe=".tools/tool --version",
        expected_verification_result="tool 1.2.3",
        feasibility_proof_requirements=("adapter_probe",),
        feasibility_proof_references=("adapter_probe",),
        lock_references=("adapter_probe",),
    )


def prepare(
    tmp_path: Path, *, empty: bool = False
) -> tuple[Path, EnvironmentIdentity, DependencyEntry | None, str | None]:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    target = environment()
    entry = None if empty else dependency(target)
    manifest = write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(target, None, empty, () if empty else (entry,)),
        root=root,
        expected_revision=0,
    )
    artifacts = (
        ()
        if empty
        else (
            FeasibilityArtifact(
                "adapter_probe",
                "python bootstrap/probe.py",
                target,
                ("bootstrap/probe.py",),
                (".cascade/bootstrap/result.json",),
                "remove probe output",
            ),
        )
    )
    entries = (
        ()
        if empty
        else (
            BootstrapEntryScope(
                entry.dependency_id,
                entry.source,
                entry.integrity_reference or entry.digest,
                entry.operation,
                entry.verification_recipe,
                (entry.install_destination or ".tools/tool",),
                entry.install_destination or ".tools/tool",
                entry.cleanup_plan,
            ),
        )
    )
    bootstrap = create_bootstrap(
        "epic_001",
        BootstrapScope(
            manifest.revision, entries, artifacts, BootstrapLimits(10, 3, 4096)
        ),
        root=root,
    )
    approval_id = None
    if entry is not None:
        authorize_feasibility(
            "epic_001",
            ("adapter_probe",),
            authorizer=AuthenticatedHuman("reviewer@example.test"),
            root=root,
            expected_revision=bootstrap.revision,
        )
        approval_id = approve_dependency_installations(
            "epic_001",
            (entry.dependency_id,),
            approver=AuthenticatedHuman("installer@example.test"),
            approved_at=datetime(2026, 11, 7, tzinfo=timezone.utc),
            root=root,
        )[0].approval_id
    return root, target, entry, approval_id


def observed(
    target: EnvironmentIdentity,
    *,
    failure: OperationFailure | None = None,
) -> OperationObservation:
    return OperationObservation(
        target,
        0 if failure is None else 1,
        "tool 1.2.3" if failure is None else "tool not installed",
        "1.2.3",
        "sha256:tool",
        failure,
    )


def test_human_ping_installs_rechecks_and_duplicate_delivery_is_a_noop(
    tmp_path: Path,
) -> None:
    root, target, entry, approval_id = prepare(tmp_path)
    assert entry is not None and approval_id is not None
    executor = Executor(
        observed(target, failure=OperationFailure.COMMAND_FAILED),
        observed(target),
        observed(target),
        OperationObservation(target, 0, "adapter succeeded"),
    )
    kickoffs = []

    first = resume_dependency_bootstrap(
        "epic_001",
        "ping-1",
        executor=executor,
        root=root,
        approval_references={entry.dependency_id: approval_id},
        kickoff=kickoffs.append,
    )
    duplicate = resume_dependency_bootstrap(
        "epic_001",
        "ping-1",
        executor=executor,
        root=root,
        approval_references={entry.dependency_id: approval_id},
        kickoff=kickoffs.append,
    )

    assert first.ready and first.planning_resumed
    assert duplicate.ready and duplicate.deduplicated
    assert not duplicate.planning_resumed
    assert [row.operation for row in executor.requests] == [
        entry.verification_recipe,
        entry.operation,
        entry.verification_recipe,
        "python bootstrap/probe.py",
    ]
    assert len(kickoffs) == 1


def test_restart_reconciles_partial_setup_before_retrying(tmp_path: Path) -> None:
    root, target, entry, approval_id = prepare(tmp_path)
    assert entry is not None and approval_id is not None
    bootstrap_revision = create_or_current_revision(root)
    dangling = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=root,
        operation_kind=CheckOperationKind.INSTALL,
        exact_operation=entry.operation,
        approval_reference=approval_id,
        bootstrap_revision=bootstrap_revision,
        attempt_id="attempt_interrupted_setup",
    )
    executor = Executor(
        observed(target),
        OperationObservation(target, 0, "adapter succeeded"),
    )

    result = resume_dependency_bootstrap(
        "epic_001",
        "restart-1",
        executor=executor,
        root=root,
        kickoff=lambda _reason: None,
    )

    assert result.ready
    assert [request.operation for request in executor.requests] == [
        entry.verification_recipe,
        "python bootstrap/probe.py",
    ]
    history = read_dependency_check_history("epic_001", root=root)
    reconciled = next(
        row
        for row in history
        if isinstance(row, CheckCompletion) and row.attempt_id == dangling.attempt_id
    )
    assert reconciled.result is CheckResult.SUCCEEDED
    assert sum(isinstance(row, CheckAdmission) for row in history) == 2


def test_concurrent_duplicate_pings_share_one_revalidation(tmp_path: Path) -> None:
    root, target, _, _ = prepare(tmp_path)
    executor = BlockingExecutor(
        observed(target, failure=OperationFailure.COMMAND_FAILED),
        observed(target),
        observed(target),
        OperationObservation(target, 0, "adapter succeeded"),
    )
    results = []

    def run() -> None:
        results.append(
            resume_dependency_bootstrap(
                "epic_001",
                "ping-concurrent",
                executor=executor,
                root=root,
                kickoff=lambda _reason: None,
            )
        )

    first = Thread(target=run)
    second = Thread(target=run)
    first.start()
    assert executor.started.wait(5)
    second.start()
    executor.release.set()
    first.join(5)
    second.join(5)

    assert len(results) == 2
    assert len(executor.requests) == 4
    assert sum(result.planning_resumed for result in results) == 1
    assert sum(result.deduplicated for result in results) == 1


def test_stale_supplied_approval_never_reaches_setup_executor(tmp_path: Path) -> None:
    root, target, entry, _ = prepare(tmp_path)
    assert entry is not None
    executor = Executor(
        observed(target, failure=OperationFailure.COMMAND_FAILED),
        OperationObservation(target, 0, "adapter succeeded"),
    )

    result = resume_dependency_bootstrap(
        "epic_001",
        "ping-stale",
        executor=executor,
        root=root,
        approval_references={entry.dependency_id: "stale-approval"},
    )

    assert not result.ready
    assert result.recovery_state == "awaiting_human_gate"
    assert entry.operation not in [request.operation for request in executor.requests]


def test_explicit_empty_manifest_resumes_planning_without_provider_work(
    tmp_path: Path,
) -> None:
    root, _, _, _ = prepare(tmp_path, empty=True)
    executor = Executor()
    kickoffs = []

    result = resume_dependency_bootstrap(
        "epic_001", "ping-empty", executor=executor, root=root, kickoff=kickoffs.append
    )

    assert result.ready and result.planning_resumed
    assert executor.requests == []
    assert len(kickoffs) == 1


def create_or_current_revision(root: Path) -> int:
    from cascade.epic.dependency_bootstrap import read_bootstrap

    snapshot = read_bootstrap("epic_001", root=root)
    assert snapshot is not None
    return snapshot.revision
