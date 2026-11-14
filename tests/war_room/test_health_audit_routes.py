from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path

from cascade.watchdog.audit_lane import (
    AuditPassResult,
    HealthAuditLane,
    audit_receipt_path,
)
from cascade.watchdog.audit_projection import (
    CoverageSummary,
    CurrentSummary,
    HistorySummary,
    ProjectionManifest,
    SourceRef,
    projection_repository_identities,
    projection_root,
)
from cascade.watchdog.config import HealthAuditConfig
from cascade.war_room.human_auth import LocalHumanIdentityVerifier
from cascade.war_room.server import serve
from tests.support import make_repo


def _request(
    url: str,
    *,
    method: str = "GET",
    token: str | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {token}"} if token else {}),
        },
    )
    try:
        response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    with response:
        return response.status, json.loads(response.read().decode())


def _post(url: str, *, token: str | None = None, body: bytes = b""):
    return _request(url, method="POST", token=token, body=body)


def _get(url: str):
    return _request(url)


@contextmanager
def _server(root: Path, **kwargs):
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port, **kwargs)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")))


def _publish(
    root: Path, *, epoch: str = "epoch-one", observed: datetime | None = None
) -> None:
    observed = observed or datetime.now(timezone.utc)
    generation = "sha256:" + "a" * 64
    current = [
        CurrentSummary(
            SourceRef("action_recovery", "current-blocker"),
            "task_002",
            "feature_team:feat_001",
            generation,
            "blocked_task_failed",
            observed.isoformat(),
            observed.isoformat(),
            observed.isoformat(),
            "proven_incident",
            "fresh authoritative blocker",
        ).as_dict()
    ]
    coverage = [
        CoverageSummary(
            SourceRef("action_recovery", "current-blocker"),
            "task_002",
            "feature_team:feat_001",
            generation,
            "blocked_task_failed",
            observed.isoformat(),
            observed.isoformat(),
            observed.isoformat(),
            "proven_incident",
            "fresh authoritative blocker",
        ).as_dict(),
        CoverageSummary(
            SourceRef("orphan_delivery", "deferred"),
            "task_003",
            "feature_team:feat_001",
            None,
            "delivery_timeout",
            observed.isoformat(),
            observed.isoformat(),
            None,
            "pending",
            "observation_timeout",
        ).as_dict(),
    ]
    history = [
        HistorySummary(
            SourceRef("remediation_dispositions", f"legacy-{index}"),
            "task_001",
            "feature_team:feat_001",
            None,
            "old_failure",
            (observed - timedelta(days=index + 1)).isoformat(),
            None,
            None,
            "unverifiable",
            "legacy_attempt",
            provenance={"legacy": "true"},
        ).as_dict()
        for index in range(2)
    ]
    sections = {"current": current, "coverage": coverage, "history": history}
    product, tracking = projection_repository_identities(root)
    manifest = ProjectionManifest(
        epoch=epoch,
        observed_at=observed.isoformat(),
        interval_seconds=60,
        fresh_until=(observed + timedelta(minutes=3)).isoformat(),
        product_identity=product,
        tracking_identity=tracking,
        page_counts={name: 1 for name in sections},
        row_counts={name: len(rows) for name, rows in sections.items()},
        coverage_by_status={"proven_incident": 1, "pending": 1},
        coverage_by_reason={"fresh authoritative blocker": 1, "observation_timeout": 1},
    ).as_dict()
    base = projection_root(root)
    for name, rows in sections.items():
        _write(
            base / epoch / name / "000000.json",
            {
                "schema_version": 2,
                "projection_kind": name,
                "epoch": epoch,
                "rows": rows,
            },
        )
    _write(base / epoch / "manifest.json", manifest)
    _write(base / "current.json", {"schema_version": 2, "epoch": epoch})


