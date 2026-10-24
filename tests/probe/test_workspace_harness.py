"""Probe harness guardrails not covered by the lifecycle end-to-end run."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.probe import (
    ProbeError,
    ProbeExecutionBounds,
    ProbeTimeoutError,
    allocate_probe_workspace,
    is_live_board_path,
    live_board_roots,
    reject_live_board_mutation_target,
)
from cascade.probe.bounds import ProbeDeadline
from cascade.probe.harness import ProbeHarnessOptions, bootstrap_probe_repository, probe_workspace


def test_live_board_detects_product_checkout() -> None:
    roots = live_board_roots()
    assert roots
    assert is_live_board_path(roots[0])
    assert is_live_board_path(roots[0] / "docs" / "epics" / "1_backlog")


def test_rejects_live_board_mutation_target() -> None:
    live = live_board_roots()[0]
    with pytest.raises(ProbeError, match="live board"):
        reject_live_board_mutation_target(live)


def test_mutation_outside_workspace_rejected(tmp_path: Path) -> None:
    parent = tmp_path / "probe-parent"
    parent.mkdir()
    with probe_workspace(parent_dir=parent) as workspace:
        with pytest.raises(ProbeError, match="inside workspace"):
            workspace.validate_mutation_target(tmp_path / "outside")


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
