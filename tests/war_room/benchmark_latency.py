#!/usr/bin/env python3
"""Repeatable real-browser War Room latency benchmark.

Run from the repository root. The fixture is generated in a temporary directory
and served by the production War Room server; no tracked board is mutated.
"""

from __future__ import annotations

import argparse
import json
import math
import platform
import socket
import statistics
import subprocess
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cascade.war_room.server import serve

FIXTURE = {"epics": 3, "features_per_epic": 10, "tasks_per_feature": 2}


def _doc(
    work_id: str, tier: str, parent: str | None, title: str, *, status: str = "backlog"
) -> str:
    parent_value = "null" if parent is None else parent
    return f"""---
id: {work_id}
title: {title}
tier: {tier}
status: {status}
parent: {parent_value}
children: []
depends_on: []
owners: [benchmark]
skills: []
parent_rev: null
created: 2026-11-05
updated: 2026-11-05
---

# {title}

Fixed War Room latency benchmark fixture.
"""


def create_fixture(root: Path) -> None:
    """Materialize the invariant 3-epic/30-feature/60-task board."""
    for tier in ("epics", "features", "tasks"):
        for column in ("1_backlog", "2_active", "3_completed"):
            (root / "docs" / tier / column).mkdir(parents=True, exist_ok=True)
    for epic_number in range(1, FIXTURE["epics"] + 1):
        epic_id = f"epic_9{epic_number:02d}"
        epic_status = "active" if epic_number == 1 else "backlog"
        epic_column = "2_active" if epic_status == "active" else "1_backlog"
        (root / "docs/epics" / epic_column / f"{epic_id}_benchmark.md").write_text(
            _doc(
                epic_id, "epic", None, f"Benchmark epic {epic_number}", status=epic_status
            ),
            encoding="utf-8",
        )
        for feature_number in range(1, FIXTURE["features_per_epic"] + 1):
            feature_id = f"feat_9{epic_number:02d}_{feature_number:03d}"
            (root / "docs/features/1_backlog" / f"{feature_id}_benchmark.md").write_text(
                _doc(feature_id, "feature", epic_id, f"Benchmark feature {feature_number}"),
                encoding="utf-8",
            )
            for task_number in range(1, FIXTURE["tasks_per_feature"] + 1):
                task_id = f"task_9{epic_number:02d}_{feature_number:03d}_{task_number:03d}"
                (root / "docs/tasks/1_backlog" / f"{task_id}_benchmark.md").write_text(
                    _doc(task_id, "task", feature_id, f"Benchmark task {task_number}"),
                    encoding="utf-8",
                )
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _percentile(values: list[float], percentile: int) -> float:
    ordered = sorted(values)
    rank = max(0, math.ceil(percentile / 100 * len(ordered)) - 1)
    return ordered[rank]


def _summary(rows: list[dict[str, float]]) -> dict[str, dict[str, float]]:
    result = {}
    for metric in rows[0]:
        values = [row[metric] for row in rows]
        result[metric] = {
            "median_ms": round(statistics.median(values), 3),
            "p95_ms": round(_percentile(values, 95), 3),
            "min_ms": round(min(values), 3),
            "max_ms": round(max(values), 3),
        }
    return result


def run(runs: int, output: Path, *, headed: bool) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment diagnostic
        raise SystemExit("Install the benchmark dependency: pip install playwright && playwright install chromium") from exc

    rows: list[dict[str, float]] = []
    with tempfile.TemporaryDirectory(prefix="cascade-war-room-benchmark-") as temp:
        fixture_root = Path(temp)
        create_fixture(fixture_root)
        port = _free_port()
        server = serve(root=fixture_root, port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as runtime:
                browser = runtime.chromium.launch(headless=not headed)
                browser_version = browser.version
                try:
                    for _ in range(runs):
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 1000}
                        )
                        page = context.new_page()
                        page.goto(
                            f"http://127.0.0.1:{port}/war-room",
                            wait_until="domcontentloaded",
                        )
                        page.locator('.board-row[data-id="epic_901"]').wait_for(
                            state="visible"
                        )
                        page.evaluate(
                            "() => new Promise(resolve => "
                            "requestAnimationFrame(() => requestAnimationFrame(resolve)))"
                        )
                        metrics = page.evaluate(
                            """() => {
                              const navigation = performance.getEntriesByType('navigation')[0];
                              const board = performance.getEntriesByType('resource').find(
                                entry => new URL(entry.name).pathname === '/api/board'
                              );
                              const render = performance.getEntriesByName('cascade.board.render')[0];
                              if (!navigation || !board || !render) throw new Error('missing performance marker');
                              const usableAt = performance.now();
                              const row = document.querySelector('.board-row[data-id="epic_901"]');
                              const actionStarted = performance.now();
                              row.click();
                              if (!row.classList.contains('board-row-selected')) {
                                throw new Error('selection feedback was not rendered');
                              }
                              return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve({
                                navigation_to_usable_board_ms: usableAt,
                                board_api_ms: board.responseEnd - board.requestStart,
                                render_ms: render.duration,
                                action_feedback_ms: performance.now() - actionStarted,
                              }))));
                            }"""
                        )
                        rows.append(
                            {
                                key: round(float(value), 3)
                                for key, value in metrics.items()
                            }
                        )
                        context.close()
                finally:
                    browser.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    result = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "fixture": FIXTURE,
        "runs": runs,
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "browser": f"Chromium {browser_version}",
            "viewport": "1440x1000",
        },
        "metric_boundaries": {
            "navigation_to_usable_board_ms": "navigation start -> first visible epic row plus two animation frames",
            "board_api_ms": "Resource Timing requestStart -> responseEnd for the initial GET /api/board",
            "render_ms": "renderBoard entry -> synchronous DOM update completion",
            "action_feedback_ms": "epic row click dispatch -> selected row visible after two animation frames",
        },
        "raw": rows,
        "summary": _summary(rows),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()
    if args.runs < 1:
        parser.error("--runs must be positive")
    result = run(args.runs, args.output, headed=args.headed)
    print(json.dumps(result["summary"], indent=2))
    print(f"raw results: {args.output.resolve()}")


if __name__ == "__main__":
    main()
