"""Contracts for the repeatable War Room latency benchmark."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cascade.board.store import list_board
from tests.war_room.benchmark_latency import FIXTURE, _percentile, _summary, create_fixture


def test_fixed_latency_fixture_shape(tmp_path):
    create_fixture(tmp_path)
    board = list_board(tmp_path)
    by_tier = {
        tier: [meta for meta in board.by_id.values() if meta.tier == tier]
        for tier in ("epic", "feature", "task")
    }
    assert len(by_tier["epic"]) == FIXTURE["epics"]
    assert len(by_tier["feature"]) == FIXTURE["epics"] * FIXTURE["features_per_epic"]
    assert len(by_tier["task"]) == len(by_tier["feature"]) * FIXTURE["tasks_per_feature"]
    assert [meta.id for meta in by_tier["epic"] if meta.status == "active"] == [
        "epic_901"
    ]
    assert all(meta.status == "backlog" for meta in by_tier["feature"] + by_tier["task"])


def test_summary_preserves_tail_latency():
    rows = [
        {
            "navigation_to_usable_board_ms": float(value),
            "board_api_ms": 1.0,
            "render_ms": 2.0,
            "action_feedback_ms": 3.0,
        }
        for value in range(1, 21)
    ]
    assert _percentile(list(range(1, 21)), 95) == 19
    assert _summary(rows)["navigation_to_usable_board_ms"] == {
        "median_ms": 10.5,
        "p95_ms": 19.0,
        "min_ms": 1.0,
        "max_ms": 20.0,
    }


def test_board_render_exposes_browser_performance_measure():
    source = (
        Path(__file__).resolve().parents[2] / "cascade/war_room/static/war_room.js"
    ).read_text(encoding="utf-8")
    render = source.split("function renderBoard(view)", 1)[1].split(
        "function wireCompletedCollapseControls", 1
    )[0]
    assert "const renderStartedAt = performance.now();" in render
    assert 'performance.measure("cascade.board.render"' in render


def test_committed_baseline_has_twenty_complete_runs():
    baseline = json.loads(
        (Path(__file__).parent / "baselines" / "task_023_003_001.json").read_text(
            encoding="utf-8"
        )
    )
    assert baseline["runs"] == 20
    assert len(baseline["raw"]) == 20
    required = {
        "navigation_to_usable_board_ms",
        "board_api_ms",
        "render_ms",
        "action_feedback_ms",
    }
    assert all(set(row) == required for row in baseline["raw"])
    assert baseline["summary"] == _summary(baseline["raw"])


def test_benchmark_cli_help_is_runnable():
    result = subprocess.run(
        ["python", "tests/war_room/benchmark_latency.py", "--help"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--runs" in result.stdout and "--output" in result.stdout
