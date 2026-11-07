"""Focused safe normalization checks for provider capability evidence."""

from __future__ import annotations

import json

import pytest

from cascade.agent.capability_contract import contract_projection
from cascade.agent.discovery.evidence import normalize_capability_evidence
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderCompatibilityEvidence,
    ProviderDiscoverySnapshot,
    ReasoningCapability,
)


@pytest.mark.parametrize(
    ("reason", "availability", "failure_kind"),
    [
        ("not_installed", "unavailable", "provider_not_installed"),
        ("not_authenticated", "unavailable", "provider_not_authenticated"),
        ("discovery_unavailable", "unknown", "discovery_unavailable"),
        ("empty", "available", "discovery_empty"),
        ("provider_unavailable", "unavailable", None),
        (
            "temporarily_unavailable",
            "unavailable",
            "provider_temporarily_unavailable",
        ),
    ],
)
def test_normalizes_distinct_discovery_failures(
    reason: str,
    availability: str,
    failure_kind: str | None,
) -> None:
    evidence = normalize_capability_evidence(
        "codex",
        snapshot=ProviderDiscoverySnapshot(
            provider_id="codex",
            available=reason == "empty",
            failure=reason,  # type: ignore[arg-type]
            message="raw upstream token=must-not-escape",
        ),
    )

    assert evidence.provider_availability == availability
    assert evidence.discovery_failure_kind == failure_kind
    assert evidence.verified_model_catalog == (() if reason == "empty" else None)
    assert "raw upstream" not in json.dumps(contract_projection(evidence))


def test_unknown_metadata_and_compatibility_never_become_verified_support() -> None:
    evidence = normalize_capability_evidence(
        "cursor",
        snapshot=ProviderDiscoverySnapshot(
            provider_id="cursor",
            available=True,
            models=(DiscoveredModel(id="auto", display_name="Auto"),),
        ),
    )

    assert evidence.provider_availability == "available"
    assert evidence.provider_supports_flex_mode is None
    assert evidence.verified_model_catalog is not None
    assert evidence.verified_model_catalog[0].reasoning_levels is None
    assert evidence.verified_model_catalog[0].supports_flex_mode is None
    assert evidence.unknown_evidence == (
        "model_reasoning",
        "model_flex",
        "provider_flex",
        "cli",
        "sdk",
        "tool_host",
    )


def test_reasoning_evidence_includes_default_with_override_levels() -> None:
    evidence = normalize_capability_evidence(
        "codex",
        snapshot=ProviderDiscoverySnapshot(
            provider_id="codex",
            available=True,
            models=(
                DiscoveredModel(
                    id="gpt-safe",
                    display_name="GPT Safe",
                    reasoning=ReasoningCapability("medium", ("low", "high")),
                ),
            ),
        ),
    )

    assert evidence.verified_model_catalog is not None
    assert evidence.verified_model_catalog[0].reasoning_levels == (
        "medium",
        "low",
        "high",
    )


def test_explicit_adapter_and_environment_rejections_remain_distinct() -> None:
    unsupported = normalize_capability_evidence(
        "future-provider",
        snapshot=None,
    )
    incompatible = normalize_capability_evidence(
        "codex",
        snapshot=ProviderDiscoverySnapshot(
            provider_id="codex",
            available=True,
            models=(
                DiscoveredModel(
                    id="gpt-safe",
                    display_name="GPT Safe",
                    reasoning=ReasoningCapability("medium", ("low", "medium")),
                    supports_flex_mode=True,
                ),
            ),
            supports_flex_mode=True,
        ),
        compatibility=ProviderCompatibilityEvidence(
            cli_compatible=False,
            sdk_compatible=False,
            required_tool_host_compatible=False,
            setup_evidence_available=True,
        ),
    )

    assert unsupported.adapter_supported is False
    assert unsupported.verified_model_catalog is None
    assert incompatible.adapter_supported is True
    assert incompatible.cli_compatible is False
    assert incompatible.sdk_compatible is False
    assert incompatible.required_tool_host_compatible is False
    assert incompatible.unknown_evidence == ()
    assert incompatible.setup_evidence_available is True
