"""Provider model discovery adapters and normalized inventory contracts."""

from cascade.agent.discovery.adapters import (
    discover_all_providers,
    discover_provider,
    supports_discovery_adapter,
)
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
    clear_provider_inventory_cache,
    get_provider_inventory,
    project_inventory_freshness,
    refresh_provider_inventory,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    DiscoveryFailureReason,
    ProviderDiscoveryAdapter,
    ProviderDiscoverySnapshot,
    ProviderCompatibilityEvidence,
    ReasoningCapability,
)
from cascade.agent.discovery.evidence import (
    capability_evidence_from_inventory,
    normalize_capability_evidence,
)

__all__ = [
    "DiscoveredModel",
    "DiscoveryFailureReason",
    "InventoryFreshness",
    "ProviderDiscoveryAdapter",
    "ProviderDiscoverySnapshot",
    "ProviderCompatibilityEvidence",
    "ProviderInventoryFailure",
    "ProviderInventoryItem",
    "ProviderInventoryResult",
    "ReasoningCapability",
    "clear_provider_inventory_cache",
    "capability_evidence_from_inventory",
    "discover_all_providers",
    "discover_provider",
    "get_provider_inventory",
    "normalize_capability_evidence",
    "project_inventory_freshness",
    "refresh_provider_inventory",
    "supports_discovery_adapter",
]
