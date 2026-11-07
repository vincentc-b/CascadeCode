"""Pure normalization of discovery observations into capability evidence."""

from __future__ import annotations

from cascade.agent.capability_contract import (
    CapabilityEvidence,
    DiscoveryFailureKind,
    ModelCapabilityEvidence,
    ProviderAvailability,
    UnknownEvidenceKind,
)
from cascade.agent.discovery.adapters import supports_discovery_adapter
from cascade.agent.discovery.inventory import ProviderInventoryResult
from cascade.agent.discovery.types import (
    DiscoveryFailureReason,
    ProviderCompatibilityEvidence,
    ProviderDiscoverySnapshot,
)

_FAILURE_KINDS: dict[DiscoveryFailureReason, DiscoveryFailureKind | None] = {
    "not_installed": "provider_not_installed",
    "not_authenticated": "provider_not_authenticated",
    "discovery_unavailable": "discovery_unavailable",
    "empty": "discovery_empty",
    "provider_unavailable": None,
    "temporarily_unavailable": "provider_temporarily_unavailable",
    "api_error": "discovery_unavailable",
}


def _model_evidence(
    snapshot: ProviderDiscoverySnapshot,
) -> tuple[ModelCapabilityEvidence, ...]:
    models: list[ModelCapabilityEvidence] = []
    for model in snapshot.models:
        reasoning = model.reasoning
        levels: tuple[str, ...] | None = None
        default: str | None = None
        if reasoning is not None:
            default = reasoning.default_level
            levels = reasoning.override_levels or (reasoning.default_level,)
        models.append(
            ModelCapabilityEvidence(
                model_id=model.id,
                reasoning_levels=levels,
                default_reasoning_level=default,
                supports_flex_mode=model.supports_flex_mode,
            )
        )
    return tuple(models)


def normalize_capability_evidence(
    provider: str,
    *,
    snapshot: ProviderDiscoverySnapshot | None,
    adapter_supported: bool | None = None,
    compatibility: ProviderCompatibilityEvidence | None = None,
) -> CapabilityEvidence:
    """Normalize already-observed facts without performing environmental probes.

    Unknown values stay unknown. In particular, a missing snapshot or absent
    model metadata never becomes verified provider, model, Flex, or reasoning
    support.
    """

    observed = compatibility or ProviderCompatibilityEvidence()
    if adapter_supported is None:
        adapter_supported = supports_discovery_adapter(provider)
    availability: ProviderAvailability = "unknown"
    failure_kind: DiscoveryFailureKind | None = None
    catalog: tuple[ModelCapabilityEvidence, ...] | None = None
    provider_flex: bool | None = None

    if adapter_supported is False:
        snapshot = None
    elif snapshot is not None:
        provider_flex = snapshot.supports_flex_mode
        if snapshot.available and snapshot.models:
            availability = "available"
            catalog = _model_evidence(snapshot)
        else:
            reason = snapshot.failure or (
                "empty" if snapshot.available else "discovery_unavailable"
            )
            failure_kind = _FAILURE_KINDS[reason]
            if reason == "empty":
                availability = "available"
                catalog = ()
            elif reason == "discovery_unavailable" or reason == "api_error":
                availability = "unknown"
            else:
                availability = "unavailable"

    unknown: list[UnknownEvidenceKind] = []
    if availability == "unknown":
        unknown.append("provider_availability")
    if catalog is None:
        unknown.append("model_catalog")
    elif any(model.reasoning_levels is None for model in catalog):
        unknown.append("model_reasoning")
    if catalog is not None and any(
        model.supports_flex_mode is None for model in catalog
    ):
        unknown.append("model_flex")
    if provider_flex is None:
        unknown.append("provider_flex")
    if observed.cli_compatible is None:
        unknown.append("cli")
    if observed.sdk_compatible is None:
        unknown.append("sdk")
    if observed.required_tool_host_compatible is None:
        unknown.append("tool_host")

    return CapabilityEvidence(
        provider=provider,
        provider_availability=availability,
        discovery_failure_kind=failure_kind,
        verified_model_catalog=catalog,
        provider_supports_flex_mode=provider_flex,
        cli_compatible=observed.cli_compatible,
        sdk_compatible=observed.sdk_compatible,
        required_tool_host_compatible=observed.required_tool_host_compatible,
        adapter_supported=adapter_supported,
        unknown_evidence=tuple(unknown),
        setup_evidence_available=observed.setup_evidence_available
        or failure_kind in {"provider_not_installed", "provider_not_authenticated"},
    )


def capability_evidence_from_inventory(
    provider: str,
    inventory: ProviderInventoryResult,
    *,
    adapter_supported: bool | None = None,
    compatibility: ProviderCompatibilityEvidence | None = None,
) -> CapabilityEvidence:
    """Project one provider's aggregate inventory entry to evaluator evidence."""

    item = next(
        (entry for entry in inventory.providers if entry.provider_id == provider), None
    )
    if item is not None:
        snapshot = ProviderDiscoverySnapshot(
            provider_id=item.provider_id,
            available=True,
            models=item.models,
            supports_flex_mode=item.supports_flex_mode,
        )
    else:
        failure = next(
            (entry for entry in inventory.failures if entry.provider_id == provider),
            None,
        )
        snapshot = (
            None
            if failure is None
            else ProviderDiscoverySnapshot(
                provider_id=failure.provider_id,
                available=False,
                failure=failure.reason,
            )
        )
    return normalize_capability_evidence(
        provider,
        snapshot=snapshot,
        adapter_supported=adapter_supported,
        compatibility=compatibility,
    )
