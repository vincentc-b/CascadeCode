"""Shared provider capability preflight contract."""

from __future__ import annotations

from dataclasses import replace

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel, ReasoningCapability
from cascade.agent.preflight import preflight_provider_capability


def _inventory(*, flex: bool = True) -> ProviderInventoryResult:
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(
                    DiscoveredModel(
                        id="gpt-5",
                        display_name="GPT-5",
                        reasoning=ReasoningCapability(
                            default_level="medium", override_levels=("low", "high")
                        ),
                    ),
                ),
                supports_flex_mode=flex,
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )


def test_preflight_accepts_offered_model_and_supported_capabilities() -> None:
    result = preflight_provider_capability(
        provider="codex",
        model_id=" gpt-5 ",
        tier="task",
        inventory=_inventory(),
        reasoning_level="high",
        flex_mode=True,
    )

    assert result.supported
    assert result.outcome == "supported"
    assert result.reason == "available"
    assert result.model_id == "gpt-5"
    assert not result.retryable


def test_preflight_marks_bad_configuration_as_deterministically_unsupported() -> None:
    result = preflight_provider_capability(
        provider="codex", model_id="missing", tier="feature", inventory=_inventory()
    )

    assert result.outcome == "unsupported"
    assert result.reason == "model_not_offered"
    assert not result.retryable


def test_preflight_validates_reasoning_and_flex_capabilities() -> None:
    reasoning = preflight_provider_capability(
        provider="codex",
        model_id="gpt-5",
        tier="epic",
        inventory=_inventory(),
        reasoning_level="max",
    )
    flex = preflight_provider_capability(
        provider="codex", model_id="gpt-5", tier="epic", inventory=_inventory(flex=False), flex_mode=True
    )

    assert reasoning.reason == "reasoning_not_supported"
    assert flex.reason == "flex_mode_not_supported"
    assert not reasoning.retryable and not flex.retryable


def test_preflight_rejects_model_without_flex_even_when_provider_offers_it() -> None:
    inventory = _inventory()
    provider = inventory.providers[0]
    model = replace(provider.models[0], supports_flex_mode=False)
    inventory = replace(inventory, providers=(replace(provider, models=(model,)),))
    result = preflight_provider_capability(
        provider="codex", model_id="gpt-5", tier="epic", inventory=inventory, flex_mode=True
    )
    assert result.reason == "flex_mode_not_supported"


def test_preflight_marks_provider_discovery_failure_as_retryable() -> None:
    inventory = ProviderInventoryResult(
        providers=(),
        failures=(
            ProviderInventoryFailure(
                provider_id="codex", reason="not_authenticated", message="sign in required"
            ),
        ),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )

    result = preflight_provider_capability(
        provider="codex", model_id="gpt-5", tier="task", inventory=inventory
    )

    assert result.outcome == "unavailable"
    assert result.reason == "provider_unavailable"
    assert result.retryable
    assert result.message == "sign in required"
