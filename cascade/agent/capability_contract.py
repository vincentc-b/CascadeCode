"""Shared declarations for effective selections and capability diagnostics.

This module is deliberately inert: importing or projecting these values does
not read configuration, run discovery, contact a provider, or persist state.
Resolution, fingerprinting, evidence normalization, and evaluation are owned
by the later feature tasks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Mapping, TypeAlias

WorkTier = Literal["epic", "feature", "task"]
SelectionRole = Literal[
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
]
SelectionSourceKind = Literal[
    "document-role",
    "document",
    "project-role",
    "project-tier",
    "project-default",
    "provider-default",
]
ReasonClassification = Literal["deterministic", "transient"]
ReasonCode = Literal[
    "missing_configuration",
    "malformed_configuration",
    "invalid_model",
    "invalid_tier",
    "unsupported_adapter",
    "provider_not_installed",
    "provider_not_authenticated",
    "discovery_unavailable",
    "discovery_empty",
    "provider_unavailable",
    "provider_temporarily_unavailable",
    "capability_unknown",
    "model_not_offered",
    "reasoning_not_supported",
    "flex_mode_not_supported",
    "cli_incompatible",
    "sdk_incompatible",
    "tool_host_incompatible",
    "stale_selection",
    "available",
]
Remedy = Literal[
    "migrate_or_default",
    "choose_configuration",
    "open_provider_setup",
    "refresh_and_retry",
    "continue_without_flex",
]
ProviderAvailability = Literal["available", "unavailable", "unknown"]
DiscoveryFailureKind = Literal[
    "provider_not_installed",
    "provider_not_authenticated",
    "discovery_unavailable",
    "discovery_empty",
    "provider_temporarily_unavailable",
]
UnknownEvidenceKind = Literal[
    "provider_availability",
    "model_catalog",
    "model_reasoning",
    "model_flex",
    "provider_flex",
    "cli",
    "sdk",
    "tool_host",
]

SELECTION_FINGERPRINT_SCHEMA = "selection-v1"

EPIC_ROLE_SCOPE: tuple[SelectionRole, ...] = (
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
)
FEATURE_ROLE_SCOPE: tuple[SelectionRole, ...] = (
    "feature_lead",
    "feature_architect",
    "swe",
)
TASK_ROLE_SCOPE: tuple[SelectionRole, ...] = ("swe",)
ROLE_SCOPES: Mapping[WorkTier, tuple[SelectionRole, ...]] = {
    "epic": EPIC_ROLE_SCOPE,
    "feature": FEATURE_ROLE_SCOPE,
    "task": TASK_ROLE_SCOPE,
}


@dataclass(frozen=True)
class SelectionSource:
    """Provenance for one selected field.

    ``revision`` is the owning document or project-configuration revision.
    The optional lineage fields describe inherited values without changing
    which document currently owns a stamped value.
    """

    kind: SelectionSourceKind
    revision: str
    document_path: str | None = None
    parent_revision: str | None = None
    stamping_rule: str | None = None


@dataclass(frozen=True)
class EffectiveSelection:
    """One fully resolved role selection, independent of capability evidence."""

    work_id: str
    tier: WorkTier
    role: SelectionRole
    provider: str
    model_id: str
    reasoning_level: str | None
    reasoning_effective: str | None
    reviewed_flex_mode: bool
    effective_flex_mode: bool
    field_sources: Mapping[str, SelectionSource]
    document_path: str
    document_revision: str
    selection_fingerprint: str

    def to_dict(self) -> dict[str, object]:
        return contract_projection(self)


@dataclass(frozen=True)
class SelectionIssue:
    """Safe failure to construct one role selection.

    ``message`` must come from the fixed operator-safe reason vocabulary; raw
    parser exceptions and provider payloads have no place in this contract.
    """

    work_id: str
    tier: WorkTier
    role: SelectionRole
    reason_code: ReasonCode
    message: str
    provider: str | None = None
    model_id: str | None = None
    reasoning_level: str | None = None
    reviewed_flex_mode: bool | None = None
    field_sources: Mapping[str, SelectionSource] | None = None
    document_path: str | None = None
    document_revision: str | None = None

    def to_dict(self) -> dict[str, object]:
        return contract_projection(self)


@dataclass(frozen=True)
class EffectiveSelectionBatch:
    """Ordered effective selections (or safe issues) for one work item."""

    work_id: str
    tier: WorkTier
    roles: tuple[SelectionOrIssue, ...]
    selection_fingerprint: str

    @property
    def complete(self) -> bool:
        return all(isinstance(item, EffectiveSelection) for item in self.roles)

    @property
    def selections(self) -> tuple[EffectiveSelection, ...]:
        return tuple(item for item in self.roles if isinstance(item, EffectiveSelection))

    @property
    def issues(self) -> tuple[SelectionIssue, ...]:
        return tuple(item for item in self.roles if isinstance(item, SelectionIssue))

    def to_dict(self) -> dict[str, object]:
        return contract_projection(self)


@dataclass(frozen=True)
class ModelCapabilityEvidence:
    """Verified per-model capability data; ``None`` means unknown evidence."""

    model_id: str
    reasoning_levels: tuple[str, ...] | None = None
    default_reasoning_level: str | None = None
    supports_flex_mode: bool | None = None

    def to_dict(self) -> dict[str, object]:
        return contract_projection(self)


@dataclass(frozen=True)
class CapabilityEvidence:
    """Normalized, credential-free observations supplied to the evaluator.

    A ``None`` catalog is unknown; an empty tuple is a verified empty catalog.
    Compatibility and Flex values use ``None`` for unknown, preserving the
    distinction between missing evidence and explicit rejection.
    """

    provider: str
    provider_availability: ProviderAvailability
    discovery_failure_kind: DiscoveryFailureKind | None
    verified_model_catalog: tuple[ModelCapabilityEvidence, ...] | None
    provider_supports_flex_mode: bool | None
    cli_compatible: bool | None
    sdk_compatible: bool | None
    required_tool_host_compatible: bool | None
    adapter_supported: bool | None = None
    unknown_evidence: tuple[UnknownEvidenceKind, ...] = ()
    setup_evidence_available: bool = False

    def to_dict(self) -> dict[str, object]:
        return contract_projection(self)


SelectionOrIssue: TypeAlias = EffectiveSelection | SelectionIssue
ContractDeclaration: TypeAlias = (
    EffectiveSelection
    | EffectiveSelectionBatch
    | SelectionIssue
    | SelectionSource
    | ModelCapabilityEvidence
    | CapabilityEvidence
)


REASON_CLASSIFICATIONS: Mapping[ReasonCode, ReasonClassification | None] = {
    "missing_configuration": "deterministic",
    "malformed_configuration": "deterministic",
    "invalid_model": "deterministic",
    "invalid_tier": "deterministic",
    "unsupported_adapter": "deterministic",
    "provider_not_installed": "transient",
    "provider_not_authenticated": "transient",
    "discovery_unavailable": "transient",
    "discovery_empty": "transient",
    "provider_unavailable": "transient",
    "provider_temporarily_unavailable": "transient",
    "capability_unknown": "transient",
    "model_not_offered": "deterministic",
    "reasoning_not_supported": "deterministic",
    "flex_mode_not_supported": "deterministic",
    "cli_incompatible": "deterministic",
    "sdk_incompatible": "deterministic",
    "tool_host_incompatible": "deterministic",
    "stale_selection": "deterministic",
    "available": None,
}

REASON_REMEDIES: Mapping[ReasonCode, tuple[Remedy, ...]] = {
    "missing_configuration": ("migrate_or_default", "choose_configuration"),
    "malformed_configuration": ("migrate_or_default", "choose_configuration"),
    "invalid_model": ("migrate_or_default", "choose_configuration"),
    "invalid_tier": ("migrate_or_default", "choose_configuration"),
    "unsupported_adapter": ("choose_configuration",),
    "provider_not_installed": ("open_provider_setup", "refresh_and_retry"),
    "provider_not_authenticated": ("open_provider_setup", "refresh_and_retry"),
    "discovery_unavailable": ("refresh_and_retry",),
    "discovery_empty": ("refresh_and_retry",),
    "provider_unavailable": ("refresh_and_retry",),
    "provider_temporarily_unavailable": ("refresh_and_retry",),
    "capability_unknown": ("refresh_and_retry",),
    "model_not_offered": ("choose_configuration",),
    "reasoning_not_supported": ("choose_configuration",),
    "flex_mode_not_supported": ("choose_configuration",),
    "cli_incompatible": ("open_provider_setup",),
    "sdk_incompatible": ("open_provider_setup",),
    "tool_host_incompatible": ("open_provider_setup",),
    "stale_selection": ("refresh_and_retry",),
    "available": (),
}

REASON_MESSAGES: Mapping[ReasonCode, str] = {
    "missing_configuration": "Agent configuration is missing",
    "malformed_configuration": "Agent configuration is malformed",
    "invalid_model": "The selected model is invalid",
    "invalid_tier": "The work tier is invalid",
    "unsupported_adapter": "The selected provider adapter is unsupported",
    "provider_not_installed": "The selected provider is not installed",
    "provider_not_authenticated": "The selected provider is not authenticated",
    "discovery_unavailable": "Provider discovery is unavailable",
    "discovery_empty": "Provider discovery returned no models",
    "provider_unavailable": "The selected provider is unavailable",
    "provider_temporarily_unavailable": "The selected provider is temporarily unavailable",
    "capability_unknown": "Required capability evidence is unknown",
    "model_not_offered": "The selected model is not offered",
    "reasoning_not_supported": "The selected reasoning level is not supported",
    "flex_mode_not_supported": "Flex mode is not supported",
    "cli_incompatible": "The provider CLI is incompatible",
    "sdk_incompatible": "The provider SDK is incompatible",
    "tool_host_incompatible": "The required tool host is incompatible",
    "stale_selection": "The reviewed selection is stale",
    "available": "Selected agent configuration is supported",
}

# This remedy is intentionally absent from every role-level mapping.  Task 004
# may add it only after a fresh whole-batch evaluation with Flex disabled.
BATCH_ONLY_REMEDIES: tuple[Remedy, ...] = ("continue_without_flex",)


def role_scope(tier: WorkTier) -> tuple[SelectionRole, ...]:
    """Return the required roles in their canonical diagnostic order."""

    return ROLE_SCOPES[tier]


def remedies_for_reason(
    reason: ReasonCode, *, setup_evidence: bool = False
) -> tuple[Remedy, ...]:
    """Return ordered role remedies, conditionally exposing setup guidance."""

    remedies = REASON_REMEDIES[reason]
    if (
        setup_evidence
        and reason
        in {
            "discovery_unavailable",
            "discovery_empty",
            "provider_unavailable",
            "provider_temporarily_unavailable",
            "capability_unknown",
        }
    ):
        return (*remedies, "open_provider_setup")
    return remedies


def _source_projection(source: SelectionSource) -> dict[str, object]:
    return {
        "kind": source.kind,
        "revision": source.revision,
        "document_path": source.document_path,
        "parent_revision": source.parent_revision,
        "stamping_rule": source.stamping_rule,
    }


def _sources_projection(
    sources: Mapping[str, SelectionSource] | None,
) -> dict[str, object] | None:
    if sources is None:
        return None
    return {name: _source_projection(sources[name]) for name in sorted(sources)}


def contract_projection(value: ContractDeclaration) -> dict[str, object]:
    """Project a declaration to deterministic, JSON-safe, non-secret fields."""

    if isinstance(value, EffectiveSelection):
        return {
            "work_id": value.work_id,
            "tier": value.tier,
            "role": value.role,
            "provider": value.provider,
            "model_id": value.model_id,
            "reasoning_level": value.reasoning_level,
            "reasoning_effective": value.reasoning_effective,
            "reviewed_flex_mode": value.reviewed_flex_mode,
            "effective_flex_mode": value.effective_flex_mode,
            "field_sources": _sources_projection(value.field_sources),
            "document_path": value.document_path,
            "document_revision": value.document_revision,
            "selection_fingerprint": value.selection_fingerprint,
        }
    if isinstance(value, SelectionIssue):
        return {
            "work_id": value.work_id,
            "tier": value.tier,
            "role": value.role,
            "reason_code": value.reason_code,
            "message": value.message,
            "provider": value.provider,
            "model_id": value.model_id,
            "reasoning_level": value.reasoning_level,
            "reviewed_flex_mode": value.reviewed_flex_mode,
            "field_sources": _sources_projection(value.field_sources),
            "document_path": value.document_path,
            "document_revision": value.document_revision,
        }
    if isinstance(value, EffectiveSelectionBatch):
        return {
            "work_id": value.work_id,
            "tier": value.tier,
            "roles": [contract_projection(item) for item in value.roles],
            "selection_fingerprint": value.selection_fingerprint,
            "complete": value.complete,
        }
    if isinstance(value, CapabilityEvidence):
        catalog = value.verified_model_catalog
        return {
            "provider": value.provider,
            "provider_availability": value.provider_availability,
            "discovery_failure_kind": value.discovery_failure_kind,
            "verified_model_catalog": (
                None if catalog is None else [contract_projection(model) for model in catalog]
            ),
            "provider_supports_flex_mode": value.provider_supports_flex_mode,
            "cli_compatible": value.cli_compatible,
            "sdk_compatible": value.sdk_compatible,
            "required_tool_host_compatible": value.required_tool_host_compatible,
            "adapter_supported": value.adapter_supported,
            "unknown_evidence": list(value.unknown_evidence),
            "setup_evidence_available": value.setup_evidence_available,
        }
    if isinstance(value, ModelCapabilityEvidence):
        return {
            "model_id": value.model_id,
            "reasoning_levels": (
                None if value.reasoning_levels is None else list(value.reasoning_levels)
            ),
            "default_reasoning_level": value.default_reasoning_level,
            "supports_flex_mode": value.supports_flex_mode,
        }
    if isinstance(value, SelectionSource):
        return _source_projection(value)
    raise TypeError(f"unsupported contract declaration: {type(value).__name__}")
