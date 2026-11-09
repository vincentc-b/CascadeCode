from __future__ import annotations

import json
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http import HTTPStatus
from types import SimpleNamespace

from cascade.watchdog.audit_lane import AuditPassResult, HealthAuditLane
from cascade.watchdog.audit_lane import audit_receipt_path
from cascade.watchdog.config import HealthAuditConfig
from cascade.watchdog.incidents import authoritative_generation, incident_record
from cascade.war_room.audit_status import health_audit_status
from cascade.war_room.human_auth import LocalHumanIdentityVerifier
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo


def _post(
    url: str,
    *,
    token: str | None = None,
    body: bytes = b"",
) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
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


def _get(url: str) -> tuple[int, dict[str, object]]:
    with urllib.request.urlopen(url) as response:
        return response.status, json.loads(response.read().decode())


def test_manual_audit_requires_human_and_coalesces_duplicate_request(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    token = "manual-audit-secret"
    verifier = LocalHumanIdentityVerifier("local:test", token)
    admissions = iter((True, False))
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=verifier,
        health_audit_request=lambda: next(admissions),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/health/audit"
    try:
        status, _ = _post(url)
        assert status == HTTPStatus.UNAUTHORIZED
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
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_stopped_lane_rejects_manual_audit(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    lane = HealthAuditLane(
        root=root,
        config=HealthAuditConfig(enabled=False, interval_seconds=60),
        run_pass=lambda *_args: AuditPassResult(),
    )
    lane.stop()
    token = "manual-audit-secret"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=LocalHumanIdentityVerifier("local:test", token),
        health_audit_request=lane.request_manual_pass,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _post(
            f"http://127.0.0.1:{port}/api/health/audit", token=token
        )
        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert payload == {"error": "health audit unavailable"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_missing_lane_rejects_manual_audit(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    token = "manual-audit-secret"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=LocalHumanIdentityVerifier("local:test", token),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _post(
            f"http://127.0.0.1:{port}/api/health/audit", token=token
        )
        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert payload == {"error": "health audit unavailable"}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_route_runs_disabled_lane_without_moving_periodic_deadline(tmp_path) -> None:
    root = make_repo(tmp_path, git=False)
    entered = threading.Event()
    release = threading.Event()
    completed = threading.Event()

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
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(
        root=root,
        host="127.0.0.1",
        port=port,
        human_identity_verifier=LocalHumanIdentityVerifier("local:test", token),
        health_audit_request=lane.request_manual_pass,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}/api/health/audit"
    try:
        assert _post(url, token=token) == (
            HTTPStatus.ACCEPTED,
            {"ok": True, "status": "admitted"},
        )
        assert entered.wait(2)
        assert _post(url, token=token) == (
            HTTPStatus.ACCEPTED,
            {"ok": True, "status": "coalesced"},
        )
        release.set()
        assert completed.wait(2)
        assert lane.deadline == deadline
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(2)
        lane.stop(timeout=2)


def test_get_audit_projects_receipt_and_truthful_durable_incident(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    receipt = audit_receipt_path(root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        json.dumps(
            {
                "last_completed_at": "2026-11-08T12:00:00+00:00",
                "next_scheduled_at": "2026-11-08T12:30:00+00:00",
                "interval_seconds": 1800,
                "duration_seconds": 2.25,
                "counts": {
                    "healthy": 2,
                    "proven_incident": 1,
                    "tier.task.healthy": 2,
                    "tier.feature.proven_incident": 1,
                },
                "next_cursor": None,
            }
        ),
        encoding="utf-8",
    )
    generation = authoritative_generation(
        work_id="feat_001",
        tier="feature",
        evidence={"status": "active"},
        capability="resume_planning_owner",
    )
    incident = incident_record(
        work_id="feat_001",
        tier="feature",
        accountable_owner="feature_team:feat_001",
        failure_class="stalled_owner",
        generation=generation,
        evidence={"status": "active", "branch": "feat/feat_001"},
        selected_capability="resume_planning_owner",
        request={
            "reservation_id": "feat_001:health_reservation:one",
            "claim_token": "token",
            "operation": "resume_planning_owner",
        },
        attempts=[{"attempt": 1, "claim_token": "token", "accepted_at": "2026-11-08T12:00:01+00:00"}],
        outcome="claimed",
        now=datetime(2026, 11, 8, 12, 0, tzinfo=timezone.utc),
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit.project_audit_observation",
        lambda *_args, **_kwargs: SimpleNamespace(
            classification="proven_incident",
            incident=SimpleNamespace(failure_class="stalled_owner"),
            generation=generation,
        ),
    )
    ledger = root / ".cascade" / "executions.json"
    ledger.write_text(
        json.dumps({"actions": {"reservation": {"incident": incident}}}),
        encoding="utf-8",
    )
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, payload = _get(f"http://127.0.0.1:{port}/api/health/audit")
        assert status == HTTPStatus.OK
        assert payload["last_run"] == "2026-11-08T12:00:00+00:00"
        assert payload["next_due"] == "2026-11-08T12:30:00+00:00"
        assert payload["duration_seconds"] == 2.25
        assert payload["counts"]["by_outcome"]["healthy"] == 2
        assert payload["counts"]["by_tier"]["feature"]["proven_incident"] == 1
        projected = payload["incidents"][0]
        assert projected["owner"] == "feature_team:feat_001"
        assert projected["evidence"] == {
            "available": True,
            "value": {"branch": "feat/feat_001", "status": "active"},
        }
        assert projected["request"]["state"] == "acknowledged"
        assert projected["acknowledgement"] == {
            "available": True,
            "value": {
                "accepted_at": "2026-11-08T12:00:01+00:00",
                "attempt": 1,
            },
        }
        assert projected["result"] == {"available": False, "value": None}
        assert projected["resume_action"] == {
            "operation": "resume_planning_owner",
            "owner": "feature_team:feat_001",
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_get_audit_exposes_unavailable_evidence_without_inventing_state(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    generation = authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence={},
        capability="retry_task",
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="blocked_task_failed",
        generation=generation,
        evidence={},
        selected_capability="retry_task",
        outcome="deferred",
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit.project_audit_observation",
        lambda *_args, **_kwargs: SimpleNamespace(
            classification="proven_incident",
            incident=SimpleNamespace(failure_class="blocked_task_failed"),
            generation=generation,
        ),
    )
    ledger = root / ".cascade" / "executions.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({"actions": {"reservation": {"incident": incident}}}),
        encoding="utf-8",
    )
    payload = health_audit_status(root=root)
    projected = payload["incidents"][0]
    assert projected["evidence"] == {"available": False, "value": None}
    assert projected["request"]["state"] == "unavailable"
    assert "investigating" not in json.dumps(projected)


def test_reserved_claim_is_not_reported_as_delivered_pending_request(
    tmp_path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    generation = authoritative_generation(
        work_id="task_001", tier="task", evidence={}, capability="retry_task"
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="blocked_task_failed",
        generation=generation,
        evidence={},
        selected_capability="retry_task",
        request={"reservation_id": "reservation", "claim_token": "token", "operation": "retry_task"},
        attempts=[
            {"attempt": 1, "claim_token": "previous", "accepted_at": "2026-11-08T12:00:00+00:00"},
            {"attempt": 2, "claim_token": "token", "started_at": "2026-11-08T12:01:00+00:00"},
        ],
        outcome="claimed",
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit.project_audit_observation",
        lambda *_args, **_kwargs: SimpleNamespace(
            classification="proven_incident",
            incident=SimpleNamespace(failure_class="blocked_task_failed"),
            generation=generation,
        ),
    )
    ledger = root / ".cascade" / "executions.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({"actions": {"reservation": {"incident": incident}}}),
        encoding="utf-8",
    )
    projected = health_audit_status(root=root)["incidents"][0]
    assert projected["request"]["state"] == "reserved"
    assert projected["acknowledgement"]["available"] is False


def test_stale_or_superseded_incident_is_not_reported_active(
    tmp_path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "terminal lifecycle"], cwd=root, check=True)
    generation = authoritative_generation(
        work_id="task_001", tier="task", evidence={}, capability="retry_task"
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="blocked_task_failed",
        generation=generation,
        evidence={"status": "blocked"},
        selected_capability="retry_task",
        outcome="deferred",
    )
    ledger = root / ".cascade" / "remediation_dispositions.json"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps({"dispositions": {"historical": {"incident": incident}}}),
        encoding="utf-8",
    )

    payload = health_audit_status(root=root)

    assert payload["incidents"] == []
    assert ledger.exists()


def test_malformed_and_missing_receipts_are_distinct_unavailable_evidence(
    tmp_path,
) -> None:
    root = make_repo(tmp_path, git=False)

    missing = health_audit_status(root=root)
    receipt = audit_receipt_path(root)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text("{broken", encoding="utf-8")
    malformed = health_audit_status(root=root)

    assert missing["last_run"] is None
    assert missing["unavailable_evidence"][0] == {
        "source": "audit_receipt",
        "reason": "no completed audit receipt",
    }
    assert malformed["last_run"] is None
    assert malformed["counts"]["by_outcome"]["healthy"] == 0
    assert malformed["unavailable_evidence"][0] == {
        "source": "audit_receipt",
        "reason": "audit receipt is malformed or incomplete",
    }
