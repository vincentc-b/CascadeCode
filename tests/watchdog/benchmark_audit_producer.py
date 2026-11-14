#!/usr/bin/env python3
"""Measured producer fixture for the 10,000-attempt audit ledger.

This is evidence tooling, not a latency assertion.  It records the enforced
limits, environment, source size, row mix, producer duration, and output work.
"""
from __future__ import annotations

import json
import platform
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cascade.watchdog.audit_lane import AuditPassResult
from cascade.watchdog.audit_projection import publish_audit_projection, projection_root


ATTEMPTS_PER_ROW = 100
INCIDENT_ROWS = 100
MALFORMED_ROWS = 20


def _incident(index: int) -> dict:
    generation = "sha256:" + f"{index:064x}"
    stamp = "2026-11-14T12:00:00+00:00"
    return {
        "schema_version": 1,
        "work_id": f"task_{index:03d}",
        "work": {"work_id": f"task_{index:03d}", "tier": "task"},
        "accountable_owner": f"feature_team:feat_{index % 17:03d}",
        "failure_class": "delivery_stalled" if index % 2 else "blocked_task_failed",
        "authoritative_generation": generation,
        "selected_capability": "recover_delivery",
        "recorded_at": stamp,
        "outcome": "error",
        "attempts": [
            {"attempt": attempt + 1, "started_at": stamp, "outcome": "failed"}
            for attempt in range(ATTEMPTS_PER_ROW)
        ],
    }


def run(root: Path) -> dict:
    home = root / ".cascade"
    home.mkdir(parents=True)
    actions = {
        f"action-{index:03d}": {"incident": _incident(index)}
        for index in range(INCIDENT_ROWS)
    }
    actions.update(
        {
            f"malformed-{index:03d}": ["broken", index]
            for index in range(MALFORMED_ROWS)
        }
    )
    (home / "executions.json").write_text(
        json.dumps({"actions": actions}), encoding="utf-8"
    )
    (home / "orphan_delivery_recoveries.json").write_text(
        '{"recoveries":{}}', encoding="utf-8"
    )
    (home / "remediation_dispositions.json").write_text(
        '{"dispositions":{}}', encoding="utf-8"
    )
    observations = tuple(
        {
            "work_id": f"task_{index:03d}",
            "owner": f"feat_{index % 17:03d}",
            "authoritative_generation": "sha256:" + f"{index:064x}",
            "failure_class": (
                "delivery_stalled" if index % 2 else "blocked_task_failed"
            ),
            "classification": "proven_incident",
            "reason": "benchmark_verified",
        }
        for index in range(INCIDENT_ROWS)
    )
    started = time.perf_counter()
    epoch = publish_audit_projection(
        root,
        AuditPassResult(projection_observations=observations),
        interval_seconds=1800,
        observed_at=datetime(2026, 11, 14, 12, tzinfo=timezone.utc),
    )
    elapsed = time.perf_counter() - started
    epoch_root = projection_root(root) / epoch
    pages = list(epoch_root.glob("*/*.json"))
    return {
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor() or "unreported",
        },
        "fixture": {
            "attempts": INCIDENT_ROWS * ATTEMPTS_PER_ROW,
            "incident_rows": INCIDENT_ROWS,
            "owners": 17,
            "generations": INCIDENT_ROWS,
            "malformed_rows": MALFORMED_ROWS,
            "source_bytes": (home / "executions.json").stat().st_size,
        },
        "enforced_ceilings": {
            "candidates_per_pass": 100,
            "pass_seconds": 60,
            "candidate_seconds": 2,
        },
        "producer": {
            "elapsed_seconds": elapsed,
            "pages": len(pages),
            "serialized_page_bytes": sum(path.stat().st_size for path in pages),
        },
        "limitations": [
            "Local filesystem measurement; not a cross-platform latency guarantee.",
            "Ceilings are verified by focused tests; elapsed time is recorded, not asserted.",
        ],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="cascade-audit-benchmark-") as directory:
        print(json.dumps(run(Path(directory)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
