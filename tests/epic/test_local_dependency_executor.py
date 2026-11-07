"""Runtime checks for the ordinary workspace dependency executor."""

from pathlib import Path

from cascade.epic.dependency_bootstrap import BootstrapLimits
from cascade.epic.dependency_manifests import EnvironmentIdentity
from cascade.epic.local_dependency_executor import (
    LocalBoundedDependencyExecutor,
    local_environment_identity,
)
from cascade.epic.dependency_runner import (
    OperationFailure,
    OperationRequest,
)


def _request(root: Path, operation: str, *, target=None) -> OperationRequest:
    return OperationRequest(
        operation=operation,
        operation_kind=None,
        target_environment=target or local_environment_identity(root),
        source="https://example.test/tool",
        selected_version="1.2.3",
        integrity_reference="sha256:tool",
        allowed_paths=(".cascade/probe",),
        destination=None,
        cleanup="remove .cascade/probe",
        limits=BootstrapLimits(5, 1, 1024),
    )


def test_local_executor_runs_in_matching_workspace_with_bounded_output(
    tmp_path: Path,
) -> None:
    executor = LocalBoundedDependencyExecutor(tmp_path)
    observation = executor.execute(_request(tmp_path, "printf 'tool 1.2.3'"))

    assert observation.exit_code == 0
    assert observation.failure is None
    assert observation.output == "tool 1.2.3"
    assert observation.selected_version == "1.2.3"
    assert observation.integrity_reference == "sha256:tool"


def test_local_executor_refuses_mismatched_environment_before_dispatch(
    tmp_path: Path,
) -> None:
    executor = LocalBoundedDependencyExecutor(tmp_path)
    marker = tmp_path / "must-not-exist"
    target = EnvironmentIdentity(
        "container",
        "container",
        "linux",
        "x86_64",
        runner="container-runner",
        repository=str(tmp_path),
        worktree=str(tmp_path),
        sandbox="container",
        runtime="java-25",
        container_digest="sha256:image",
    )

    observation = executor.execute(
        _request(tmp_path, f"touch {marker}", target=target)
    )

    assert observation.failure is OperationFailure.WRONG_ENVIRONMENT
    assert not marker.exists()
