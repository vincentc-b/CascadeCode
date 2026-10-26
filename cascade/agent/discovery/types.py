"""Normalized provider discovery contracts (feat_006 / task_006_001_001)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from cascade.agent.providers import ProviderId

DiscoveryFailureReason = Literal[
    "not_installed",
    "not_authenticated",
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


@dataclass(frozen=True)
class ProviderDiscoverySnapshot:
    """Result of probing one provider adapter (no credentials in ``message``)."""

    provider_id: ProviderId
    available: bool
    models: tuple[DiscoveredModel, ...] = ()
    failure: DiscoveryFailureReason | None = None
    message: str | None = None
    supports_flex_mode: bool = False


class ProviderDiscoveryAdapter(Protocol):
    """Provider integration that lists models from the provider API."""

    @property
    def provider_id(self) -> ProviderId:
        ...

    def discover(self) -> ProviderDiscoverySnapshot:
        ...
