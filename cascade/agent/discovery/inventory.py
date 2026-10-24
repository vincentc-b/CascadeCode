"""Aggregate provider discovery with a bounded freshness cache (task_006_001_002)."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cascade.agent.discovery.adapters import discover_provider
from cascade.agent.discovery.availability import unavailable_snapshot
from cascade.agent.discovery.normalize import sanitize_provider_error
from cascade.agent.discovery.types import (
    DiscoveredModel,
    DiscoveryFailureReason,
    ProviderDiscoverySnapshot,
)
from cascade.agent.providers import ALL_PROVIDER_IDS, ProviderId, provider_display_name

DEFAULT_INVENTORY_TTL_SECONDS = 300.0
_MAX_CACHE_ENTRIES = 1
_SECRET_LIKE = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|authorization|bearer)\s*[:=]|sk-[a-z0-9]{8,}"
)

DiscoverFn = Callable[[ProviderId], ProviderDiscoverySnapshot]


@dataclass(frozen=True)
class ProviderInventoryItem:
    """One available provider with models discovered from its API."""

    provider_id: ProviderId
    display_name: str
    models: tuple[DiscoveredModel, ...]


@dataclass(frozen=True)
class ProviderInventoryFailure:
    """Sanitized unavailable provider; never includes credentials or raw upstream payloads."""

    provider_id: ProviderId
    reason: DiscoveryFailureReason
    message: str | None = None


@dataclass(frozen=True)
class InventoryFreshness:
    """Whether the payload came from cache and when it expires."""

    from_cache: bool
    fetched_at: float
    expires_at: float
    ttl_seconds: float


@dataclass(frozen=True)
class ProviderInventoryResult:
    """Authoritative multi-provider inventory for application boundaries."""

    providers: tuple[ProviderInventoryItem, ...]
    failures: tuple[ProviderInventoryFailure, ...]
    freshness: InventoryFreshness


@dataclass
class _CacheEntry:
    result: ProviderInventoryResult
    expires_at: float


_cache_lock = threading.RLock()
_cache: dict[str, _CacheEntry] = {}


def clear_provider_inventory_cache() -> None:
    """Drop cached inventory (tests only)."""

    with _cache_lock:
        _cache.clear()


def _sanitize_failure_message(message: str | None) -> str | None:
    if message is None:
        return None
    stripped = message.strip()
    if not stripped:
        return None
    if _SECRET_LIKE.search(stripped):
        return "discovery failed"
    return stripped


def _discover_isolated(
    provider_id: ProviderId,
    discover: DiscoverFn,
) -> ProviderDiscoverySnapshot:
    try:
        return discover(provider_id)
    except Exception as exc:
        return unavailable_snapshot(
            provider_id,
            failure="api_error",
            message=sanitize_provider_error(exc),
        )


def _aggregate_snapshots(
    snapshots: Sequence[ProviderDiscoverySnapshot],
) -> tuple[tuple[ProviderInventoryItem, ...], tuple[ProviderInventoryFailure, ...]]:
    providers: list[ProviderInventoryItem] = []
    failures: list[ProviderInventoryFailure] = []

    for snap in snapshots:
        if snap.available and snap.models:
            providers.append(
                ProviderInventoryItem(
                    provider_id=snap.provider_id,
                    display_name=provider_display_name(snap.provider_id),
                    models=snap.models,
                )
            )
            continue

        reason = snap.failure or "api_error"
        failures.append(
            ProviderInventoryFailure(
                provider_id=snap.provider_id,
                reason=reason,
                message=_sanitize_failure_message(snap.message),
            )
        )

    providers.sort(key=lambda item: (item.display_name.casefold(), item.provider_id))
    failures.sort(key=lambda item: item.provider_id)
    return tuple(providers), tuple(failures)


def refresh_provider_inventory(
    *,
    discover: DiscoverFn | None = None,
    ttl_seconds: float = DEFAULT_INVENTORY_TTL_SECONDS,
    now: float | None = None,
) -> ProviderInventoryResult:
    """Discover all configured providers and return a normalized aggregate (no cache read/write)."""

    discover_fn = discover or discover_provider
    fetched_at = time.monotonic() if now is None else now
    ttl = max(0.0, ttl_seconds)
    snapshots = tuple(
        _discover_isolated(pid, discover_fn) for pid in ALL_PROVIDER_IDS
    )
    provider_items, failure_items = _aggregate_snapshots(snapshots)
    freshness = InventoryFreshness(
        from_cache=False,
        fetched_at=fetched_at,
        expires_at=fetched_at + ttl,
        ttl_seconds=ttl,
    )
    return ProviderInventoryResult(
        providers=provider_items,
        failures=failure_items,
        freshness=freshness,
    )


def _store_cache(result: ProviderInventoryResult) -> None:
    with _cache_lock:
        while len(_cache) >= _MAX_CACHE_ENTRIES:
            oldest_key = min(_cache, key=lambda key: _cache[key].expires_at)
            del _cache[oldest_key]
        _cache["aggregate"] = _CacheEntry(
            result=result,
            expires_at=result.freshness.expires_at,
        )


def _cached_result(now: float) -> ProviderInventoryResult | None:
    with _cache_lock:
        entry = _cache.get("aggregate")
        if entry is None or entry.expires_at <= now:
            if entry is not None:
                del _cache["aggregate"]
            return None
        cached = entry.result
        freshness = InventoryFreshness(
            from_cache=True,
            fetched_at=cached.freshness.fetched_at,
            expires_at=cached.freshness.expires_at,
            ttl_seconds=cached.freshness.ttl_seconds,
        )
        return ProviderInventoryResult(
            providers=cached.providers,
            failures=cached.failures,
            freshness=freshness,
        )


def get_provider_inventory(
    *,
    force_refresh: bool = False,
    discover: DiscoverFn | None = None,
    ttl_seconds: float = DEFAULT_INVENTORY_TTL_SECONDS,
    now: float | None = None,
) -> ProviderInventoryResult:
    """Return the cached inventory when fresh; otherwise discover and cache the aggregate."""

    current = time.monotonic() if now is None else now
    if not force_refresh:
        hit = _cached_result(current)
        if hit is not None:
            return hit

    result = refresh_provider_inventory(
        discover=discover,
        ttl_seconds=ttl_seconds,
        now=current,
    )
    _store_cache(result)
    return result
