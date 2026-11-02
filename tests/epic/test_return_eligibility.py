"""Contract coverage for the fail-closed Epic return evaluator."""

from __future__ import annotations

from dataclasses import replace

import pytest

from cascade.epic.return_eligibility import (
    ReturnEligibilityInput,
    ReturnEligibilityReasonCode,
    ReturnGraphMember,
    evaluate_return_eligibility,
)


def _member(
    member_id: str,
    tier: str,
    parent_id: str | None,
    **changes: object,
) -> ReturnGraphMember:
    values: dict[str, object] = {
        "id": member_id,
        "tier": tier,
        "parent_id": parent_id,
        "source_revision": f"source-{member_id}",
        "activation_provenance": f"activation-{member_id}",
        "turn_quiesced": True,
        "transition_in_progress": False,
        "history_preservable": True,
        "git_state_preservable": True,
    }
    values.update(changes)
    return ReturnGraphMember(**values)  # type: ignore[arg-type]


def _eligible_input(**changes: object) -> ReturnEligibilityInput:
    members = (
        _member("epic_030", "epic", None),
        _member("feat_030_001", "feature", "epic_030"),
        _member("task_030_001_001", "task", "feat_030_001"),
    )
    values: dict[str, object] = {
        "epic_id": "epic_030",
        "epic_tier": "epic",
        "epic_status": "active",
        "epic_transition_in_progress": False,
        "graph": members,
        "graph_complete": True,
        "source_brief_revision": "brief-sha",
        "lock_order": tuple(sorted(member.id for member in members if member.id)),
        "conflicting_lifecycle_operation": False,
    }
    values.update(changes)
    return ReturnEligibilityInput(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"epic_status": "backlog"}, ReturnEligibilityReasonCode.EPIC_NOT_ACTIVE),
        ({"epic_tier": None}, ReturnEligibilityReasonCode.EPIC_NOT_ACTIVE),
        ({"epic_transition_in_progress": None}, ReturnEligibilityReasonCode.EPIC_TRANSITION_IN_PROGRESS),
        ({"graph": None}, ReturnEligibilityReasonCode.GRAPH_UNAVAILABLE),
        ({"graph_complete": None}, ReturnEligibilityReasonCode.GRAPH_INCOMPLETE),
        ({"source_brief_revision": None}, ReturnEligibilityReasonCode.SOURCE_BRIEF_MISSING),
        ({"lock_order": None}, ReturnEligibilityReasonCode.LIFECYCLE_LOCK_ORDER_UNAVAILABLE),
        ({"conflicting_lifecycle_operation": None}, ReturnEligibilityReasonCode.CONFLICTING_LIFECYCLE_OPERATION),
    ],
)
def test_refuses_each_epic_level_unknown_or_failed_predicate(
    changes: dict[str, object], reason: ReturnEligibilityReasonCode
) -> None:
    result = evaluate_return_eligibility(_eligible_input(**changes))

    assert not result.eligible
    assert reason.value in result.reason_codes


@pytest.mark.parametrize(
    ("member_changes", "reason"),
    [
        ({"id": None}, ReturnEligibilityReasonCode.GRAPH_MEMBER_INVALID),
        ({"parent_id": "missing"}, ReturnEligibilityReasonCode.GRAPH_MEMBER_INVALID),
        ({"source_revision": None}, ReturnEligibilityReasonCode.GRAPH_MEMBER_INVALID),
        ({"turn_quiesced": None}, ReturnEligibilityReasonCode.TURN_NOT_QUIESCED),
        ({"transition_in_progress": None}, ReturnEligibilityReasonCode.MEMBER_TRANSITION_IN_PROGRESS),
        ({"history_preservable": None}, ReturnEligibilityReasonCode.HISTORY_NOT_PRESERVABLE),
        ({"git_state_preservable": None}, ReturnEligibilityReasonCode.GIT_STATE_NOT_PRESERVABLE),
        ({"activation_provenance": None}, ReturnEligibilityReasonCode.ACTIVATION_PROVENANCE_MISSING),
    ],
)
def test_refuses_each_member_predicate_when_unknown(
    member_changes: dict[str, object], reason: ReturnEligibilityReasonCode
) -> None:
    snapshot = _eligible_input()
    changed_member = replace(snapshot.graph[1], **member_changes)  # type: ignore[index,arg-type]
    members = (snapshot.graph[0], changed_member, snapshot.graph[2])  # type: ignore[index]
    result = evaluate_return_eligibility(replace(snapshot, graph=members))

    assert not result.eligible
    assert reason.value in result.reason_codes


def test_reports_every_independent_refusal_in_one_response() -> None:
    result = evaluate_return_eligibility(
        _eligible_input(
            epic_status="completed",
            source_brief_revision=None,
            graph_complete=False,
            conflicting_lifecycle_operation=True,
        )
    )

    assert result.reason_codes == (
        "epic_not_active",
        "conflicting_lifecycle_operation",
        "source_brief_missing",
        "graph_incomplete",
    )


def test_failed_startup_without_substantive_mutation_remains_eligible() -> None:
    """Provider startup failure is evidence, not an eligibility predicate."""

    result = evaluate_return_eligibility(_eligible_input())

    assert result.eligible
    assert result.to_dict()["reason_codes"] == []
