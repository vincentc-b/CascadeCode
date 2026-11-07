"""Failure matrix and serialization checks for the pure batch evaluator."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from cascade.agent.capability_contract import (
    CapabilityEvidence,
    EffectiveSelection,
    EffectiveSelectionBatch,
    ModelCapabilityEvidence,
    REASON_CLASSIFICATIONS,
    REASON_MESSAGES,
    SelectionIssue,
    SelectionSource,
)
from cascade.agent.discovery.inventory import InventoryFreshness
from cascade.agent.preflight import evaluate_provider_capability_batch

FRESH = InventoryFreshness(False, 100.0, 400.0, 300.0, 10.0, False)
SOURCE = SelectionSource("document-role", "rev-1", "docs/tasks/task.md")


def _selection(role: str = "swe", **changes: object) -> EffectiveSelection:
    value = EffectiveSelection(
        work_id="task_1",
        tier="task",
        role=role,
        provider="codex",
        model_id="gpt-safe",
        reasoning_level=None,
        reasoning_effective="medium",
        reviewed_flex_mode=False,
        effective_flex_mode=False,
        field_sources={"model_id": SOURCE},
        document_path="docs/tasks/task.md",
        document_revision="rev-1",
        selection_fingerprint="f" * 64,
    )
    return replace(value, **changes)


def _evidence(**changes: object) -> CapabilityEvidence:
    value = CapabilityEvidence(
        provider="codex",
        provider_availability="available",
        discovery_failure_kind=None,
        verified_model_catalog=(
            ModelCapabilityEvidence("gpt-safe", ("medium",), "medium", True),
        ),
        provider_supports_flex_mode=True,
        cli_compatible=True,
        sdk_compatible=True,
        required_tool_host_compatible=True,
        adapter_supported=True,
    )
    return replace(value, **changes)


def _run(
    item: EffectiveSelection | SelectionIssue,
    evidence: CapabilityEvidence | None = None,
):
    batch = EffectiveSelectionBatch("task_1", "task", (item,), "f" * 64)
    return evaluate_provider_capability_batch(
        selections=batch,
        evidence={} if evidence is None else {"codex": evidence},
        inventory_freshness=FRESH,
        action="dispatch",
    )


@pytest.mark.parametrize(
    ("reason", "evidence"),
    [
        ("unsupported_adapter", _evidence(adapter_supported=False)),
        (
            "provider_not_installed",
            _evidence(
                provider_availability="unavailable",
                discovery_failure_kind="provider_not_installed",
            ),
        ),
        (
            "provider_not_authenticated",
            _evidence(
                provider_availability="unavailable",
                discovery_failure_kind="provider_not_authenticated",
            ),
        ),
        (
            "discovery_unavailable",
            _evidence(
                provider_availability="unknown",
                discovery_failure_kind="discovery_unavailable",
            ),
        ),
        (
            "discovery_empty",
            _evidence(
                verified_model_catalog=(), discovery_failure_kind="discovery_empty"
            ),
        ),
        ("provider_unavailable", _evidence(provider_availability="unavailable")),
        (
            "provider_temporarily_unavailable",
            _evidence(
                provider_availability="unavailable",
                discovery_failure_kind="provider_temporarily_unavailable",
            ),
        ),
        ("capability_unknown", _evidence(verified_model_catalog=None)),
        (
            "model_not_offered",
            _evidence(verified_model_catalog=(ModelCapabilityEvidence("other"),)),
        ),
        ("cli_incompatible", _evidence(cli_compatible=False)),
        ("sdk_incompatible", _evidence(sdk_compatible=False)),
        ("tool_host_incompatible", _evidence(required_tool_host_compatible=False)),
    ],
)
def test_failure_matrix_uses_stable_classification_and_message(
    reason: str, evidence: CapabilityEvidence
) -> None:
    result = _run(_selection(), evidence)
    check = result.checks[0].result

    assert check.reason == reason
    assert check.reason_code == reason
    assert check.classification == REASON_CLASSIFICATIONS[reason]
    assert check.message == REASON_MESSAGES[reason]
    assert result.outcome == (
        "blocked" if check.classification == "deterministic" else "transient"
    )


def test_selection_issues_are_checks_and_deterministic_failure_wins_batch() -> None:
    issue = SelectionIssue(
        "task_1",
        "task",
        "swe",
        "malformed_configuration",
        "unsafe parser detail is ignored",
        provider="codex",
    )
    transient = _run(
        _selection(role="feature_lead"), _evidence(provider_availability="unavailable")
    )
    issue_check = _run(issue).checks[0]
    combined = EffectiveSelectionBatch(
        "task_1", "task", (issue, _selection(role="feature_lead")), "f" * 64
    )
    result = evaluate_provider_capability_batch(
        selections=combined,
        evidence={"codex": _evidence(provider_availability="unavailable")},
        inventory_freshness=FRESH,
        action="preview",
    )

    assert issue_check.result.message == REASON_MESSAGES["malformed_configuration"]
    assert transient.outcome == "transient"
    assert result.outcome == "blocked"
    assert [check.result.reason for check in result.checks] == [
        "malformed_configuration",
        "provider_unavailable",
    ]


def test_reasoning_flex_waiver_and_safe_json_projection() -> None:
    reasoning = _run(_selection(reasoning_effective="high"), _evidence())
    flex = _run(
        _selection(reviewed_flex_mode=True, effective_flex_mode=True),
        _evidence(provider_supports_flex_mode=False),
    )

    assert reasoning.reason_code == "reasoning_not_supported"
    assert flex.checks[0].result.capability_scope == "provider"
    assert flex.remedies == ("choose_configuration", "continue_without_flex")
    projection = flex.to_dict()
    encoded = json.dumps(projection, sort_keys=True, allow_nan=False)
    assert json.loads(encoded) == projection
    assert projection["checks"][0]["reason"] == "flex_mode_not_supported"
    assert projection["checks"][0]["field_sources"]["model_id"]["revision"] == "rev-1"
    assert "unsafe parser detail" not in encoded


def test_missing_evidence_and_empty_scope_cannot_report_support() -> None:
    assert _run(_selection()).reason_code == "capability_unknown"
    empty = EffectiveSelectionBatch("task_1", "task", (), "f" * 64)
    result = evaluate_provider_capability_batch(
        selections=empty, evidence={}, inventory_freshness=FRESH, action="dispatch"
    )
    assert result.outcome == "transient"
    assert result.reason_code == "capability_unknown"
