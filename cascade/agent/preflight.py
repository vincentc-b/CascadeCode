"""Pure, safe provider capability evaluation for lifecycle boundaries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal, Mapping

from cascade.agent.capability_contract import (
    CapabilityEvidence,
    EffectiveSelection,
    EffectiveSelectionBatch,
    REASON_CLASSIFICATIONS,
    REASON_MESSAGES,
    ReasonClassification,
    ReasonCode,
    Remedy,
    SelectionIssue,
    SelectionOrIssue,
    contract_projection,
    remedies_for_reason,
)
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)

WorkTier = Literal["epic", "feature", "task"]
PreflightOutcome = Literal["supported", "unsupported", "unavailable"]
PreflightReason = ReasonCode
BatchPreflightOutcome = Literal["supported", "blocked", "transient"]


@dataclass(frozen=True)
class ProviderCapabilityPreflight:
    """Safe result for one role; the first seven fields retain the legacy API."""

    outcome: PreflightOutcome
    reason: PreflightReason
    provider: str | None
    model_id: str | None
    tier: str
    message: str
    retryable: bool
    classification: ReasonClassification | None = None
    remedies: tuple[Remedy, ...] = ()
    work_id: str | None = None
    reasoning_level: str | None = None
    reasoning_effective: str | None = None
    reviewed_flex_mode: bool | None = None
    effective_flex_mode: bool | None = None
    field_sources: Mapping[str, object] | None = None
    document_path: str | None = None
    document_revision: str | None = None
    selection_fingerprint: str | None = None
    capability_scope: Literal["provider", "model"] | None = None
    inventory_freshness: InventoryFreshness | None = None

    @property
    def supported(self) -> bool:
        return self.outcome == "supported"

    @property
    def reason_code(self) -> ReasonCode:
        return self.reason

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "reason": self.reason,
            "reason_code": self.reason,
            "provider": self.provider,
            "model_id": self.model_id,
            "tier": self.tier,
            "message": self.message,
            "retryable": self.retryable,
            "classification": self.classification,
            "remedies": list(self.remedies),
            "work_id": self.work_id,
            "reasoning_level": self.reasoning_level,
            "reasoning_effective": self.reasoning_effective,
            "reviewed_flex_mode": self.reviewed_flex_mode,
            "effective_flex_mode": self.effective_flex_mode,
            "field_sources": _sources_to_dict(self.field_sources),
            "document_path": self.document_path,
            "document_revision": self.document_revision,
            "selection_fingerprint": self.selection_fingerprint,
            "capability_scope": self.capability_scope,
            "inventory_freshness": _freshness_to_dict(self.inventory_freshness),
        }


@dataclass(frozen=True)
class RoleCapabilityPreflight:
    role: str
    result: ProviderCapabilityPreflight

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role, **self.result.to_dict()}


@dataclass(frozen=True)
class ProviderCapabilityBatchPreflight:
    outcome: BatchPreflightOutcome
    checks: tuple[RoleCapabilityPreflight, ...]
    work_id: str | None = None
    action: str | None = None
    selection_fingerprint: str | None = None
    inventory_freshness: InventoryFreshness | None = None
    classification: ReasonClassification | None = None
    reason_code: ReasonCode | None = None
    message: str | None = None
    remedies: tuple[Remedy, ...] = ()

    @property
    def supported(self) -> bool:
        return self.outcome == "supported"

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "supported": self.supported,
            "checks": [check.to_dict() for check in self.checks],
            "work_id": self.work_id,
            "action": self.action,
            "selection_fingerprint": self.selection_fingerprint,
            "inventory_freshness": _freshness_to_dict(self.inventory_freshness),
            "classification": self.classification,
            "reason_code": self.reason_code,
            "message": self.message,
            "remedies": list(self.remedies),
        }


def evaluate_provider_capability_batch(
    *,
    selections: EffectiveSelectionBatch,
    evidence: Mapping[str, CapabilityEvidence],
    inventory_freshness: InventoryFreshness,
    action: str,
) -> ProviderCapabilityBatchPreflight:
    """Evaluate ordered selections/issues using normalized evidence only."""

    checks = tuple(
        RoleCapabilityPreflight(
            item.role, _evaluate(item, evidence, inventory_freshness)
        )
        for item in selections.roles
    )
    batch = batch_provider_capability_preflight(
        checks,
        work_id=selections.work_id,
        action=action,
        selection_fingerprint=selections.selection_fingerprint,
        inventory_freshness=inventory_freshness,
    )
    if _can_disable_flex(selections, evidence, inventory_freshness, checks):
        batch = replace(batch, remedies=(*batch.remedies, "continue_without_flex"))
    return batch


def batch_provider_capability_preflight(
    checks: tuple[RoleCapabilityPreflight, ...],
    *,
    work_id: str | None = None,
    action: str | None = None,
    selection_fingerprint: str | None = None,
    inventory_freshness: InventoryFreshness | None = None,
) -> ProviderCapabilityBatchPreflight:
    """Aggregate all checks; deterministic rejection wins over transience."""

    failed = next((c.result for c in checks if c.result.outcome == "unsupported"), None)
    outcome: BatchPreflightOutcome = "blocked" if failed else "supported"
    if failed is None:
        failed = next(
            (c.result for c in checks if c.result.outcome == "unavailable"), None
        )
        if failed:
            outcome = "transient"
    if failed is None and not checks:
        outcome, reason = "transient", "capability_unknown"
        classification: ReasonClassification | None = "transient"
        message, remedies = REASON_MESSAGES[reason], remedies_for_reason(reason)
    elif failed is None:
        reason, classification = "available", None
        message, remedies = REASON_MESSAGES[reason], ()
    else:
        reason, classification, message = (
            failed.reason,
            failed.classification,
            failed.message,
        )
        remedies = _ordered_remedies(checks)
    return ProviderCapabilityBatchPreflight(
        outcome,
        checks,
        work_id,
        action,
        selection_fingerprint,
        inventory_freshness,
        classification,
        reason,
        message,
        remedies,
    )


def _evaluate(
    selection: SelectionOrIssue,
    by_provider: Mapping[str, CapabilityEvidence],
    freshness: InventoryFreshness,
) -> ProviderCapabilityPreflight:
    if isinstance(selection, SelectionIssue):
        return _result(selection.reason_code, selection, freshness)
    evidence = by_provider.get(selection.provider)
    if evidence is None or evidence.adapter_supported is None:
        return _result("capability_unknown", selection, freshness, evidence)
    if evidence.adapter_supported is False:
        return _result("unsupported_adapter", selection, freshness, evidence)
    if evidence.discovery_failure_kind:
        return _result(evidence.discovery_failure_kind, selection, freshness, evidence)
    if evidence.provider_availability == "unavailable":
        return _result("provider_unavailable", selection, freshness, evidence)
    if evidence.provider_availability != "available":
        return _result("capability_unknown", selection, freshness, evidence)
    catalog = evidence.verified_model_catalog
    if catalog is None:
        return _result("capability_unknown", selection, freshness, evidence)
    if not catalog:
        return _result("discovery_empty", selection, freshness, evidence)
    model = next((m for m in catalog if m.model_id == selection.model_id), None)
    if model is None:
        return _result("model_not_offered", selection, freshness, evidence)
    compatibility: tuple[tuple[bool | None, ReasonCode], ...] = (
        (evidence.cli_compatible, "cli_incompatible"),
        (evidence.sdk_compatible, "sdk_incompatible"),
        (evidence.required_tool_host_compatible, "tool_host_incompatible"),
    )
    for compatible, reason in compatibility:
        if compatible is False:
            return _result(reason, selection, freshness, evidence)
        if compatible is None:
            return _result("capability_unknown", selection, freshness, evidence)
    if selection.reasoning_effective is not None:
        if model.reasoning_levels is None:
            return _result("capability_unknown", selection, freshness, evidence)
        if selection.reasoning_effective not in model.reasoning_levels:
            return _result("reasoning_not_supported", selection, freshness, evidence)
    if selection.effective_flex_mode:
        if evidence.provider_supports_flex_mode is False:
            return _result(
                "flex_mode_not_supported", selection, freshness, evidence, "provider"
            )
        if evidence.provider_supports_flex_mode is None:
            return _result("capability_unknown", selection, freshness, evidence)
        if model.supports_flex_mode is False:
            return _result(
                "flex_mode_not_supported", selection, freshness, evidence, "model"
            )
        if model.supports_flex_mode is None:
            return _result("capability_unknown", selection, freshness, evidence)
    return _result("available", selection, freshness, evidence)


def _result(
    reason: ReasonCode,
    selection: SelectionOrIssue,
    freshness: InventoryFreshness,
    evidence: CapabilityEvidence | None = None,
    scope: Literal["provider", "model"] | None = None,
) -> ProviderCapabilityPreflight:
    classification = REASON_CLASSIFICATIONS[reason]
    outcome: PreflightOutcome = (
        "supported"
        if classification is None
        else "unsupported"
        if classification == "deterministic"
        else "unavailable"
    )
    return ProviderCapabilityPreflight(
        outcome,
        reason,
        selection.provider,
        selection.model_id,
        selection.tier,
        REASON_MESSAGES[reason],
        classification == "transient",
        classification,
        remedies_for_reason(
            reason, setup_evidence=bool(evidence and evidence.setup_evidence_available)
        ),
        selection.work_id,
        selection.reasoning_level,
        selection.reasoning_effective,
        selection.reviewed_flex_mode,
        selection.effective_flex_mode,
        selection.field_sources,
        selection.document_path,
        selection.document_revision,
        selection.selection_fingerprint
        if isinstance(selection, EffectiveSelection)
        else None,
        scope,
        freshness,
    )


def _can_disable_flex(
    selections: EffectiveSelectionBatch,
    evidence: Mapping[str, CapabilityEvidence],
    freshness: InventoryFreshness,
    checks: tuple[RoleCapabilityPreflight, ...],
) -> bool:
    deterministic = [c for c in checks if c.result.classification == "deterministic"]
    if (
        freshness.stale
        or not deterministic
        or any(c.result.reason != "flex_mode_not_supported" for c in deterministic)
    ):
        return False
    disabled = tuple(
        replace(item, effective_flex_mode=False)
        if isinstance(item, EffectiveSelection)
        else item
        for item in selections.roles
    )
    return bool(disabled) and all(
        _evaluate(item, evidence, freshness).supported for item in disabled
    )


def _ordered_remedies(
    checks: tuple[RoleCapabilityPreflight, ...],
) -> tuple[Remedy, ...]:
    return tuple(
        dict.fromkeys(
            r for c in checks if not c.result.supported for r in c.result.remedies
        )
    )


def _sources_to_dict(sources: Mapping[str, object] | None) -> dict[str, object] | None:
    if sources is None:
        return None
    return {
        name: contract_projection(source) if hasattr(source, "kind") else source
        for name, source in sorted(sources.items())
    }


def _freshness_to_dict(value: InventoryFreshness | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "from_cache": value.from_cache,
        "fetched_at": value.fetched_at,
        "expires_at": value.expires_at,
        "ttl_seconds": value.ttl_seconds,
        "age_seconds": value.age_seconds,
        "stale": value.stale,
    }


# Legacy inventory evaluator retained until consumer migration in task 005.
def preflight_provider_capability(
    *,
    provider: str,
    model_id: str,
    tier: WorkTier | str,
    inventory: ProviderInventoryResult,
    reasoning_level: str | None = None,
    flex_mode: bool | None = None,
) -> ProviderCapabilityPreflight:
    model_id = model_id.strip()
    if tier not in ("epic", "feature", "task"):
        return _legacy_failure("invalid_tier", provider, model_id, tier)
    if not model_id:
        return _legacy_failure("invalid_model", provider, model_id, tier)
    item = _provider_item(provider, inventory)
    if item is None:
        failure = next(
            (entry for entry in inventory.failures if entry.provider_id == provider),
            None,
        )
        return ProviderCapabilityPreflight(
            "unavailable",
            "provider_unavailable",
            provider,
            model_id,
            tier,
            failure.message
            if failure and failure.message
            else "Provider is unavailable",
            True,
            "transient",
            ("refresh_and_retry",),
        )
    model = next((m for m in item.models if m.id == model_id), None)
    if model is None:
        return _legacy_failure("model_not_offered", provider, model_id, tier)
    if reasoning_level:
        capability = model.reasoning
        allowed = (
            {capability.default_level, *capability.override_levels}
            if capability is not None and capability.supports_overrides
            else set()
        )
        if reasoning_level not in allowed:
            return _legacy_failure("reasoning_not_supported", provider, model_id, tier)
    if flex_mode and (not item.supports_flex_mode or model.supports_flex_mode is False):
        return _legacy_failure("flex_mode_not_supported", provider, model_id, tier)
    return ProviderCapabilityPreflight(
        "supported",
        "available",
        provider,
        model_id,
        tier,
        REASON_MESSAGES["available"],
        False,
    )


def _provider_item(
    provider: str, inventory: ProviderInventoryResult
) -> ProviderInventoryItem | None:
    return next(
        (item for item in inventory.providers if item.provider_id == provider), None
    )


def _legacy_failure(
    reason: ReasonCode, provider: str, model: str, tier: str
) -> ProviderCapabilityPreflight:
    return ProviderCapabilityPreflight(
        "unsupported",
        reason,
        provider,
        model,
        tier,
        REASON_MESSAGES[reason],
        False,
        "deterministic",
        remedies_for_reason(reason),
    )
