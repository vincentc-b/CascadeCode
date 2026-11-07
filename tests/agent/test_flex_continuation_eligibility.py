"""Action-bound, read-only Continue without Flex eligibility."""

from __future__ import annotations

from dataclasses import replace

from cascade.agent.capability_contract import (
    CapabilityEvidence,
    EffectiveSelection,
    EffectiveSelectionBatch,
    ModelCapabilityEvidence,
    SelectionSource,
)
from cascade.agent.discovery.inventory import InventoryFreshness
from cascade.agent.flex_continuation import evaluate_flex_continuation_eligibility
from cascade.agent.flex_continuation_contract import (
    OriginalActionIdentity,
    contract_projection,
)
from cascade.agent.preflight import evaluate_provider_capability_batch
from cascade.provider_recovery_command import (
    continue_without_flex_eligibility_command,
)

FRESH = InventoryFreshness(False, 100.0, 400.0, 300.0, 1.0, False)
SOURCE = SelectionSource("document", "rev-1", "docs/features/feature.md")


def _selection(role: str, *, model: str = "safe") -> EffectiveSelection:
    return EffectiveSelection(
        work_id="feat_1",
        tier="feature",
        role=role,  # type: ignore[arg-type]
        provider="codex",
        model_id=model,
        reasoning_level=None,
        reasoning_effective="medium",
        reviewed_flex_mode=True,
        effective_flex_mode=True,
        field_sources={"model_id": SOURCE},
        document_path="docs/features/feature.md",
        document_revision="rev-1",
        selection_fingerprint="a" * 64,
    )


def _evidence(*, models: tuple[str, ...] = ("safe",)) -> CapabilityEvidence:
    return CapabilityEvidence(
        provider="codex",
        provider_availability="available",
        discovery_failure_kind=None,
        verified_model_catalog=tuple(
            ModelCapabilityEvidence(model, ("medium",), "medium", False)
            for model in models
        ),
        provider_supports_flex_mode=False,
        cli_compatible=True,
        sdk_compatible=True,
        required_tool_host_compatible=True,
        adapter_supported=True,
    )


def _batch(*items: EffectiveSelection):
    selections = EffectiveSelectionBatch("feat_1", "feature", items, "a" * 64)
    return evaluate_provider_capability_batch(
        selections=selections,
        evidence={"codex": _evidence()},
        inventory_freshness=FRESH,
        action="feature_dispatch",
    )


def _identity() -> OriginalActionIdentity:
    return OriginalActionIdentity(
        action_id="attempt-7",
        action_kind="feature_dispatch",
        work_id="feat_1",
        target_tier="feature",
        document_revision="rev-1",
        selection_fingerprint="a" * 64,
    )


def test_same_failed_action_is_eligible_only_after_full_flex_off_pass() -> None:
    roles = (
        _selection("feature_lead"),
        _selection("feature_architect"),
        _selection("swe"),
    )
    failed = _batch(*roles)
    disabled = _batch(*(replace(item, effective_flex_mode=False) for item in roles))

    result = evaluate_flex_continuation_eligibility(
        failed_action=contract_projection(_identity()),
        failed_preflight=failed.to_dict(),
        disabled_preflight=disabled,
    )

    assert result.eligible
    assert result.reason_code == "eligible"
    assert result.action_id == "attempt-7"
    assert result.receipt_id == _identity().receipt_id
    assert "provider_payload" not in repr(result.to_dict())


def test_mixed_failure_stale_inventory_and_current_blocker_fail_closed() -> None:
    roles = (
        _selection("feature_lead"),
        _selection("feature_architect", model="missing"),
        _selection("swe"),
    )
    failed = _batch(*roles)
    disabled = _batch(*(replace(item, effective_flex_mode=False) for item in roles))
    identity = contract_projection(_identity())

    mixed = evaluate_flex_continuation_eligibility(
        failed_action=identity,
        failed_preflight=failed.to_dict(),
        disabled_preflight=disabled,
    )
    assert mixed.reason_code == "mixed_deterministic_failures"

    flex_only = _batch(
        _selection("feature_lead"), _selection("feature_architect"), _selection("swe")
    )
    stale_disabled = replace(
        _batch(
            replace(_selection("feature_lead"), effective_flex_mode=False),
            replace(_selection("feature_architect"), effective_flex_mode=False),
            replace(_selection("swe"), effective_flex_mode=False),
        ),
        inventory_freshness=replace(FRESH, from_cache=True),
    )
    stale = evaluate_flex_continuation_eligibility(
        failed_action=identity,
        failed_preflight=flex_only.to_dict(),
        disabled_preflight=stale_disabled,
    )
    assert stale.reason_code == "inventory_not_fresh"

    changed = evaluate_flex_continuation_eligibility(
        failed_action=identity,
        failed_preflight=flex_only.to_dict(),
        disabled_preflight=replace(stale_disabled, selection_fingerprint="b" * 64),
    )
    assert changed.reason_code == "selection_changed"


def test_command_boundary_rejects_non_human_callers_before_reading_state() -> None:
    for actor in ("agent", "system", "scheduler", "refresh", "automatic_retry"):
        result = continue_without_flex_eligibility_command(
            "feat_1",
            actor=actor,  # type: ignore[arg-type]
        )
        assert not result.eligible
        assert result.reason_code == "unauthorized"
