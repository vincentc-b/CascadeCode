"""Focused checks for the shared capability contract declarations."""

from __future__ import annotations

import json

from cascade.agent.capability_contract import (
    CapabilityEvidence,
    EffectiveSelection,
    ModelCapabilityEvidence,
    SELECTION_FINGERPRINT_SCHEMA,
    SelectionIssue,
    SelectionSource,
    contract_projection,
    role_scope,
)


def test_role_order_and_representative_declarations_have_safe_json_projections() -> None:
    assert SELECTION_FINGERPRINT_SCHEMA == "selection-v1"
    assert role_scope("epic") == (
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    assert role_scope("feature") == ("feature_lead", "feature_architect", "swe")
    assert role_scope("task") == ("swe",)

    source = SelectionSource(
        kind="document-role",
        document_path="docs/tasks/2_active/task_037_001_001.md",
        revision="task-rev-7",
    )
    declarations = (
        EffectiveSelection(
            work_id="task_037_001_001",
            tier="task",
            role="swe",
            provider="codex",
            model_id="gpt-safe",
            reasoning_level=None,
            reasoning_effective="medium",
            reviewed_flex_mode=True,
            effective_flex_mode=False,
            field_sources={"provider": source, "model_id": source},
            document_path="docs/tasks/2_active/task_037_001_001.md",
            document_revision="task-rev-7",
            selection_fingerprint="a" * 64,
        ),
        SelectionIssue(
            work_id="task_037_001_001",
            tier="task",
            role="swe",
            reason_code="malformed_configuration",
            message="Agent configuration is malformed",
            provider="codex",
            field_sources={"provider": source},
        ),
        CapabilityEvidence(
            provider="codex",
            provider_availability="available",
            discovery_failure_kind=None,
            verified_model_catalog=(
                ModelCapabilityEvidence(
                    model_id="gpt-safe",
                    reasoning_levels=("low", "medium"),
                    default_reasoning_level="medium",
                    supports_flex_mode=True,
                ),
            ),
            provider_supports_flex_mode=True,
            cli_compatible=True,
            sdk_compatible=None,
            required_tool_host_compatible=True,
            unknown_evidence=("sdk",),
        ),
    )

    projections = [contract_projection(item) for item in declarations]
    encoded = json.dumps(projections, sort_keys=True)

    assert json.loads(encoded) == projections
    assert "credential" not in encoded.lower()
    assert "token" not in encoded.lower()
    assert list(projections[0]["field_sources"]) == ["model_id", "provider"]
