"""Provider discovery adapter registry."""

from __future__ import annotations

from collections.abc import Callable

from cascade.agent.discovery.claude_adapter import discover_claude_models
from cascade.agent.discovery.codex_adapter import discover_codex_models
from cascade.agent.discovery.cursor_adapter import discover_cursor_models
from cascade.agent.discovery.types import ProviderDiscoverySnapshot
from cascade.agent.providers import ALL_PROVIDER_IDS, ProviderId

DiscoverFn = Callable[[], ProviderDiscoverySnapshot]

_ADAPTERS: dict[ProviderId, DiscoverFn] = {
    "cursor": discover_cursor_models,
    "claude": discover_claude_models,
    "codex": discover_codex_models,
}


def discover_provider(provider_id: ProviderId) -> ProviderDiscoverySnapshot:
    try:
        fn = _ADAPTERS[provider_id]
    except KeyError as exc:
        raise ValueError(f"no discovery adapter for provider {provider_id!r}") from exc
    return fn()


def discover_all_providers() -> tuple[ProviderDiscoverySnapshot, ...]:
    return tuple(discover_provider(pid) for pid in ALL_PROVIDER_IDS)
