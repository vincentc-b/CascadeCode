"""Normalized provider discovery contracts (feat_006 / task_006_001_001)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from cascade.agent.providers import ProviderId

DiscoveryFailureReason = Literal[
    "not_installed",
    "not_authenticated",
    "discovery_unavailable",
    "empty",
    "provider_unavailable",
    "temporarily_unavailable",
    # Compatibility alias for snapshots produced by older adapters.
    "api_error",
]


@dataclass(frozen=True)
class ReasoningCapability:
    """Per-model reasoning defaults and optional override levels.

    ``override_levels`` empty means the model uses ``default_level`` only; consumers
    must not offer a reasoning selector.
    """

    default_level: str
    override_levels: tuple[str, ...] = ()

    @property
    def supports_overrides(self) -> bool:
        return bool(self.override_levels)


@dataclass(frozen=True)
class DiscoveredModel:
    """One model entry normalized for inventory consumers."""

    id: str
    display_name: str
    reasoning: ReasoningCapability | None = None
    # None means the provider did not supply per-model service-tier metadata.
    supports_flex_mode: bool | None = None


@dataclass(frozen=True)
class ProviderDiscoverySnapshot:
    """Result of probing one provider adapter (no credentials in ``message``)."""

    provider_id: ProviderId
    available: bool
    models: tuple[DiscoveredModel, ...] = ()
    failure: DiscoveryFailureReason | None = None
    message: str | None = None
    # None means discovery did not provide provider-level Flex evidence.
    supports_flex_mode: bool | None = None


@dataclass(frozen=True)
class ProviderCompatibilityEvidence:
    """Side-effect-free results from environment compatibility probes.

    The probes themselves live outside capability normalization and preflight.
    None is deliberately preserved as unknown rather than treated as support.
    """

    cli_compatible: bool | None = None
    sdk_compatible: bool | None = None
    required_tool_host_compatible: bool | None = None
    setup_evidence_available: bool = False


class ProviderDiscoveryAdapter(Protocol):
    """Provider integration that lists models from the provider API."""

    @property
    def provider_id(self) -> ProviderId: ...

    def discover(self) -> ProviderDiscoverySnapshot: ...
