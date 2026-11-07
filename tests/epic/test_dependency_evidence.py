"""Persistence-level contracts for dependency check evidence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.epic.dependency_evidence import (
    CheckAttemptAlreadyCompleted,
    CheckOperationKind,
    CheckResult,
    DependencyEvidenceError,
    admit_dependency_check,
    create_dependency_evidence_snapshot,
    read_dependency_check_history,
    read_dependency_evidence_snapshots,
    record_trusted_dependency_check_completion,
    project_current_dependency_evidence,
)
from cascade.epic.dependency_manifests import (
    DependencyEntry,
    DependencyManifestDraft,
    EnvironmentIdentity,
    write_dependency_manifest,
)
from tests.support import add_doc, make_repo

NOW = datetime(2026, 11, 7, 12, tzinfo=timezone.utc)


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
        runner="github-actions",
        repository="example/cascade",
        worktree="/work/cascade",
        sandbox="container",
        runtime="python-3.12",
        container_digest="sha256:runner-image",
    )


def dependency(
    environment: EnvironmentIdentity,
    dependency_id: str = "dep_python",
    *,
    version: str = "3.12.7",
    recipe: str = "python --version",
) -> DependencyEntry:
    return DependencyEntry(
        dependency_id=dependency_id,
        version=version,
        source=f"https://packages.example/{dependency_id}/{version}",
        digest=f"sha256:{dependency_id}-{version}",
        target_environment=environment,
        install_scope="project toolchain",
        operation=f"install {dependency_id} {version}",
        cleanup_plan=f"remove {dependency_id}",
        verification_recipe=recipe,
    )


def write_manifest(
    board: Path,
    environment: EnvironmentIdentity,
    entries: tuple[DependencyEntry, ...],
    *,
    expected_revision: int,
) -> None:
    write_dependency_manifest(
        "epic_001",
        DependencyManifestDraft(environment, None, False, entries),
        root=board,
        expected_revision=expected_revision,
        recorded_at=NOW + timedelta(minutes=expected_revision),
    )


def complete(
    board: Path,
    environment: EnvironmentIdentity,
    entry: DependencyEntry,
    *,
    admitted_at: datetime = NOW,
    completed_at: datetime = NOW + timedelta(seconds=1),
):
    admission = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=entry.verification_recipe,
        lock_references=("uv.lock:python",),
        admitted_at=admitted_at,
    )
    completion = record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=board,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="Python 3.12.7\n[token redacted]",
        selected_version=entry.version,
        integrity_reference=entry.digest,
        lock_references=("uv.lock:python",),
        completed_at=completed_at,
    )
    return admission, completion


def test_attempt_events_are_append_only_reloadable_and_setup_requires_approval(
    board: Path, environment: EnvironmentIdentity
) -> None:
    entry = dependency(environment)
    write_manifest(board, environment, (entry,), expected_revision=0)

    admission, completion = complete(board, environment, entry)
    assert read_dependency_check_history("epic_001", root=board) == (
        admission,
        completion,
    )
    assert completion.attempt_id == admission.attempt_id
    assert completion.redacted_output.endswith("[token redacted]")
    assert admission.selected_version == entry.version
    assert admission.integrity_reference == entry.digest
    assert admission.lock_references == ("uv.lock:python",)
    assert completion.lock_references == ("uv.lock:python",)

    with pytest.raises(CheckAttemptAlreadyCompleted):
        record_trusted_dependency_check_completion(
            "epic_001",
            admission.attempt_id,
            root=board,
            actual_environment=environment,
            result=CheckResult.SUCCEEDED,
            redacted_output="duplicate",
            selected_version=entry.version,
            integrity_reference=entry.digest,
        )
    with pytest.raises(DependencyEvidenceError, match="approval reference"):
        admit_dependency_check(
            "epic_001",
            entry.dependency_id,
            root=board,
            operation_kind=CheckOperationKind.INSTALL,
            exact_operation=entry.operation,
        )
    setup = admit_dependency_check(
        "epic_001",
        entry.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.INSTALL,
        exact_operation=entry.operation,
        approval_reference="approval-human-001",
    )
    assert setup.approval_reference == "approval-human-001"


@pytest.mark.parametrize(
    ("actual", "reason"),
    [
        (
            EnvironmentIdentity("developer-laptop", "host", "linux", "x86_64"),
            "mismatched_environment",
        ),
        (
            EnvironmentIdentity("unknown", "container", "linux", "x86_64"),
            "unknown_environment",
        ),
    ],
)
def test_projection_rejects_mismatched_and_unknown_actual_environments(
    board: Path,
    environment: EnvironmentIdentity,
    actual: EnvironmentIdentity,
    reason: str,
) -> None:
    entry = dependency(environment)
    write_manifest(board, environment, (entry,), expected_revision=0)
    complete(board, actual, entry)

    projection = project_current_dependency_evidence("epic_001", root=board)
    assert not projection.ready
    assert [(row.dependency_id, row.reason) for row in projection.blockers] == [
        (entry.dependency_id, reason)
    ]


def test_completion_of_stale_admission_is_historical_not_current(
    board: Path, environment: EnvironmentIdentity
) -> None:
    original = dependency(environment)
    write_manifest(board, environment, (original,), expected_revision=0)
    admission = admit_dependency_check(
        "epic_001",
        original.dependency_id,
        root=board,
        operation_kind=CheckOperationKind.READ_ONLY,
        exact_operation=original.verification_recipe,
        admitted_at=NOW,
    )
    revised = replace(original, verification_recipe="python -VV")
    write_manifest(board, environment, (revised,), expected_revision=1)
    completion = record_trusted_dependency_check_completion(
        "epic_001",
        admission.attempt_id,
        root=board,
        actual_environment=environment,
        result=CheckResult.SUCCEEDED,
        redacted_output="Python 3.12.7",
        selected_version=revised.version,
        integrity_reference=revised.digest,
        completed_at=NOW + timedelta(minutes=2),
    )

    assert len(read_dependency_check_history("epic_001", root=board)) == 2
    assert completion.recipe_revision != admission.recipe_revision
    projection = project_current_dependency_evidence("epic_001", root=board)
    assert [(row.dependency_id, row.reason) for row in projection.blockers] == [
        (original.dependency_id, "stale_admission")
    ]


def test_revision_change_selectively_invalidates_and_snapshots_remain_immutable(
    board: Path, environment: EnvironmentIdentity
) -> None:
    python = dependency(environment)
    node = dependency(
        environment, "dep_node", version="22.1.0", recipe="node --version"
    )
    write_manifest(board, environment, (python, node), expected_revision=0)
    python_attempt, _ = complete(board, environment, python)
    node_attempt, _ = complete(
        board,
        environment,
        node,
        admitted_at=NOW + timedelta(seconds=2),
        completed_at=NOW + timedelta(seconds=3),
    )

    snapshot = create_dependency_evidence_snapshot(
        "epic_001", root=board, created_at=NOW + timedelta(seconds=4)
    )
    assert [row.attempt_id for row in snapshot.accepted] == [
        python_attempt.attempt_id,
        node_attempt.attempt_id,
    ]

    revised_python = replace(python, verification_recipe="python -VV")
    write_manifest(board, environment, (revised_python, node), expected_revision=1)
    projection = project_current_dependency_evidence("epic_001", root=board)

    assert [(row.dependency_id, row.reason) for row in projection.blockers] == [
        (python.dependency_id, "stale_check")
    ]
    assert [(row.dependency_id, row.attempt_id) for row in projection.accepted] == [
        (node.dependency_id, node_attempt.attempt_id)
    ]
    assert read_dependency_evidence_snapshots("epic_001", root=board) == (snapshot,)
    assert snapshot.manifest_revision == 1
    assert len(snapshot.accepted) == 2
