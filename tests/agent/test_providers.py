"""Provider registry and installation probes."""

from __future__ import annotations

import dataclasses
from unittest.mock import patch

import pytest

from cascade.agent import (
    ALL_PROVIDER_IDS,
    ProviderConfigError,
    ProviderStatus,
    parse_provider_id,
    probe_provider,
    probe_providers,
)


def test_probe_providers_returns_three_entries_with_expected_ids() -> None:
    statuses = probe_providers()
    assert len(statuses) == 3
    assert [s.id for s in statuses] == list(ALL_PROVIDER_IDS)


@pytest.mark.parametrize("provider_id", ["cursor", "claude", "codex"])
def test_probe_provider_auth_fields_task_073(
    provider_id: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key in ("CURSOR_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    status = probe_provider(provider_id)  # type: ignore[arg-type]
    assert status.authenticated is False
    assert status.auth_source == "missing"


def test_cursor_installed_tracks_find_spec() -> None:
    with patch("cascade.agent.providers.importlib.util.find_spec", return_value=object()):
        status = probe_provider("cursor")
        assert status.installed is True

    with patch("cascade.agent.providers.importlib.util.find_spec", return_value=None):
        status = probe_provider("cursor")
        assert status.installed is False


@pytest.mark.parametrize("provider_id, binary", [("claude", "claude"), ("codex", "codex")])
def test_cli_installed_tracks_which(
    provider_id: str,
    binary: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "cascade.agent.providers.shutil.which",
        lambda name: "/usr/bin/" + name if name == binary else None,
    )
    status = probe_provider(provider_id)  # type: ignore[arg-type]
    assert status.installed is True

    monkeypatch.setattr("cascade.agent.providers.shutil.which", lambda _name: None)
    status = probe_provider(provider_id)  # type: ignore[arg-type]
    assert status.installed is False


def test_provider_status_only_documented_fields() -> None:
    fields = {f.name for f in dataclasses.fields(ProviderStatus)}
    assert fields == {"id", "installed", "authenticated", "auth_source"}


@pytest.mark.parametrize("provider_id", ["cursor", "claude", "codex"])
def test_parse_provider_id_accepts_legal_ids(provider_id: str) -> None:
    assert parse_provider_id(provider_id) == provider_id


@pytest.mark.parametrize(
    "value",
    ["", "   ", "unknown", 42, None, []],
)
def test_parse_provider_id_rejects_invalid(value: object) -> None:
    with pytest.raises(ProviderConfigError):
        parse_provider_id(value)
