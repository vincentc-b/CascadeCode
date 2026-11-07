"""Aggregate provider discovery with a bounded freshness cache (task_006_001_002)."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from cascade.agent.capability_contract import DiscoveryFailureKind
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
DiscoverFn = Callable[[ProviderId], ProviderDiscoverySnapshot]

_FAILURE_KINDS: dict[DiscoveryFailureReason, DiscoveryFailureKind | None] = {
    "not_installed": "provider_not_installed",
    "not_authenticated": "provider_not_authenticated",
    "discovery_unavailable": "discovery_unavailable",
    "empty": "discovery_empty",
    "provider_unavailable": None,
    "temporarily_unavailable": "provider_temporarily_unavailable",
    "api_error": "discovery_unavailable",
}

_FAILURE_MESSAGES: dict[DiscoveryFailureKind, str] = {
    "provider_not_installed": "Provider is not installed",
    "provider_not_authenticated": "Provider is not authenticated",
    "discovery_unavailable": "Provider discovery is unavailable",
    "discovery_empty": "Provider discovery returned no models",
    "provider_temporarily_unavailable": "Provider is temporarily unavailable",
}
_PROVIDER_UNAVAILABLE_MESSAGE = "Provider is unavailable"


@dataclass(frozen=True)
class ProviderInventoryItem:
    """One available provider with models discovered from its API."""

    provider_id: ProviderId
    display_name: str
    models: tuple[DiscoveredModel, ...]
    supports_flex_mode: bool | None = None


@dataclass(frozen=True)
class ProviderInventoryFailure:
    """Sanitized unavailable provider; never includes credentials or raw upstream payloads."""

    provider_id: ProviderId
    reason: DiscoveryFailureReason
    message: str | None = None
    failure_kind: DiscoveryFailureKind | None = None

    def __post_init__(self) -> None:
        kind = _FAILURE_KINDS[self.reason]
        safe_message = (
            _PROVIDER_UNAVAILABLE_MESSAGE if kind is None else _FAILURE_MESSAGES[kind]
        )
        object.__setattr__(self, "failure_kind", kind)
        object.__setattr__(self, "message", safe_message)


@dataclass(frozen=True)
class InventoryFreshness:
    """Portable wall-clock freshness projected for application consumers."""

    from_cache: bool
    fetched_at: float | None
    expires_at: float | None
    ttl_seconds: float
    age_seconds: float | None = None
    stale: bool = True


@dataclass(frozen=True)
class ProviderInventoryResult:
    """Authoritative multi-provider inventory for application boundaries."""

    providers: tuple[ProviderInventoryItem, ...]
    failures: tuple[ProviderInventoryFailure, ...]
    freshness: InventoryFreshness


@dataclass
class _CacheEntry:
    result: ProviderInventoryResult
    expires_at_monotonic: float


_cache_lock = threading.RLock()
_cache: dict[str, _CacheEntry] = {}


def clear_provider_inventory_cache() -> None:
    """Drop cached inventory (tests only)."""

    with _cache_lock:
        _cache.clear()


def _failure_kind(reason: DiscoveryFailureReason) -> DiscoveryFailureKind | None:
    return _FAILURE_KINDS[reason]


def project_inventory_freshness(
    freshness: InventoryFreshness,
    *,
    now: float | None = None,
) -> InventoryFreshness:
    """Calculate restart-safe age from UTC epoch timestamps.

    Monotonic deadlines never enter this function. Missing, non-finite, or
    structurally invalid wall-clock evidence has unknown age and is stale.
    Backwards clock skew is clamped to zero as required by the API contract.
    """

    current = time.time() if now is None else now
    fetched_at = freshness.fetched_at
    expires_at = freshness.expires_at
    values = (current, fetched_at, expires_at, freshness.ttl_seconds)
    valid = all(
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
        for value in values
    )
    valid = (
        valid
        and fetched_at is not None
        and expires_at is not None
        and fetched_at > 0
        and expires_at >= fetched_at
    )
    valid = valid and freshness.ttl_seconds >= 0
    if not valid:
        return InventoryFreshness(
            from_cache=freshness.from_cache,
            fetched_at=None,
            expires_at=None,
            ttl_seconds=(
                freshness.ttl_seconds
                if isinstance(freshness.ttl_seconds, (int, float))
                and not isinstance(freshness.ttl_seconds, bool)
                and math.isfinite(freshness.ttl_seconds)
                and freshness.ttl_seconds >= 0
                else 0.0
            ),
            age_seconds=None,
            stale=True,
        )
    assert fetched_at is not None and expires_at is not None
    return InventoryFreshness(
        from_cache=freshness.from_cache,
        fetched_at=freshness.fetched_at,
        expires_at=freshness.expires_at,
        ttl_seconds=freshness.ttl_seconds,
        age_seconds=max(0.0, current - fetched_at),
        stale=current >= expires_at,
    )


def _discover_isolated(
    provider_id: ProviderId,
    discover: DiscoverFn,
) -> ProviderDiscoverySnapshot:
    try:
        return discover(provider_id)
    except Exception as exc:
        return unavailable_snapshot(
            provider_id,
            failure="discovery_unavailable",
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
                    supports_flex_mode=snap.supports_flex_mode,
                )
            )
            continue

        reason = snap.failure or (
            "empty" if snap.available else "discovery_unavailable"
        )
        failure_kind = _failure_kind(reason)
        failures.append(
            ProviderInventoryFailure(
                provider_id=snap.provider_id,
                reason=reason,
                message=(
                    _PROVIDER_UNAVAILABLE_MESSAGE
                    if failure_kind is None
                    else _FAILURE_MESSAGES[failure_kind]
                ),
                failure_kind=failure_kind,
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
    fetched_at = time.time() if now is None else now
    ttl = max(0.0, ttl_seconds)
    snapshots = tuple(_discover_isolated(pid, discover_fn) for pid in ALL_PROVIDER_IDS)
    provider_items, failure_items = _aggregate_snapshots(snapshots)
    freshness = project_inventory_freshness(
        InventoryFreshness(
            from_cache=False,
            fetched_at=fetched_at,
            expires_at=fetched_at + ttl,
            ttl_seconds=ttl,
        ),
        now=fetched_at,
    )
    return ProviderInventoryResult(
        providers=provider_items,
        failures=failure_items,
        freshness=freshness,
    )


def _store_cache(
    result: ProviderInventoryResult, *, expires_at_monotonic: float
) -> None:
    with _cache_lock:
        while len(_cache) >= _MAX_CACHE_ENTRIES:
            oldest_key = min(_cache, key=lambda key: _cache[key].expires_at_monotonic)
            del _cache[oldest_key]
        _cache["aggregate"] = _CacheEntry(
            result=result,
            expires_at_monotonic=expires_at_monotonic,
        )


def _cached_result(
    monotonic_now: float, wall_now: float
) -> ProviderInventoryResult | None:
    with _cache_lock:
        entry = _cache.get("aggregate")
        if entry is None or entry.expires_at_monotonic <= monotonic_now:
            if entry is not None:
                del _cache["aggregate"]
            return None
        cached = entry.result
        freshness = project_inventory_freshness(
            InventoryFreshness(
                from_cache=True,
                fetched_at=cached.freshness.fetched_at,
                expires_at=cached.freshness.expires_at,
                ttl_seconds=cached.freshness.ttl_seconds,
            ),
            now=wall_now,
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
    wall_now: float | None = None,
) -> ProviderInventoryResult:
    """Return the cached inventory when fresh; otherwise discover and cache the aggregate."""

    monotonic_current = time.monotonic() if now is None else now
    # ``now`` remains a test-friendly compatibility clock. Production always
    # uses a wall clock for serialized timestamps and monotonic time for TTL.
    wall_current = (
        time.time()
        if wall_now is None and now is None
        else (monotonic_current if wall_now is None else wall_now)
    )
    if not force_refresh:
        hit = _cached_result(monotonic_current, wall_current)
        if hit is not None:
            return hit

    result = refresh_provider_inventory(
        discover=discover,
        ttl_seconds=ttl_seconds,
        now=wall_current,
    )
    _store_cache(
        result, expires_at_monotonic=monotonic_current + result.freshness.ttl_seconds
    )
    return result
