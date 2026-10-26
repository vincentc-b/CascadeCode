"""Provider discovery contracts and adapters (task_006_001_001)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from cascade.agent.discovery.adapters import discover_provider
from cascade.agent.discovery.claude_adapter import discover_claude_models
from cascade.agent.discovery.codex_adapter import discover_codex_models
from cascade.agent.discovery.cursor_adapter import discover_cursor_models
from cascade.agent.discovery.normalize import (
    reasoning_from_codex_record,
    reasoning_from_cursor_parameters,
)
from cascade.agent.discovery.types import ReasoningCapability
from cursor_sdk.types import (
    ModelParameterDefinition,
    ModelParameterDefinitionValue,
    ModelParameterValue,
    ModelVariant,
)


def _authenticated_probe(monkeypatch: pytest.MonkeyPatch, *, installed: bool = True) -> None:
    from cascade.agent.providers import ProviderStatus

    def fake_probe(provider_id: str) -> ProviderStatus:
        return ProviderStatus(
            id=provider_id,  # type: ignore[arg-type]
            installed=installed,
            authenticated=True,
            auth_source="env",
        )

    monkeypatch.setattr("cascade.agent.discovery.availability.probe_provider", fake_probe)


def test_reasoning_from_cursor_parameters_default_only() -> None:
    param = ModelParameterDefinition(
        id="reasoning",
        values=(ModelParameterDefinitionValue(value="medium"),),
    )
    cap = reasoning_from_cursor_parameters(parameters=(param,), variants=())
    assert cap == ReasoningCapability(default_level="medium", override_levels=())
    assert cap is not None and not cap.supports_overrides


def test_reasoning_from_cursor_parameters_with_overrides() -> None:
    param = ModelParameterDefinition(
        id="effort",
        values=(
            ModelParameterDefinitionValue(value="low"),
            ModelParameterDefinitionValue(value="high"),
        ),
    )
    variant = ModelVariant(
        params=(ModelParameterValue(id="effort", value="high"),),
        is_default=True,
    )
    cap = reasoning_from_cursor_parameters(parameters=(param,), variants=(variant,))
    assert cap == ReasoningCapability(
        default_level="high", override_levels=("low", "high")
    )
    assert cap is not None and cap.supports_overrides


def test_reasoning_from_codex_record_default_only() -> None:
    cap = reasoning_from_codex_record(
        {
            "default_reasoning_level": "low",
            "supported_reasoning_levels": [{"effort": "low"}],
            "supports_reasoning_effort_updates": False,
        }
    )
    assert cap == ReasoningCapability(default_level="low", override_levels=())


def test_reasoning_from_codex_record_with_overrides() -> None:
    cap = reasoning_from_codex_record(
        {
            "default_reasoning_level": "medium",
            "supported_reasoning_levels": [
                {"effort": "low"},
                {"effort": "medium"},
                {"effort": "high"},
            ],
            "supports_reasoning_effort_updates": False,
        }
    )
    assert cap == ReasoningCapability(
        default_level="medium", override_levels=("low", "medium", "high")
    )


def test_cursor_adapter_not_authenticated(monkeypatch: pytest.MonkeyPatch) -> None:
    from cascade.agent.providers import ProviderStatus

    monkeypatch.setattr(
        "cascade.agent.discovery.availability.probe_provider",
        lambda _pid: ProviderStatus(
            id="cursor",
            installed=True,
            authenticated=False,
            auth_source="missing",
        ),
    )
    snap = discover_cursor_models()
    assert snap.available is False
    assert snap.failure == "not_authenticated"
    assert snap.models == ()


def test_cursor_adapter_api_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated_probe(monkeypatch)
    monkeypatch.setattr(
        "cascade.agent.discovery.cursor_adapter.resolve_credential",
        lambda _pid: MagicMock(token="secret-key"),
    )

    class Boom(Exception):
        pass

    monkeypatch.setattr(
        "cascade.agent.discovery.cursor_adapter._list_cursor_sdk_models",
        lambda _key: (_ for _ in ()).throw(Boom("leaked-secret-key")),
    )
    snap = discover_cursor_models()
    assert snap.available is False
    assert snap.failure == "api_error"
    assert snap.message == "Boom"
    assert "secret" not in (snap.message or "")


def test_cursor_adapter_normalizes_models(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated_probe(monkeypatch)
    monkeypatch.setattr(
        "cascade.agent.discovery.cursor_adapter.resolve_credential",
        lambda _pid: MagicMock(token="key"),
    )

    @dataclass
    class FakeModel:
        id: str
        display_name: str
        parameters: tuple[Any, ...] = ()
        variants: tuple[Any, ...] = ()

    param = ModelParameterDefinition(
        id="reasoning",
        values=(
            ModelParameterDefinitionValue(value="fast"),
            ModelParameterDefinitionValue(value="slow"),
        ),
    )
    fake_models = [
        FakeModel(id=" composer-2.5 ", display_name=" Composer ", parameters=(param,)),
        FakeModel(id="auto", display_name="Auto"),
    ]
    monkeypatch.setattr(
        "cascade.agent.discovery.cursor_adapter._list_cursor_sdk_models",
        lambda _key: fake_models,
    )
    snap = discover_cursor_models()
    assert snap.available is True
    assert [m.id for m in snap.models] == ["auto", "composer-2.5"]
    reasoning = snap.models[1].reasoning
    assert reasoning is not None
    assert reasoning.supports_overrides


def test_codex_adapter_filters_hidden(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated_probe(monkeypatch)
    payload = {
        "models": [
            {
                "slug": "visible-model",
                "display_name": "Visible",
                "visibility": "list",
                "supported_in_api": True,
                "default_reasoning_level": "low",
                "supported_reasoning_levels": [{"effort": "low"}],
                "supports_reasoning_effort_updates": False,
            },
            {
                "slug": "hidden-model",
                "display_name": "Hidden",
                "visibility": "hidden",
            },
        ]
    }
    monkeypatch.setattr(
        "cascade.agent.discovery.codex_adapter._run_codex_debug_models",
        lambda: payload,
    )
    snap = discover_codex_models()
    assert snap.available is True
    assert [m.id for m in snap.models] == ["visible-model"]


def test_codex_adapter_api_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated_probe(monkeypatch)

    def boom() -> dict[str, object]:
        raise RuntimeError("catalog unavailable")

    monkeypatch.setattr(
        "cascade.agent.discovery.codex_adapter._run_codex_debug_models", boom
    )
    snap = discover_codex_models()
    assert snap.available is False
    assert snap.failure == "api_error"


def test_claude_adapter_paginates(monkeypatch: pytest.MonkeyPatch) -> None:
    _authenticated_probe(monkeypatch)
    monkeypatch.setattr(
        "cascade.agent.discovery.claude_adapter.resolve_credential",
        lambda _pid: MagicMock(token="anthropic-key"),
    )

    pages = [
        {
            "data": [{"id": "claude-a", "display_name": "A"}],
            "has_more": True,
            "last_id": "claude-a",
        },
        {
            "data": [{"id": "claude-b", "display_name": "B"}],
            "has_more": False,
        },
    ]

    class FakeResponse:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def read(self) -> bytes:
            return json.dumps(self._payload).encode("utf-8")

        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, *args: object) -> None:
            return None

    calls: list[str] = []

    def fake_urlopen(request: object, timeout: float = 0) -> FakeResponse:
        assert timeout == 60
        url = getattr(request, "full_url", "")
        calls.append(url)
        if "after=" in url:
            return FakeResponse(pages[1])
        return FakeResponse(pages[0])

    monkeypatch.setattr(
        "cascade.agent.discovery.claude_adapter.urllib.request.urlopen", fake_urlopen
    )
    snap = discover_claude_models()
    assert snap.available is True
    assert [m.id for m in snap.models] == ["claude-a", "claude-b"]
    assert len(calls) == 2


def test_discover_provider_unknown() -> None:
    with pytest.raises(ValueError, match="no discovery adapter"):
        discover_provider("fake")  # type: ignore[arg-type]
