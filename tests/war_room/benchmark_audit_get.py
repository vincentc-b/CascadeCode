#!/usr/bin/env python3
"""Record warm local audit-status GET latency on a 10,000-attempt fixture.

This is inspectable environment evidence, not a latency assertion. Functional
tests separately enforce source, row, and response ceilings.
"""

from __future__ import annotations

import json
import math
import platform
import socket
import sys
import tempfile
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cascade.watchdog.audit_lane import AuditPassResult
from cascade.watchdog.audit_projection import publish_audit_projection
from cascade.war_room.server import serve

ROWS = 100
ATTEMPTS_PER_ROW = 100
SAMPLES = 30


def _incident(index: int, stamp: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "work_id": f"task_{index:03d}",
        "work": {"work_id": f"task_{index:03d}", "tier": "task"},
        "accountable_owner": f"feature_team:feat_{index % 17:03d}",
        "failure_class": "delivery_stalled",
        "authoritative_generation": "sha256:" + f"{index:064x}",
        "selected_capability": "recover_delivery",
        "recorded_at": stamp,
        "outcome": "error",
        "attempts": [
            {"attempt": attempt + 1, "started_at": stamp, "outcome": "failed"}
            for attempt in range(ATTEMPTS_PER_ROW)
        ],
    }


def run(root: Path) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    home = root / ".cascade"
    home.mkdir(parents=True)
    source = home / "executions.json"
    source.write_text(
        json.dumps(
            {
                "actions": {
                    f"action-{index:03d}": {"incident": _incident(index, stamp)}
                    for index in range(ROWS)
                }
            }
        )
    )
    (home / "orphan_delivery_recoveries.json").write_text('{"recoveries":{}}')
    (home / "remediation_dispositions.json").write_text('{"dispositions":{}}')
    observations = tuple(
        {
            "work_id": f"task_{index:03d}",
            "owner": f"feat_{index % 17:03d}",
            "authoritative_generation": "sha256:" + f"{index:064x}",
            "failure_class": "delivery_stalled",
            "classification": "proven_incident",
            "reason": "benchmark_verified",
        }
        for index in range(ROWS)
    )
    publish_audit_projection(
        root,
        AuditPassResult(projection_observations=observations),
        interval_seconds=1800,
        observed_at=now,
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/health/audit"
    try:
        urllib.request.urlopen(url).read()  # Warm imports and filesystem cache.
        samples = []
        response_bytes = 0
        for _ in range(SAMPLES):
            started = time.perf_counter()
            with urllib.request.urlopen(url) as response:
                body = response.read()
            samples.append((time.perf_counter() - started) * 1000)
            response_bytes = len(body)
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)
    ordered = sorted(samples)
    return {
        "command": "python tests/war_room/benchmark_audit_get.py",
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "processor": platform.processor() or "unreported",
            "transport": "loopback HTTP/1.1, one request per connection",
        },
        "fixture": {
            "attempts": ROWS * ATTEMPTS_PER_ROW,
            "incident_rows": ROWS,
            "owners": 17,
            "source_bytes": source.stat().st_size,
        },
        "measurement": {
            "warm_samples": SAMPLES,
            "median_ms": round(ordered[len(ordered) // 2], 3),
            "p95_ms": round(ordered[math.ceil(0.95 * len(ordered)) - 1], 3),
            "min_ms": round(ordered[0], 3),
            "max_ms": round(ordered[-1], 3),
            "response_bytes": response_bytes,
        },
        "limitations": [
            "Local warm-cache measurement; not a cross-platform latency guarantee.",
            "Recorded evidence only; no flaky latency threshold is asserted.",
        ],
    }


def main() -> None:
    with tempfile.TemporaryDirectory(
        prefix="cascade-audit-get-benchmark-"
    ) as directory:
        print(json.dumps(run(Path(directory)), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
