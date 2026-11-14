"""Cross-boundary evidence for the retained health-audit experience."""

from __future__ import annotations

import json
import socket
import threading
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cascade.board.context import set_project_context
from cascade.watchdog.audit_investigation import follow_up_snapshot_path
from cascade.watchdog.audit_lane import AuditPassResult
from cascade.watchdog.audit_projection import publish_audit_projection, projection_root
from cascade.war_room.server import serve
from cascade.workspace.types import ProjectContext
from tests.support import make_repo


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _incident(
    work_id: str,
    generation: str,
    failure_class: str,
    stamp: str,
    *,
    outcome: str = "error",
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "work_id": work_id,
        "work": {"work_id": work_id, "tier": work_id.split("_", 1)[0]},
        "accountable_owner": "feature_team:feat_owner",
        "failure_class": failure_class,
        "authoritative_generation": generation,
        "recorded_at": stamp,
        "outcome": outcome,
        "attempts": [{"attempt": 1, "started_at": stamp, "outcome": "failed"}],
    }


@contextmanager
def _server(root: Path):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def _get(url: str) -> dict[str, object]:
    with urllib.request.urlopen(url) as response:
        return json.loads(response.read())


def test_real_producer_to_loopback_api_retains_failures_across_restart_and_split_roots(
    tmp_path: Path, monkeypatch
) -> None:
    product = make_repo(tmp_path / "product", git=False)
    tracking = tmp_path / "tracking"
    tracking.mkdir()
    set_project_context(ProjectContext.split(product, tracking))
    try:
        now = datetime.now(timezone.utc)
        stamp = now.isoformat()
        old_stamp = (now - timedelta(days=8)).isoformat()
        generation = lambda value: "sha256:" + value * 64
        later = _incident(
            "task_002", generation("c"), "blocked_task_failed", stamp
        )
        later_history = [
            _incident(
                "task_002", generation(value), "delivery_stalled", old_stamp
            )
            for value in ("a", "b")
        ]
        publication = _incident(
            "feat_003", generation("d"), "publication_stalled", stamp
        )
        home = product / ".cascade"
        _write(
            home / "executions.json",
            {
                "actions": {
                    "later-blocker": {
                        "incident": later,
                        "incident_history": later_history,
                    },
                    "completed-publication": {"incident": publication},
                }
            },
        )
        _write(home / "orphan_delivery_recoveries.json", {"recoveries": {}})
        _write(
            home / "remediation_dispositions.json",
            {
                "dispositions": {
                    "legacy-remediation": {
                        "child_id": "task_legacy",
                        "observed_child_sha": "ambiguous-old-sha",
                        "supervisor_id": "feat_owner",
                        "observed_at": old_stamp,
                        "result": "reported_fixed",
                        "reason": "legacy remediation cannot prove resolution",
                    },
                    "malformed-neighbor": ["not", "a", "record"],
                }
            },
        )

        first_epoch = publish_audit_projection(
            product,
            AuditPassResult(
                candidate_failures=(
                    {"work_id": "task_001", "reason": "observation_timeout"},
                )
            ),
            interval_seconds=60,
            observed_at=now,
        )
        second_epoch = publish_audit_projection(
            product,
            AuditPassResult(
                projection_observations=(
                    {
                        "work_id": "task_002",
                        "owner": "feature_team:feat_owner",
                        "authoritative_generation": generation("c"),
                        "failure_class": "blocked_task_failed",
                        "classification": "proven_incident",
                        "reason": "later authoritative blocker",
                    },
                    {
                        "work_id": "feat_003",
                        "owner": "feature_team:feat_owner",
                        "authoritative_generation": generation("d"),
                        "failure_class": "publication_stalled",
                        "classification": "proven_incident",
                        "reason": "completed work awaits publication",
                    },
                )
            ),
            prior_epoch=first_epoch,
            interval_seconds=60,
            observed_at=now + timedelta(seconds=1),
        )
        assert second_epoch != first_epoch
        follow_up = follow_up_snapshot_path(product)
        assert follow_up.is_relative_to(tracking)
        _write(
            follow_up,
            {
                "version": 1,
                "state": "available",
                "published_at": stamp,
                "source": {"kind": "audit_investigation_cases"},
                "rows": [],
            },
        )

        runtime_files = sorted(
            path
            for root in (product / ".cascade", tracking / ".cascade")
            for path in root.rglob("*")
            if path.is_file()
        )
        before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in runtime_files}
        monkeypatch.setattr(
            "cascade.watchdog.audit.project_audit_observation",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("GET performed a lifecycle probe")
            ),
        )
        monkeypatch.setattr(
            "cascade.agent.providers.probe_providers",
            lambda: (_ for _ in ()).throw(AssertionError("GET probed providers")),
        )

        with _server(product) as base:
            results: list[dict[str, object]] = []
            threads = [
                threading.Thread(
                    target=lambda: results.append(_get(f"{base}/api/health/audit"))
                )
                for _ in range(8)
            ]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(3)
            history = _get(f"{base}/api/health/audit/history?limit=100")
            coverage = _get(
                f"{base}/api/health/audit/coverage?work_id="
                + urllib.parse.quote("task_001")
            )

        assert len(results) == 8
        assert all(result["snapshot"]["epoch"] == second_epoch for result in results)
        current = results[0]["current"]["rows"]
        assert {(row["work_id"], row["failure_class"]) for row in current} == {
            ("task_002", "blocked_task_failed"),
            ("feat_003", "publication_stalled"),
        }
        history_rows = history["page"]["rows"]
        assert sum(
            row["source_ref"].get("incident_history_ordinal") is not None
            for row in history_rows
        ) == 2
        legacy = next(row for row in history_rows if row["work_id"] == "task_legacy")
        assert legacy["verification_status"] == "unverifiable"
        assert legacy["provenance"]["result"] == "reported_fixed"
        assert coverage["page"]["rows"][0]["reason"] == "observation_timeout"
        assert before == {
            path: (path.stat().st_mtime_ns, path.read_bytes()) for path in runtime_files
        }
        assert projection_root(product).is_relative_to(product)
    finally:
        set_project_context(None)