def test_manual_audit_requires_human_and_coalesces_duplicate_request(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    token = "manual-audit-secret"
    admissions = iter((True, False))
    with _server(
        root,
        human_identity_verifier=LocalHumanIdentityVerifier("local:test", token),
        health_audit_request=lambda: next(admissions),
    ) as base:
        url = f"{base}/api/health/audit"
        assert _post(url)[0] == HTTPStatus.UNAUTHORIZED
        assert _post(url, token=token) == (
            HTTPStatus.ACCEPTED,
            {"ok": True, "status": "admitted"},
        )
        assert _post(url, token=token) == (
            HTTPStatus.ACCEPTED,
            {"ok": True, "status": "coalesced"},
        )
        assert _post(url, token=token, body=b'{"unexpected":true}') == (
            HTTPStatus.BAD_REQUEST,
            {"error": "manual audit accepts no body"},
        )


def test_stopped_or_missing_lane_rejects_manual_audit(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    lane = HealthAuditLane(
        root=root,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=lambda *_args: AuditPassResult(),
    )
    lane.stop()
    token = "manual-audit-secret"
    verifier = LocalHumanIdentityVerifier("local:test", token)
    for request in (lane.request_manual_pass, None):
        with _server(
            root, human_identity_verifier=verifier, health_audit_request=request
        ) as base:
            assert _post(f"{base}/api/health/audit", token=token) == (
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "health audit unavailable"},
            )


def test_route_runs_disabled_lane_without_moving_periodic_deadline(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    entered, release, completed = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    def run_pass(*_args) -> AuditPassResult:
        entered.set()
        assert release.wait(2)
        return AuditPassResult(counts={"manual": 1})

    lane = HealthAuditLane(
        root=root,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=run_pass,
        handoff=lambda _ids: completed.set(),
    ).start()
    deadline = lane.deadline
    token = "manual-audit-secret"
    try:
        with _server(
            root,
            human_identity_verifier=LocalHumanIdentityVerifier("local:test", token),
            health_audit_request=lane.request_manual_pass,
        ) as base:
            url = f"{base}/api/health/audit"
            assert _post(url, token=token)[1]["status"] == "admitted"
            assert entered.wait(2)
            assert _post(url, token=token)[1]["status"] == "coalesced"
            release.set()
            assert completed.wait(2)
            assert lane.deadline == deadline
    finally:
        release.set()
        lane.stop(timeout=2)


def test_get_status_uses_verified_projection_and_bounded_runtime_metadata(
    tmp_path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root)
    receipt = audit_receipt_path(root)
    _write(
        receipt,
        {
            "last_completed_at": "2026-11-14T12:00:00+00:00",
            "next_scheduled_at": "2026-11-14T12:01:00+00:00",
            "interval_seconds": 60,
            "duration_seconds": 1.25,
            "counts": {"proven_incident": 1, "tier.task.proven_incident": 1},
            "next_cursor": "opaque",
            "secret_extra": "not exposed",
        },
    )
    with _server(root) as base:
        status, payload = _get(f"{base}/api/health/audit")
    assert status == HTTPStatus.OK
    assert payload["state"] == "ready"
    assert payload["snapshot"]["epoch"] == "epoch-one"
    assert payload["current"]["returned"] == 1
    assert payload["coverage"]["by_status"] == {"pending": 1, "proven_incident": 1}
    assert payload["incidents"][0]["work_id"] == "task_002"
    assert payload["incidents"][0]["source_ref"]["row_key"] == "current-blocker"
    assert payload["receipt"].get("secret_extra") is None
    assert payload["counts"]["by_tier"]["task"]["proven_incident"] == 1


def test_get_status_reports_missing_stale_and_corrupt_snapshots_as_pending(
    tmp_path,
) -> None:
    root = make_repo(tmp_path, git=False)
    assert _get_status(root)["snapshot"]["reason"] == "pointer_missing"
    _publish(root, observed=datetime.now(timezone.utc) - timedelta(hours=1))
    assert _get_status(root)["snapshot"]["reason"] == "snapshot_stale"
    projection_root(root).joinpath("current.json").write_text("{broken")
    assert _get_status(root)["snapshot"]["reason"] == "pointer_malformed"


def _get_status(root: Path) -> dict[str, object]:
    with _server(root) as base:
        return _get(f"{base}/api/health/audit")[1]


def test_paginated_routes_filter_continue_and_reject_bad_queries(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root)
    with _server(root) as base:
        status, first = _get(
            f"{base}/api/health/audit/history?limit=1&status=unverifiable"
        )
        assert status == HTTPStatus.OK
        assert first["page"]["returned"] == 1
        assert first["page"]["complete"] is False
        cursor = urllib.parse.quote(first["page"]["next_cursor"], safe="")
        status, second = _get(
            f"{base}/api/health/audit/history?limit=1&status=unverifiable&cursor={cursor}"
        )
        assert status == HTTPStatus.OK
        assert second["page"]["complete"] is True
        status, coverage = _get(f"{base}/api/health/audit/coverage?work_id=task_003")
        assert status == HTTPStatus.OK
        assert coverage["page"]["rows"][0]["reason"] == "observation_timeout"
        assert (
            _get(f"{base}/api/health/audit/history?limit=101")[0]
            == HTTPStatus.BAD_REQUEST
        )
        assert (
            _get(f"{base}/api/health/audit/history?owner=")[0] == HTTPStatus.BAD_REQUEST
        )
        mismatch = _get(f"{base}/api/health/audit/history?limit=2&cursor={cursor}")
        assert mismatch == (
            HTTPStatus.CONFLICT,
            {"state": "pending", "reason": "cursor_mismatch", "restart": True},
        )


def test_repeated_concurrent_gets_do_not_mutate_or_probe_runtime_state(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _publish(root)
    files = sorted(path for path in projection_root(root).rglob("*") if path.is_file())
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files}
    monkeypatch.setattr(
        "cascade.watchdog.audit.project_audit_observation",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("GET probed lifecycle")
        ),
    )
    with _server(root) as base:
        results: list[int] = []
        threads = [
            threading.Thread(
                target=lambda: results.append(_get(f"{base}/api/health/audit")[0])
            )
            for _ in range(12)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(3)
    assert results == [HTTPStatus.OK] * 12
    assert before == {
        path: (path.stat().st_mtime_ns, path.read_bytes()) for path in files
    }
