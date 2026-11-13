"""Feature-attention board projection and authenticated acknowledgement API."""

from __future__ import annotations

import json
import socket
import threading
import urllib.error
import urllib.request
from contextlib import contextmanager
from http import HTTPStatus
from pathlib import Path
from typing import Iterator

import pytest

import cascade.feature_attention as attention_store
from cascade.feature_attention import feature_attention_paths
from cascade.war_room.human_auth import LocalHumanIdentityVerifier
from cascade.war_room.server import serve
from tests.support import add_doc, make_repo

TOKEN = "feature-attention-test-token"


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextmanager
def _server(root: Path) -> Iterator[str]:
    server = serve(
        root=root,
        host="127.0.0.1",
        port=_free_port(),
        human_identity_verifier=LocalHumanIdentityVerifier("local:operator", TOKEN),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(base: str) -> tuple[int, dict]:
    with urllib.request.urlopen(base + "/api/board") as response:
        return response.status, json.loads(response.read())


def _post(
    base: str,
    body: object,
    *,
    authenticated: bool = False,
) -> tuple[int, dict]:
    request = urllib.request.Request(
        base + "/api/feature_attention/mark_seen",
        method="POST",
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {TOKEN}"} if authenticated else {}),
        },
    )
    try:
        with urllib.request.urlopen(request) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_board_projection_and_mark_seen_are_explicit_durable_and_idempotent(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Corrective one",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_001_002",
        title="Corrective two",
        tier="feature",
        parent="epic_001",
    )
    product_before = {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*.md")
    }

    with _server(root) as base:
        status, board = _get(base)
        attention = board["feature_attention"]
        assert status == HTTPStatus.OK
        assert attention["state"] == "available"
        assert attention["revision"] == 1
        assert attention["epic_new_counts"] == {"epic_001": 2}
        assert attention["features"]["feat_001_001"]["new"] is True

        assert _post(base, {"feature_id": "feat_001_001"})[0] == HTTPStatus.UNAUTHORIZED
        assert _post(base, {"feature_id": "not-an-id"}, authenticated=True)[0] == HTTPStatus.BAD_REQUEST
        assert _post(
            base,
            {"feature_id": "feat_001_001", "extra": True},
            authenticated=True,
        )[0] == HTTPStatus.BAD_REQUEST
        assert _post(base, {"feature_id": "feat_001_999"}, authenticated=True)[0] == HTTPStatus.NOT_FOUND

        first_status, first = _post(
            base, {"feature_id": "feat_001_001"}, authenticated=True
        )
        repeat_status, repeat = _post(
            base, {"feature_id": "feat_001_001"}, authenticated=True
        )
        assert first_status == repeat_status == HTTPStatus.OK
        assert first["revision"] == repeat["revision"] == 2
        assert first["attention"] == repeat["attention"]
        assert first["attention"]["seen"]["actor"] == "local:operator"
        assert first["attention"]["new"] is False

        _, refreshed = _get(base)
        assert refreshed["feature_attention"]["revision"] == 2
        assert refreshed["feature_attention"]["epic_new_counts"] == {"epic_001": 1}

    # Restart reads the same tracking-owned acknowledgement and never edits a
    # work plan or approval/status document.
    with _server(root) as base:
        _, restarted = _get(base)
        record = restarted["feature_attention"]["features"]["feat_001_001"]
        assert record["seen"]["actor"] == "local:operator"
        assert record["new"] is False
    assert {
        path.relative_to(root): path.read_bytes() for path in root.rglob("*.md")
    } == product_before


def test_concurrent_acknowledgements_return_monotonic_revisions(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    for index in (1, 2):
        add_doc(
            root,
            id=f"feat_001_{index:03d}",
            title=f"Corrective {index}",
            tier="feature",
            parent="epic_001",
        )

    with _server(root) as base:
        barrier = threading.Barrier(2)
        results: list[tuple[int, dict]] = []

        def acknowledge(feature_id: str) -> None:
            barrier.wait()
            results.append(_post(base, {"feature_id": feature_id}, authenticated=True))

        threads = [
            threading.Thread(target=acknowledge, args=(f"feat_001_{index:03d}",))
            for index in (1, 2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        assert {status for status, _ in results} == {HTTPStatus.OK}
        assert {payload["revision"] for _, payload in results} == {2, 3}
        _, board = _get(base)
        assert board["feature_attention"]["revision"] == 3
        assert board["feature_attention"]["epic_new_counts"] == {}


def test_missing_initialized_ledger_is_exposed_and_write_fails_closed(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Corrective",
        tier="feature",
        parent="epic_001",
    )
    with _server(root) as base:
        feature_attention_paths(root).ledger.unlink()
        _, board = _get(base)
        assert board["feature_attention"] == {
            "schema_version": 1,
            "state": "unavailable",
            "revision": None,
            "features": {},
            "epic_new_counts": {},
            "reason": "ledger_missing_after_initialization",
        }
        status, _ = _post(
            base, {"feature_id": "feat_001_001"}, authenticated=True
        )
        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert not feature_attention_paths(root).ledger.exists()


def test_storage_failure_reports_503_without_acknowledging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Active", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Corrective",
        tier="feature",
        parent="epic_001",
    )
    with _server(root) as base:
        ledger_path = feature_attention_paths(root).ledger
        original = ledger_path.read_bytes()
        real_atomic_json = attention_store._atomic_json

        def fail_attention_write(path: Path, value: dict[str, object]) -> None:
            if path == ledger_path:
                raise OSError("simulated full disk")
            real_atomic_json(path, value)

        monkeypatch.setattr(attention_store, "_atomic_json", fail_attention_write)
        status, _ = _post(
            base, {"feature_id": "feat_001_001"}, authenticated=True
        )
        assert status == HTTPStatus.SERVICE_UNAVAILABLE
        assert ledger_path.read_bytes() == original

        monkeypatch.setattr(attention_store, "_atomic_json", real_atomic_json)
        _, board = _get(base)
        record = board["feature_attention"]["features"]["feat_001_001"]
        assert record["seen"] is None
        assert record["new"] is True
