from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus

from cascade.watchdog.audit_lane import AuditPassResult, HealthAuditLane
from cascade.watchdog.config import HealthAuditConfig
from cascade.war_room.human_auth import LocalHumanIdentityVerifier
from cascade.war_room.server import serve
from tests.support import make_repo


def _post(url: str, *, token: str | None = None) -> tuple[int, dict[str, object]]:
    request = urllib.request.Request(
        url,
        data=b"{}",
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
