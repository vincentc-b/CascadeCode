"""Provider inventory aggregation and cache (task_006_001_002)."""

from __future__ import annotations

import pytest

from cascade.agent.discovery.inventory import (
    clear_provider_inventory_cache,
    get_provider_inventory,
    refresh_provider_inventory,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderDiscoverySnapshot,
    ReasoningCapability,
)
from cascade.agent.providers import ALL_PROVIDER_IDS, ProviderId


def _model(model_id: str) -> DiscoveredModel:
    return DiscoveredModel(id=model_id, display_name=model_id.title())


def _available(provider_id: ProviderId, *model_ids: str) -> ProviderDiscoverySnapshot:
    return ProviderDiscoverySnapshot(
        provider_id=provider_id,
        available=True,
        models=tuple(_model(mid) for mid in model_ids),
    )


def _unavailable(
    provider_id: ProviderId,
    *,
    failure: str = "not_authenticated",
    message: str | None = None,
) -> ProviderDiscoverySnapshot:
    return ProviderDiscoverySnapshot(
        provider_id=provider_id,
        available=False,
        failure=failure,  # type: ignore[arg-type]
        message=message,
    )


def _fake_discover(
    mapping: dict[ProviderId, ProviderDiscoverySnapshot],
) -> callable:
    calls: list[ProviderId] = []

    def discover(provider_id: ProviderId) -> ProviderDiscoverySnapshot:
        calls.append(provider_id)
        return mapping[provider_id]

    discover.calls = calls  # type: ignore[attr-defined]
    return discover


@pytest.fixture(autouse=True)
def _clear_inventory_cache() -> None:
    clear_provider_inventory_cache()
    yield
    clear_provider_inventory_cache()


def test_filters_unavailable_providers() -> None:
    mapping = {
        "cursor": _available("cursor", "composer-2.5"),
        "claude": _unavailable("claude", failure="not_installed"),
        "codex": _unavailable("codex", failure="not_authenticated"),
    }
    discover = _fake_discover(mapping)
    result = refresh_provider_inventory(discover=discover, ttl_seconds=60.0, now=100.0)

    assert [item.provider_id for item in result.providers] == ["cursor"]
    assert len(result.failures) == 2
    assert {failure.provider_id for failure in result.failures} == {"claude", "codex"}
    assert result.freshness.from_cache is False
    assert result.freshness.fetched_at == 100.0
    assert result.freshness.expires_at == 160.0


def test_partial_failure_keeps_healthy_providers() -> None:
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _available("claude", "claude-a"),
        "codex": _unavailable(
            "codex",
            failure="api_error",
            message="RuntimeError",
        ),
    }
    discover = _fake_discover(mapping)
    result = refresh_provider_inventory(discover=discover, now=0.0)

    assert {item.provider_id for item in result.providers} == {"cursor", "claude"}
    assert len(result.failures) == 1
    assert result.failures[0].provider_id == "codex"
    assert result.failures[0].message == "RuntimeError"


def test_sanitizes_secret_bearing_failure_messages() -> None:
    mapping = {
        "cursor": _unavailable("cursor"),
        "claude": _unavailable("claude"),
        "codex": _unavailable(
            "codex",
            failure="api_error",
            message="token=super-secret-value",
        ),
    }
    discover = _fake_discover(mapping)
    result = refresh_provider_inventory(discover=discover, now=0.0)

    codex_failure = next(item for item in result.failures if item.provider_id == "codex")
    assert codex_failure.message == "discovery failed"
    assert "secret" not in (codex_failure.message or "")


def test_cache_hit_avoids_rediscovery() -> None:
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _unavailable("claude"),
        "codex": _unavailable("codex"),
    }
    discover = _fake_discover(mapping)

    first = get_provider_inventory(discover=discover, ttl_seconds=30.0, now=10.0)
    second = get_provider_inventory(discover=discover, ttl_seconds=30.0, now=20.0)

    assert first.freshness.from_cache is False
    assert second.freshness.from_cache is True
    assert len(discover.calls) == len(ALL_PROVIDER_IDS)  # type: ignore[attr-defined]
    assert second.providers == first.providers


def test_cache_expiry_rediscovers() -> None:
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _unavailable("claude"),
        "codex": _unavailable("codex"),
    }
    discover = _fake_discover(mapping)

    get_provider_inventory(discover=discover, ttl_seconds=30.0, now=0.0)
    expired = get_provider_inventory(discover=discover, ttl_seconds=30.0, now=31.0)

    assert expired.freshness.from_cache is False
    assert len(discover.calls) == 2 * len(ALL_PROVIDER_IDS)  # type: ignore[attr-defined]


def test_force_refresh_bypasses_fresh_cache() -> None:
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _unavailable("claude"),
        "codex": _unavailable("codex"),
    }
    discover = _fake_discover(mapping)

    get_provider_inventory(discover=discover, ttl_seconds=60.0, now=5.0)
    refreshed = get_provider_inventory(
        discover=discover,
        ttl_seconds=60.0,
        now=6.0,
        force_refresh=True,
    )

    assert refreshed.freshness.from_cache is False
    assert len(discover.calls) == 2 * len(ALL_PROVIDER_IDS)  # type: ignore[attr-defined]


def test_isolates_adapter_exceptions() -> None:
    calls: list[ProviderId] = []

    def discover(provider_id: ProviderId) -> ProviderDiscoverySnapshot:
        calls.append(provider_id)
        if provider_id == "claude":
            raise RuntimeError("upstream blew up with sk-abcdef1234567890")
        if provider_id == "cursor":
            return _available("cursor", "auto")
        return _unavailable("codex")

    result = refresh_provider_inventory(discover=discover, now=0.0)

    assert [item.provider_id for item in result.providers] == ["cursor"]
    claude_failure = next(item for item in result.failures if item.provider_id == "claude")
    assert claude_failure.reason == "api_error"
    assert claude_failure.message == "RuntimeError"
    assert len(calls) == len(ALL_PROVIDER_IDS)


def test_provider_display_metadata() -> None:
    mapping = {
        "cursor": _available("cursor", "auto"),
        "claude": _available("claude", "claude-a"),
        "codex": _available("codex", "gpt-5"),
    }
    discover = _fake_discover(mapping)
    result = refresh_provider_inventory(discover=discover, now=0.0)

    assert [item.display_name for item in result.providers] == [
        "Claude Code",
        "Codex",
        "Cursor",
    ]
    reasoning = DiscoveredModel(
        id="x",
        display_name="X",
        reasoning=ReasoningCapability(default_level="low", override_levels=("low", "high")),
    )
    assert reasoning.reasoning is not None
    assert reasoning.reasoning.supports_overrides
