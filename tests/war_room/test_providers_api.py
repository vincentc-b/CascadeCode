"""War Room provider status and credential API (task_075)."""

from __future__ import annotations

import json
import os
import socket
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.agent.credentials import resolve_credential
from cascade.war_room.server import serve
from tests.support import make_git_repo, make_repo
from cascade.workspace import init_workspace


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload or {}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict | None = None) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _json_has_token_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "token":
                return True
            if _json_has_token_key(item):
                return True
    elif isinstance(value, list):
        for item in value:
            if _json_has_token_key(item):
                return True
    return False


@pytest.fixture
def cascade_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    return home


@pytest.fixture(autouse=True)
def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in ("CURSOR_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture
def providers_server(tmp_path: Path, cascade_home: Path):
    root = make_repo(tmp_path, git=False)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root, cascade_home
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_get_providers_after_init_workspace(tmp_path: Path, cascade_home: Path) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, payload = _get(f"{base}/api/providers")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
    assert status == HTTPStatus.OK
    assert payload["default"] == "cursor"
    assert len(payload["providers"]) == 3
    assert not _json_has_token_key(payload)


def test_get_providers_shape(providers_server) -> None:
    base, _root, _home = providers_server
    status, payload = _get(f"{base}/api/providers")
    assert status == HTTPStatus.OK
    assert payload["default"] == "cursor"
    assert len(payload["providers"]) == 3
    ids = {row["id"] for row in payload["providers"]}
    assert ids == {"cursor", "claude", "codex"}
    for row in payload["providers"]:
        assert set(row) == {"id", "installed", "authenticated", "auth_source"}
    assert not _json_has_token_key(payload)


def test_post_token_expect_100_continue(providers_server) -> None:
    """Browsers withhold a large token body until the server sends 100 Continue."""

    base, _root, home = providers_server
    host_port = base.removeprefix("http://")
    host, port_s = host_port.rsplit(":", 1)
    token = "k" * 2048
    body = json.dumps({"token": token}).encode("utf-8")
    header = (
        "POST /api/providers/cursor/token HTTP/1.1\r\n"
        f"Host: {host}:{port_s}\r\n"
        "Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        "Expect: 100-continue\r\n"
        "Connection: close\r\n"
        "\r\n"
    ).encode("ascii")
    with socket.create_connection((host, int(port_s)), timeout=3) as sock:
        sock.sendall(header)
        sock.settimeout(2)
        prelude = b""
        while b"\r\n\r\n" not in prelude:
            chunk = sock.recv(4096)
            assert chunk, "connection closed before 100 Continue"
            prelude += chunk
        status_line = prelude.split(b"\r\n", 1)[0]
        assert status_line.startswith(b"HTTP/1.1 100"), status_line
        sock.sendall(body)
        rest = prelude.split(b"\r\n\r\n", 1)[1]
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            rest += chunk
    head, _, raw_body = rest.partition(b"\r\n\r\n")
    assert b"200" in head.split(b"\r\n", 1)[0]
    payload = json.loads(raw_body.decode("utf-8"))
    assert payload.get("ok") is True
    stored = json.loads((home / ".cascade" / "credentials").read_text(encoding="utf-8"))
    assert stored["cursor"] == token


def test_post_token_writes_user_store(providers_server) -> None:
    base, root, home = providers_server
    before = list(root.rglob("*"))
    status, body = _post(f"{base}/api/providers/cursor/token", {"token": "  secret-key  "})
    assert status == HTTPStatus.OK
    assert body.get("ok") is True
    cred_path = home / ".cascade" / "credentials"
    assert cred_path.is_file()
    assert oct(cred_path.stat().st_mode & 0o777) == oct(0o600)
    stored = json.loads(cred_path.read_text(encoding="utf-8"))
    assert stored["cursor"] == "secret-key"
    assert not any(p.is_relative_to(root) for p in cred_path.parents)
    after = list(root.rglob("*"))
    assert sorted(before) == sorted(after)


def test_post_token_blank_and_unknown_id(providers_server) -> None:
    base, _root, _home = providers_server
    code, body = _post_expect_error(f"{base}/api/providers/cursor/token", {"token": "   "})
    assert code == HTTPStatus.BAD_REQUEST
    assert "token" in body.get("error", "").lower()

    code, body = _post_expect_error(f"{base}/api/providers/nope/token", {"token": "x"})
    assert code == HTTPStatus.BAD_REQUEST
    assert "unknown" in body.get("error", "").lower()


def test_post_forget_removes_user_store_only(
    providers_server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base, _root, home = providers_server
    monkeypatch.setenv("CURSOR_API_KEY", "env-secret")
    cred_path = home / ".cascade" / "credentials"
    cred_path.parent.mkdir(parents=True)
    cred_path.write_text(json.dumps({"cursor": "saved"}), encoding="utf-8")
    cred_path.chmod(0o600)

    status, _body = _post(f"{base}/api/providers/cursor/forget", {})
    assert status == HTTPStatus.OK
    assert not cred_path.is_file()

    assert os.environ.get("CURSOR_API_KEY") == "env-secret"
    cred = resolve_credential("cursor")
    assert cred is not None
    assert cred.token == "env-secret"


def test_post_forget_unknown_id(providers_server) -> None:
    base, _root, _home = providers_server
    code, body = _post_expect_error(f"{base}/api/providers/unknown/forget", {})
    assert code == HTTPStatus.BAD_REQUEST
    assert "unknown" in body.get("error", "").lower()
