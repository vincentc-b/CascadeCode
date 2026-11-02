"""Pure provider/model capability checks for lifecycle dispatch boundaries.

The lifecycle owns when inventory is refreshed and how a failed check is
persisted.  This module only classifies a requested backend against the
inventory it was given, so using it cannot start a provider process, make a
network request, or mutate board state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from cascade.agent.discovery.inventory import ProviderInventoryItem, ProviderInventoryResult
from cascade.agent.providers import ProviderId

WorkTier = Literal["epic", "feature", "task"]
PreflightOutcome = Literal["supported", "unsupported", "unavailable"]
PreflightReason = Literal[
    "available",
    "invalid_tier",
    "invalid_model",
    "model_not_offered",
    "reasoning_not_supported",
    "flex_mode_not_supported",
    "provider_unavailable",
]


@dataclass(frozen=True)
class ProviderCapabilityPreflight:
    """A safe-to-persist description of a requested backend's availability.

    ``unsupported`` is deterministic for the supplied inventory: retrying the
    same configuration will not help.  ``unavailable`` represents provider or
    setup/discovery failure and is retryable after the environment changes.
    """

    outcome: PreflightOutcome
    reason: PreflightReason
    provider: ProviderId
    model_id: str
    tier: str
    message: str
    retryable: bool

    @property
    def supported(self) -> bool:
        return self.outcome == "supported"


def preflight_provider_capability(
    *,
    provider: ProviderId,
    model_id: str,
    tier: WorkTier | str,
    inventory: ProviderInventoryResult,
    reasoning_level: str | None = None,
    flex_mode: bool | None = None,
) -> ProviderCapabilityPreflight:
    """Classify a provider/model request using an already obtained inventory.

    Callers deliberately supply the inventory.  That keeps this shared check
    pure and lets a lifecycle boundary choose cache/refresh policy separately.
    """

    clean_model = model_id.strip()
    if tier not in ("epic", "feature", "task"):
        return _unsupported(
            "invalid_tier", provider, clean_model, tier, f"unknown work tier {tier!r}"
        )
    if not clean_model:
        return _unsupported("invalid_model", provider, clean_model, tier, "model id is required")

    item = _provider_item(provider, inventory)
    if item is None:
        failure = next((entry for entry in inventory.failures if entry.provider_id == provider), None)
        detail = failure.message if failure and failure.message else "provider is unavailable"
        return ProviderCapabilityPreflight(
            outcome="unavailable",
            reason="provider_unavailable",
            provider=provider,
            model_id=clean_model,
            tier=tier,
            message=detail,
            retryable=True,
        )

    model = next((candidate for candidate in item.models if candidate.id == clean_model), None)
    if model is None:
        return _unsupported(
            "model_not_offered",
            provider,
            clean_model,
            tier,
            f"model {clean_model!r} is not offered by {provider}",
        )
    if reasoning_level:
        capability = model.reasoning
        allowed = (
            {capability.default_level, *capability.override_levels}
            if capability is not None and capability.supports_overrides
            else set()
        )
        if reasoning_level not in allowed:
            return _unsupported(
                "reasoning_not_supported",
                provider,
                clean_model,
                tier,
                f"reasoning level {reasoning_level!r} is not supported by model {clean_model!r}",
            )
    if flex_mode and not item.supports_flex_mode:
        return _unsupported(
            "flex_mode_not_supported",
            provider,
            clean_model,
            tier,
            f"provider {provider!r} does not support flex mode",
        )
    return ProviderCapabilityPreflight(
        outcome="supported",
        reason="available",
        provider=provider,
        model_id=clean_model,
        tier=tier,
        message="provider capability is available",
        retryable=False,
    )


def _provider_item(
    provider: ProviderId, inventory: ProviderInventoryResult) -> ProviderInventoryItem | None:
    return next((item for item in inventory.providers if item.provider_id == provider), None)


def _unsupported(
    reason: PreflightReason,
    provider: ProviderId,
    model_id: str,
    tier: str,
    message: str,
) -> ProviderCapabilityPreflight:
    return ProviderCapabilityPreflight(
        outcome="unsupported",
        reason=reason,
        provider=provider,
        model_id=model_id,
        tier=tier,
        message=message,
        retryable=False,
    )
