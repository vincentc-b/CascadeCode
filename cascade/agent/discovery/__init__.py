"""Provider model discovery adapters and normalized inventory contracts."""

from cascade.agent.discovery.adapters import discover_all_providers, discover_provider
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
    "ProviderDiscoveryAdapter",
    "ProviderDiscoverySnapshot",
    "ReasoningCapability",
    "discover_all_providers",
    "discover_provider",
]
