"""Brief provider inventory HTTP contract (task_006_001_003)."""

from __future__ import annotations

import json
import urllib.request
from http import HTTPStatus

import pytest

from cascade.agent.discovery.inventory import (
    clear_provider_inventory_cache,
    get_provider_inventory,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderDiscoverySnapshot,
    ReasoningCapability,
)
from cascade.agent.providers import ProviderId
from tests.agent.test_provider_inventory import _available, _fake_discover, _unavailable
from tests.war_room.test_http_read import war_room_server


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=b"{}",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _inventory_get(monkeypatch: pytest.MonkeyPatch, mapping: dict[ProviderId, ProviderDiscoverySnapshot]) -> None:
    discover = _fake_discover(mapping)

    def _get_inventory(**kwargs: object) -> object:
        return get_provider_inventory(
            discover=discover,
            ttl_seconds=60.0,
            now=10.0,
            force_refresh=bool(kwargs.get("force_refresh")),
        )

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", _get_inventory)


@pytest.fixture(autouse=True)
def _clear_inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


def test_brief_inventory_success_contract(war_room_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _root, _server = war_room_server
    reasoning = ReasoningCapability(default_level="medium", override_levels=("low", "high"))
    cursor_model = DiscoveredModel(
        id="composer-2.5",
        display_name="Composer 2.5",
        reasoning=reasoning,
    )
    mapping = {
        "cursor": ProviderDiscoverySnapshot(
            provider_id="cursor",
            available=True,
            models=(cursor_model,),
        ),
        "claude": _unavailable("claude", failure="not_installed"),
        "codex": _unavailable("codex", failure="not_authenticated"),
    }
    _inventory_get(monkeypatch, mapping)

    status, payload = _get(f"{base}/api/brief/inventory")

    assert status == HTTPStatus.OK
    assert payload["availability"] == "partial"
    assert payload["loading"] is False
    assert payload["default_provider"] == "cursor"
    assert len(payload["providers"]) == 1
    provider = payload["providers"][0]
    assert provider["id"] == "cursor"
    assert provider["display_name"] == "Cursor"
    model = provider["models"][0]
    assert model["id"] == "composer-2.5"
    assert model["reasoning"]["default_level"] == "medium"
    assert model["reasoning"]["override_levels"] == ["low", "high"]
    assert model["reasoning"]["default_only"] is False
    assert payload["freshness"]["from_cache"] is False
    assert payload["refresh"] == {"forced": False, "failed": False, "error": None}


def test_brief_inventory_partial_failure_keeps_healthy_providers(
    war_room_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _root, _server = war_room_server
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _available("claude", "claude-a"),
        "codex": _unavailable("codex", failure="api_error", message="upstream timeout"),
    }
    _inventory_get(monkeypatch, mapping)

    _status, payload = _get(f"{base}/api/brief/inventory")

    assert payload["availability"] == "partial"
    assert {item["id"] for item in payload["providers"]} == {"cursor", "claude"}
    assert len(payload["failures"]) == 1
    assert payload["failures"][0]["id"] == "codex"
    assert payload["failures"][0]["message"] == "upstream timeout"


def test_brief_inventory_refresh_bypasses_cache(war_room_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _root, _server = war_room_server
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _unavailable("claude"),
        "codex": _unavailable("codex"),
    }
    discover = _fake_discover(mapping)

    def _get_inventory(**kwargs: object) -> object:
        return get_provider_inventory(
            discover=discover,
            ttl_seconds=60.0,
            now=10.0,
            force_refresh=bool(kwargs.get("force_refresh")),
        )

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", _get_inventory)

    _get(f"{base}/api/brief/inventory")
    status, payload = _post(f"{base}/api/brief/inventory/refresh")

    assert status == HTTPStatus.OK
    assert payload["refresh"]["forced"] is True
    assert payload["refresh"]["failed"] is False
    assert payload["freshness"]["from_cache"] is False
    assert len(discover.calls) == 2 * 3  # type: ignore[attr-defined]


def test_brief_inventory_refresh_failure_is_sanitized(
    war_room_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _root, _server = war_room_server

    def _boom(**_kwargs: object) -> object:
        raise RuntimeError("token=super-secret")

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", _boom)

    status, payload = _post(f"{base}/api/brief/inventory/refresh")

    assert status == HTTPStatus.OK
    assert payload["availability"] == "unavailable"
    assert payload["providers"] == []
    assert payload["refresh"]["failed"] is True
    assert payload["refresh"]["error"] == "RuntimeError"
    assert "secret" not in json.dumps(payload).lower()

