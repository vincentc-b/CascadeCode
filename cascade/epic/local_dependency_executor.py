"""Bounded dependency executor for the ordinary local workspace runtime."""

from __future__ import annotations

import os
import platform
import resource
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from cascade.epic.dependency_manifests import (
    EnvironmentIdentity,
    environment_identities_match,
)
from cascade.epic.dependency_runner import (
    OperationFailure,
    OperationObservation,
    OperationRequest,
)


def local_environment_identity(root: Path) -> EnvironmentIdentity:
    resolved = Path(root).resolve()
    return EnvironmentIdentity(
        environment_id=platform.node() or "local-host",
        kind="host",
        platform=platform.system().lower(),
        architecture=platform.machine().lower(),
        runner=platform.node() or "local-host",
        repository=str(resolved),
        worktree=str(resolved),
        sandbox="host",
        runtime=str(Path(sys.executable).resolve()),
        container_digest="not_applicable",
    )


class LocalBoundedDependencyExecutor:
    """Run an exact reviewed operation only when its target is this host."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def execute(self, request: OperationRequest) -> OperationObservation:
        actual = local_environment_identity(self.root)
        if not environment_identities_match(request.target_environment, actual):
            return OperationObservation(
                actual,
                126,
                "refused: requested dependency environment is not this workspace host",
                failure=OperationFailure.WRONG_ENVIRONMENT,
            )

        def limits() -> None:
            os.setsid()
            cpu = max(1, request.limits.timeout_seconds)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
            if request.limits.memory_bytes is not None:
                memory = request.limits.memory_bytes
                resource.setrlimit(resource.RLIMIT_AS, (memory, memory))

        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                ["/bin/sh", "-c", request.operation],
                cwd=self.root,
                stdin=subprocess.DEVNULL,
                stdout=output,
                stderr=subprocess.STDOUT,
                start_new_session=False,
                preexec_fn=limits,
                close_fds=True,
            )
            failure = None
            try:
                process.wait(timeout=request.limits.timeout_seconds)
            except subprocess.TimeoutExpired:
                failure = OperationFailure.TIMEOUT
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            output.seek(0)
            raw = output.read(request.limits.max_output_bytes + 1)
        truncated = len(raw) > request.limits.max_output_bytes
        text = raw[: request.limits.max_output_bytes].decode("utf-8", errors="replace")
        if truncated:
            text += "\n[output truncated]"
        if failure is None and process.returncode != 0:
            failure = OperationFailure.COMMAND_FAILED
        return OperationObservation(
            actual,
            process.returncode,
            text,
            selected_version=request.selected_version,
            integrity_reference=request.integrity_reference,
            failure=failure,
        )
