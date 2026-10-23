"""Disposable probe workspace harness (feat_012_003 / task_012_003_001)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cascade.probe import (
    ProbeError,
    ProbeExecutionBounds,
    ProbeTimeoutError,
    allocate_probe_workspace,
    is_live_board_path,
    live_board_roots,
    probe_workspace,
    reject_live_board_mutation_target,
    smoke_probe_harness,
)
from cascade.probe.bounds import ProbeDeadline
from cascade.probe.harness import ProbeHarnessOptions, bootstrap_probe_repository


def test_live_board_detects_product_checkout() -> None:
    roots = live_board_roots()
    assert roots
    assert is_live_board_path(roots[0])
    assert is_live_board_path(roots[0] / "docs" / "epics" / "1_backlog")


def test_rejects_live_board_mutation_target() -> None:
    live = live_board_roots()[0]
    with pytest.raises(ProbeError, match="live board"):
        reject_live_board_mutation_target(live)


def test_allocate_creates_git_board_and_runtime(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        root = workspace.root
        assert root.is_dir()
        assert (root / ".git").is_dir()
        assert (root / "cascade.toml").is_file()
        assert (root / "docs" / "tasks" / "2_active").is_dir()
        assert (root / ".cascade").name == ".cascade"
        workspace.validate_mutation_target(root / "docs")
    assert not root.exists()


def test_mutation_outside_workspace_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        with pytest.raises(ProbeError, match="inside workspace"):
            workspace.validate_mutation_target(tmp_path / "outside")


def test_debug_retention_keeps_workspace(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    retained = smoke_probe_harness(retain_artifacts=True, parent_dir=parent)
    assert retained is not None
    root = retained.root
    assert root.is_dir()
    retained.cleanup(force=True)
    assert not root.exists()


def test_bootstrap_refuses_live_board(tmp_path: Path) -> None:
    live = live_board_roots()[0]
    with pytest.raises(ProbeError, match="live board"):
        bootstrap_probe_repository(live / "must-not-create")


def test_parent_on_live_board_rejected(tmp_path: Path) -> None:
    live = live_board_roots()[0]
    with pytest.raises(ProbeError, match="live board"):
        allocate_probe_workspace(ProbeHarnessOptions(parent_dir=live / "probe-nest"))


def test_probe_deadline_raises_without_sleeping() -> None:
    deadline = ProbeDeadline(start=0.0, max_seconds=1.0)
    with pytest.MonkeyPatch.context() as monkeypatch:
        times = iter([0.0, 2.0])
        monkeypatch.setattr("cascade.probe.bounds.time.monotonic", lambda: next(times))
        deadline.check(phase="unit")
        with pytest.raises(ProbeTimeoutError):
            deadline.check(phase="unit")


def test_invalid_probe_max_seconds_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASCADE_PROBE_MAX_SECONDS", "nope")
    with pytest.raises(ProbeTimeoutError):
        ProbeExecutionBounds.from_env()


def test_cascade_probe_prepare_cli_smoke(tmp_path: Path) -> None:
    parent = tmp_path / "cli-parent"
    parent.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "probe",
            "prepare",
            "--parent",
            str(parent),
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    assert payload["ok"] is True
    assert payload["retained"] is False
    assert not Path(payload["workspace"]).exists()


def test_cascade_probe_prepare_debug_retain(tmp_path: Path) -> None:
    parent = tmp_path / "cli-parent"
    parent.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "probe",
            "prepare",
            "--parent",
            str(parent),
            "--debug-retain",
            "--json",
        ],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout.strip())
    root = Path(payload["workspace"])
    assert payload["retained"] is True
    assert root.is_dir()
    subprocess.run(["rm", "-rf", str(root)], check=True)
