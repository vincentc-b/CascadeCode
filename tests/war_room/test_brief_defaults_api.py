"""Brief template and create API inventory validation (task_006_002_001)."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from http import HTTPStatus

import pytest

from cascade.agent.discovery.inventory import clear_provider_inventory_cache, get_provider_inventory
from cascade.agent.discovery.types import DiscoveredModel, ProviderDiscoverySnapshot, ReasoningCapability
from tests.agent.test_provider_inventory import _fake_discover, _unavailable
from tests.war_room.test_http_read import war_room_server


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        url,
        method="POST",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture(autouse=True)
def _clear_inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


def _patch_inventory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    provider_id: str = "codex",
    supports_flex_mode: bool = False,
) -> None:
    reasoning = ReasoningCapability(default_level="medium", override_levels=("low", "high"))
    models = (
        DiscoveredModel(id="gpt-manager", display_name="Manager"),
        DiscoveredModel(id="gpt-architect", display_name="Architect"),
        DiscoveredModel(id="gpt-feature-lead", display_name="Feature lead"),
        DiscoveredModel(id="gpt-feature-architect", display_name="Feature architect"),
        DiscoveredModel(id="gpt-swe", display_name="SWE", reasoning=reasoning),
    )
    mapping = {
        "cursor": _unavailable("cursor", failure="not_installed"),
        "claude": _unavailable("claude", failure="not_authenticated"),
        "codex": _unavailable("codex", failure="not_installed"),
    }
    mapping[provider_id] = ProviderDiscoverySnapshot(
        provider_id=provider_id,  # type: ignore[arg-type]
        available=True,
        models=models,
        supports_flex_mode=supports_flex_mode,
    )

    def _get_inventory(**kwargs: object) -> object:
        return get_provider_inventory(
            discover=_fake_discover(mapping),
            ttl_seconds=60.0,
            now=10.0,
            force_refresh=bool(kwargs.get("force_refresh")),
        )

    monkeypatch.setattr("cascade.briefs.get_provider_inventory", _get_inventory)


def test_brief_template_lists_inventory_providers(war_room_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _root, _server = war_room_server
    _patch_inventory(monkeypatch)

    status, payload = _get(f"{base}/api/brief/template")

    assert status == HTTPStatus.OK
    assert payload["providers"] == ["codex"]
    assert payload["roles"] == [
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    ]
    assert set(payload["models"]) == {
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    }


def test_create_brief_rejects_stale_model(war_room_server, monkeypatch: pytest.MonkeyPatch) -> None:
    base, _root, _server = war_room_server
    _patch_inventory(monkeypatch)
    monkeypatch.setattr("cascade.briefs.forge_ready", lambda _repo: True)
    payload = {
        "title": "Stale models",
        "intent": "Intent",
        "success_criteria": "Criteria",
        "constraints": "",
        "provider": "codex",
        "models": {
            "epic_manager": "gpt-manager",
            "epic_architect": "gpt-architect",
            "feature_lead": "gpt-feature-lead",
            "feature_architect": "gpt-feature-architect",
            "swe": "retired-model",
        },
    }

    status, body = _post_expect_error(f"{base}/api/briefs", payload)

    assert status == HTTPStatus.BAD_REQUEST
    assert "not offered" in body["error"]
