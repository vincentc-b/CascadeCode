"""Provider credential resolution (env → user store → CLI session).

Never reads workspace paths, cascade.toml, .netrc, or Cursor setting_sources.
Tokens are never logged.

CLI-session probe (claude/codex only; cursor has no CLI-session source in v1):
- Claude Code: ``~/.claude/.credentials.json`` with ``claudeAiOauth.accessToken`` (non-blank).
- OpenAI Codex CLI: ``~/.codex/auth.json`` with ``tokens.access_token`` (non-blank).
If the file is missing, unreadable, or lacks those fields, treat as not authenticated.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from typing import Literal

ProviderId = Literal["cursor", "claude", "codex", "fake"]
AuthSource = Literal["env", "user-store", "cli-session", "missing"]

_ENV_KEYS: dict[ProviderId, str] = {
    "cursor": "CURSOR_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "codex": "OPENAI_API_KEY",
}


@dataclass(frozen=True)
class Credential:
    provider: ProviderId
    token: str


def _user_store_path() -> Path:
    return Path.home() / ".cascade" / "credentials"


def _read_user_store_raw() -> dict[str, str]:
    path = _user_store_path()
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    out: dict[str, str] = {}
    for key, value in data.items():
        if isinstance(key, str) and isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


def _write_user_store_raw(entries: dict[str, str]) -> None:
    directory = _user_store_path().parent
    directory.mkdir(parents=True, exist_ok=True)
    path = _user_store_path()
    path.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def write_user_store_token(provider: ProviderId, token: str) -> None:
    stripped = token.strip()
    if not stripped:
        raise ValueError("token must be non-blank")
    entries = _read_user_store_raw()
    entries[provider] = stripped
    _write_user_store_raw(entries)


def forget_user_store_token(provider: ProviderId) -> None:
    entries = _read_user_store_raw()
    if provider not in entries:
        return
    del entries[provider]
    if entries:
        _write_user_store_raw(entries)
    else:
        path = _user_store_path()
        if path.is_file():
            path.unlink()


def _env_token(provider: ProviderId) -> str | None:
    key = _ENV_KEYS[provider]
    raw = os.environ.get(key)
    if raw is None:
        return None
    stripped = str(raw).strip()
    return stripped if stripped else None


def _user_store_token(provider: ProviderId) -> str | None:
    return _read_user_store_raw().get(provider)


def _claude_cli_session_token() -> str | None:
    path = Path.home() / ".claude" / ".credentials.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    oauth = data.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    token = oauth.get("accessToken")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _codex_cli_session_token() -> str | None:
    path = Path.home() / ".codex" / "auth.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    tokens = data.get("tokens")
    if not isinstance(tokens, dict):
        return None
    token = tokens.get("access_token")
    if isinstance(token, str) and token.strip():
        return token.strip()
    return None


def _cli_session_token(provider: ProviderId) -> str | None:
    if provider == "cursor":
        return None
    if provider == "claude":
        return _claude_cli_session_token()
    if provider == "codex":
        return _codex_cli_session_token()
    return None


def credential_auth_source(provider: ProviderId) -> AuthSource:
    """Return how auth would resolve for ``provider`` (no secret values)."""

    if _env_token(provider) is not None:
        return "env"
    if _user_store_token(provider) is not None:
        return "user-store"
    if provider != "cursor" and _cli_session_token(provider) is not None:
        return "cli-session"
    return "missing"


def resolve_credential(provider: ProviderId) -> Credential | None:
    """First match wins: env, user store, CLI session (claude/codex only)."""

    if provider == "fake":
        return Credential(provider="fake", token="fake")

    env = _env_token(provider)
    if env is not None:
        return Credential(provider=provider, token=env)
    store = _user_store_token(provider)
    if store is not None:
        return Credential(provider=provider, token=store)
    if provider != "cursor":
        cli = _cli_session_token(provider)
        if cli is not None:
            return Credential(provider=provider, token=cli)
    return None
