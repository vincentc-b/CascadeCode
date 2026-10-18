"""Credential resolver and user store (task_073)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.agent.credentials import (
    credential_auth_source,
    forget_user_store_token,
    resolve_credential,
    write_user_store_token,
)


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


def test_env_precedence_over_user_store(
    cascade_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    write_user_store_token("cursor", "store-key")
    monkeypatch.setenv("CURSOR_API_KEY", "env-key")
    cred = resolve_credential("cursor")
    assert cred is not None
    assert cred.token == "env-key"
    assert credential_auth_source("cursor") == "env"


def test_user_store_write_read_forget(cascade_home: Path) -> None:
    write_user_store_token("claude", "claude-secret")
    path = cascade_home / ".cascade" / "credentials"
    assert path.is_file()
    assert oct(path.stat().st_mode & 0o777) == oct(0o600)
    cred = resolve_credential("claude")
    assert cred is not None
    assert cred.token == "claude-secret"
    assert credential_auth_source("claude") == "user-store"

    forget_user_store_token("claude")
    assert resolve_credential("claude") is None
    forget_user_store_token("claude")


def test_cursor_never_uses_cli_session(
    cascade_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    claude_creds = cascade_home / ".claude" / ".credentials.json"
    claude_creds.parent.mkdir(parents=True)
    claude_creds.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "oauth-token"}}),
        encoding="utf-8",
    )
    assert resolve_credential("cursor") is None
    assert credential_auth_source("cursor") == "missing"


def test_never_reads_workspace_for_secrets(
    tmp_path: Path,
    cascade_home: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "ws"
    workspace.mkdir()
    (workspace / "cascade.toml").write_text(
        'CURSOR_API_KEY = "from-toml"\n',
        encoding="utf-8",
    )
    (workspace / ".env").write_text("CURSOR_API_KEY=from-dotenv\n", encoding="utf-8")
    assert resolve_credential("cursor") is None


def test_claude_cli_session_when_no_env_or_store(cascade_home: Path) -> None:
    path = cascade_home / ".claude" / ".credentials.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps({"claudeAiOauth": {"accessToken": "oauth-token"}}),
        encoding="utf-8",
    )
    cred = resolve_credential("claude")
    assert cred is not None
    assert cred.token == "oauth-token"
    assert credential_auth_source("claude") == "cli-session"
