"""Shared selection resolution and capability evaluation for application boundaries."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

from cascade.agent.capability_contract import (
    EffectiveSelection,
    EffectiveSelectionBatch,
    REASON_MESSAGES,
    SelectionIssue,
)
from cascade.agent.discovery.evidence import capability_evidence_from_inventory
from cascade.agent.discovery.compatibility import probe_provider_compatibility
from cascade.agent.discovery.inventory import (
    ProviderInventoryResult,
    project_inventory_freshness,
)
from cascade.agent.preflight import (
    ProviderCapabilityBatchPreflight,
    evaluate_provider_capability_batch,
)
from cascade.board.types import WorkDoc, WorkMeta
from cascade.watchdog.model_resolve import resolve_effective_selections


@dataclass(frozen=True)
class RuntimeSelection:
    """Non-secret launch arguments checked against a reviewed selection."""

    role: str
    provider: str
    model_id: str
    reasoning_level: str | None = None
    flex_mode: bool | None = None


@dataclass(frozen=True)
class SelectionPreflight:
    """The exact reviewed selection and its pure capability result."""

    selections: EffectiveSelectionBatch
    result: ProviderCapabilityBatchPreflight


def evaluate_work_selection(
    doc: WorkDoc | WorkMeta,
    *,
    root: Path,
    inventory: ProviderInventoryResult,
    action: str,
    runtime_selections: Iterable[RuntimeSelection] = (),
) -> SelectionPreflight:
    """Resolve once and feed the shared result contract at every boundary.

    Compatibility is observed separately from model discovery. Providers with
    failed discovery are rejected before compatibility evidence is consulted.
    """

    reasoning_defaults = {
        (item.provider_id, model.id): model.reasoning.default_level
        for item in inventory.providers
        for model in item.models
        if model.reasoning is not None
    }
    selections = resolve_effective_selections(
        doc,
        root=Path(root).resolve(),
        provider_reasoning_defaults=reasoning_defaults,
    )
    expected = {item.role: item for item in runtime_selections}
    if expected:
        selections = _mark_runtime_drift(selections, expected)

    providers = {
        item.provider
        for item in selections.roles
        if item.provider is not None
    }
    evidence = {
        provider: capability_evidence_from_inventory(
            provider,
            inventory,
            compatibility=(
                probe_provider_compatibility(provider)
                if any(item.provider_id == provider for item in inventory.providers)
                else None
            ),
        )
        for provider in providers
    }
    result = evaluate_provider_capability_batch(
        selections=selections,
        evidence=evidence,
        inventory_freshness=project_inventory_freshness(inventory.freshness),
        action=action,
    )
    return SelectionPreflight(selections, result)


def _mark_runtime_drift(
    selections: EffectiveSelectionBatch,
    expected: dict[str, RuntimeSelection],
) -> EffectiveSelectionBatch:
    roles = []
    for item in selections.roles:
        runtime = expected.get(item.role)
        if not isinstance(item, EffectiveSelection) or runtime is None:
            roles.append(item)
            continue
        matches = (
            runtime.provider == item.provider
            and runtime.model_id == item.model_id
            and runtime.reasoning_level == item.reasoning_level
            and bool(runtime.flex_mode) == item.effective_flex_mode
        )
        if matches:
            roles.append(item)
            continue
        roles.append(
            SelectionIssue(
                work_id=item.work_id,
                tier=item.tier,
                role=item.role,
                reason_code="stale_selection",
                message=REASON_MESSAGES["stale_selection"],
                provider=item.provider,
                model_id=item.model_id,
                reasoning_level=item.reasoning_level,
                reasoning_effective=item.reasoning_effective,
                reviewed_flex_mode=item.reviewed_flex_mode,
                effective_flex_mode=item.effective_flex_mode,
                field_sources=item.field_sources,
                document_path=item.document_path,
                document_revision=item.document_revision,
            )
        )
    return replace(selections, roles=tuple(roles))
