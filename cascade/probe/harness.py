"""Disposable git workspace and Cascade board for the lifecycle readiness probe."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from cascade.workspace import WorkspaceError, WorkspaceRoot, init_workspace
from cascade.probe.bounds import ProbeDeadline, ProbeExecutionBounds
from cascade.probe.errors import ProbeError
from cascade.probe.live_board import is_live_board_path, reject_live_board_mutation_target

_PROBE_PARENT_NAME = "cascade-probe"


@dataclass(frozen=True, slots=True)
class ProbeHarnessOptions:
    """Operator controls for allocating a disposable probe workspace."""

    retain_artifacts: bool = False
    bounds: ProbeExecutionBounds | None = None
    parent_dir: Path | None = None


@dataclass(frozen=True, slots=True)
class ProbeWorkspace:
    """Temporary git repository with an initialized Cascade board."""

    root: Path
    workspace: WorkspaceRoot
    retain_artifacts: bool
    deadline: ProbeDeadline

    def validate_mutation_target(self, path: Path) -> Path:
        """Ensure ``path`` is inside this workspace and not the live board."""

        resolved = Path(path).resolve()
        reject_live_board_mutation_target(resolved)
        probe_root = self.root.resolve()
        if resolved != probe_root and probe_root not in resolved.parents:
            raise ProbeError(
                f"probe mutation target must stay inside workspace {probe_root}: {path}"
            )
        return resolved

    def cleanup(self, *, force: bool = False) -> None:
        """Remove the workspace directory unless debug retention was requested."""

        if self.retain_artifacts and not force:
            return
        shutil.rmtree(self.root, ignore_errors=True)


def default_probe_parent_dir() -> Path:
    """Parent directory for newly allocated probe workspaces (outside the live board)."""

    base = Path(tempfile.gettempdir()) / _PROBE_PARENT_NAME
    base.mkdir(parents=True, exist_ok=True)
    reject_live_board_mutation_target(base)
    return base


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def bootstrap_probe_repository(root: Path) -> WorkspaceRoot:
    """Initialize git, board layout, and an initial commit under ``root``."""

    reject_live_board_mutation_target(root)
    root.mkdir(parents=True, exist_ok=False)
    _git(root, "init", "-b", "main")
    _git(root, "config", "user.email", "probe@cascade.local")
    _git(root, "config", "user.name", "Cascade Probe")
    try:
        ws = init_workspace(root)
    except WorkspaceError as exc:
        raise ProbeError(str(exc)) from exc
    readme = root / "README.md"
    if not readme.is_file():
        readme.write_text("cascade lifecycle probe workspace\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-m", "probe workspace bootstrap")
    return ws


def allocate_probe_workspace(options: ProbeHarnessOptions | None = None) -> ProbeWorkspace:
    """Create a fresh disposable workspace (caller must ``cleanup`` or use the context manager)."""

    opts = options or ProbeHarnessOptions()
    bounds = opts.bounds or ProbeExecutionBounds.from_env()
    deadline = bounds.deadline()
    deadline.check(phase="probe allocation")

    parent = (opts.parent_dir or default_probe_parent_dir()).resolve()
    reject_live_board_mutation_target(parent)
    if is_live_board_path(parent):
        raise ProbeError(f"probe parent directory cannot be on the live board: {parent}")

    run_id = uuid.uuid4().hex
    root = (parent / f"run-{run_id}").resolve()
    if root.exists():
        raise ProbeError(f"probe workspace path already exists: {root}")

    ws = bootstrap_probe_repository(root)
    return ProbeWorkspace(
        root=root,
        workspace=ws,
        retain_artifacts=opts.retain_artifacts,
        deadline=deadline,
    )


@contextmanager
def probe_workspace(
    *,
    retain_artifacts: bool = False,
    bounds: ProbeExecutionBounds | None = None,
    parent_dir: Path | None = None,
) -> Iterator[ProbeWorkspace]:
    """Allocate a probe workspace and clean it up on exit unless ``retain_artifacts``."""

    opts = ProbeHarnessOptions(
        retain_artifacts=retain_artifacts,
        bounds=bounds,
        parent_dir=parent_dir,
    )
    workspace = allocate_probe_workspace(opts)
    try:
        yield workspace
    finally:
        workspace.cleanup()


def _verify_probe_board_layout(workspace: ProbeWorkspace) -> None:
    workspace.deadline.check(phase="probe smoke")
    for rel in (
        "docs/epics/1_backlog",
        "docs/features/1_backlog",
        "docs/tasks/1_backlog",
    ):
        column = workspace.root / rel
        if not column.is_dir():
            raise ProbeError(f"probe workspace missing board layout: {column}")


def smoke_probe_harness(
    *,
    retain_artifacts: bool = False,
    parent_dir: Path | None = None,
) -> ProbeWorkspace | None:
    """Allocate and verify board layout; cleanup unless ``retain_artifacts``.

    Returns the workspace only when ``retain_artifacts`` is true (caller must cleanup).
    """

    if retain_artifacts:
        workspace = allocate_probe_workspace(
            ProbeHarnessOptions(retain_artifacts=True, parent_dir=parent_dir)
        )
        _verify_probe_board_layout(workspace)
        return workspace

    with probe_workspace(parent_dir=parent_dir) as workspace:
        _verify_probe_board_layout(workspace)
    return None
