"""End-to-end lifecycle probe: success, stall, isolation, cleanup (feat_012_003)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from cascade.probe import live_board_roots, probe_workspace
from cascade.probe.lifecycle import run_lifecycle_probe

_EXPECTED_PHASES = frozenset(
    {
        "synthetic_lifecycle",
        "readiness_transitions",
        "watchdog_reconciliation",
        "convergence_detection",
        "intentional_stall",
        "stall_diagnostic",
        "stall_recovery",
        "stall_re_emit",
    }
)

_STALL_PHASES = frozenset(
    {
        "intentional_stall",
        "stall_diagnostic",
        "stall_recovery",
        "stall_re_emit",
    }
)


def test_run_lifecycle_probe_reports_all_phases(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        report = run_lifecycle_probe(workspace)
    assert report.ok, report.phases
    phase_names = {row.phase for row in report.phases}
    assert phase_names >= _EXPECTED_PHASES
    assert report.failing_phase is None


def test_run_lifecycle_probe_stall_and_diagnostic_phases_ok(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        report = run_lifecycle_probe(workspace)
    assert report.ok
    by_phase = {row.phase: row for row in report.phases}
    for name in _STALL_PHASES:
        assert by_phase[name].ok, by_phase[name].detail
    assert by_phase["stall_diagnostic"].detail == ""


def test_run_lifecycle_probe_finishes_within_bounds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CASCADE_PROBE_MAX_SECONDS", "300")
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        report = run_lifecycle_probe(workspace)
        assert report.ok
        assert workspace.deadline.remaining() > 0


def test_run_lifecycle_probe_identifies_failing_phase(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()

    def broken_success(root, *, deadline_check):
        from cascade.probe.report import ProbePhaseResult

        return (
            ProbePhaseResult(phase="synthetic_lifecycle", ok=False, detail="injected"),
        )

    monkeypatch.setattr("cascade.probe.lifecycle._exercise_success_path", broken_success)
    monkeypatch.setattr(
        "cascade.probe.lifecycle._exercise_stall_and_recovery",
        lambda root, *, deadline_check: (),
    )

    with probe_workspace(parent_dir=parent) as workspace:
        report = run_lifecycle_probe(workspace)
    assert not report.ok
    assert report.failing_phase == "synthetic_lifecycle"


def test_lifecycle_probe_does_not_touch_live_board(tmp_path: Path) -> None:
    live = live_board_roots()[0]
    marker = live / "docs" / "tasks" / "1_backlog"
    assert marker.is_dir()
    before = marker.stat().st_mtime_ns
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        report = run_lifecycle_probe(workspace)
    assert report.ok
    assert marker.stat().st_mtime_ns == before


def test_cascade_probe_run_cli_json(tmp_path: Path) -> None:
    parent = tmp_path / "cli-parent"
    parent.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "probe",
            "run",
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
    assert payload["failing_phase"] is None
    assert payload["retained"] is False
    assert not Path(payload["workspace"]).exists()
    phase_names = {row["phase"] for row in payload["phases"]}
    assert phase_names >= _EXPECTED_PHASES
    assert all(row["ok"] for row in payload["phases"])


def test_cascade_probe_run_debug_retain(tmp_path: Path) -> None:
    parent = tmp_path / "cli-parent"
    parent.mkdir()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "cascade.cli",
            "probe",
            "run",
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
    assert payload["ok"] is True
    assert root.is_dir()
    subprocess.run(["rm", "-rf", str(root)], check=True)
