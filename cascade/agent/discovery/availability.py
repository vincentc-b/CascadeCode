"""Shared preflight for provider discovery adapters."""

from __future__ import annotations

from cascade.agent.discovery.types import DiscoveryFailureReason, ProviderDiscoverySnapshot
from cascade.agent.providers import ProviderId, probe_provider


def unavailable_snapshot(
    provider_id: ProviderId,
    *,
    failure: DiscoveryFailureReason,
    message: str,
) -> ProviderDiscoverySnapshot:
    return ProviderDiscoverySnapshot(
        provider_id=provider_id,
        available=False,
        failure=failure,
        message=message,
    )


def require_probe(provider_id: ProviderId) -> ProviderDiscoverySnapshot | None:
    """Return a snapshot when the provider cannot be discovered; else ``None``."""

    status = probe_provider(provider_id)
    if not status.installed:
        return unavailable_snapshot(
            provider_id,
            failure="not_installed",
            message=f"{provider_id} is not installed",
        )
    if not status.authenticated:
        return unavailable_snapshot(
            provider_id,
            failure="not_authenticated",
            message=f"{provider_id} is not authenticated",
        )
    return None
