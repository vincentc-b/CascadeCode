"""Provider model discovery adapters and normalized inventory contracts."""

from cascade.agent.discovery.adapters import discover_all_providers, discover_provider
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
    clear_provider_inventory_cache,
    get_provider_inventory,
    refresh_provider_inventory,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    DiscoveryFailureReason,
    ProviderDiscoveryAdapter,
    ProviderDiscoverySnapshot,
    ReasoningCapability,
)

__all__ = [
    "DiscoveredModel",
    "DiscoveryFailureReason",
    "InventoryFreshness",
    "ProviderDiscoveryAdapter",
    "ProviderDiscoverySnapshot",
    "ProviderInventoryFailure",
    "ProviderInventoryItem",
    "ProviderInventoryResult",
    "ReasoningCapability",
    "clear_provider_inventory_cache",
    "discover_all_providers",
    "discover_provider",
    "get_provider_inventory",
    "refresh_provider_inventory",
]
