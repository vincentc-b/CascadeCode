"""Authorization and side-effect boundaries for Epic return requests."""

from __future__ import annotations

from cascade.epic.return_command import return_epic_to_backlog
from cascade.epic.return_eligibility import ReturnEligibilityInput, ReturnGraphMember


def _snapshot(*, quiesced: bool = True) -> ReturnEligibilityInput:
    members = (
        ReturnGraphMember("epic_030", "epic", None, "source", "activation", quiesced, False, True, True),
    )
    return ReturnEligibilityInput(
        epic_id="epic_030",
        epic_tier="epic",
        epic_status="active",
        epic_transition_in_progress=False,
        graph=members,
        graph_complete=True,
        source_brief_revision="brief",
        lock_order=("epic_030",),
        conflicting_lifecycle_operation=False,
    )


def test_non_human_is_denied_before_the_snapshot_or_transition_is_read() -> None:
    calls: list[str] = []

    result = return_epic_to_backlog(
        "epic_030",
        "request-1",
        actor="agent",
        snapshot_loader=lambda _id: calls.append("snapshot") or _snapshot(),
        transition=lambda *_args: calls.append("transition"),
    )

    assert result.error_code == "unauthorized"
    assert calls == []


def test_ineligible_result_is_the_shared_refusal_and_does_not_transition() -> None:
    calls: list[str] = []

    result = return_epic_to_backlog(
        "epic_030",
        "request-1",
        actor="human",
        snapshot_loader=lambda _id: _snapshot(quiesced=False),
        transition=lambda *_args: calls.append("transition"),
    )

    assert result.ok is False
    assert result.eligibility is not None
    assert result.eligibility.reason_codes == ("turn_not_quiesced",)
    assert result.to_dict()["refusals"][0]["code"] == "turn_not_quiesced"
    assert calls == []


def test_eligible_request_needs_the_durable_transition_capability() -> None:
    result = return_epic_to_backlog(
        "epic_030", "request-1", actor="human", snapshot_loader=lambda _id: _snapshot()
    )

    assert result.ok is False
    assert result.error_code == "transition_unavailable"
    assert result.eligibility is not None and result.eligibility.eligible


def test_eligible_request_delegates_once_to_the_transition_capability() -> None:
    calls: list[tuple[str, str]] = []

    result = return_epic_to_backlog(
        "epic_030",
        "request-1",
        actor="human",
        snapshot_loader=lambda _id: _snapshot(),
        transition=lambda epic_id, request_id: calls.append((epic_id, request_id)),
    )

    assert result.ok is True
    assert calls == [("epic_030", "request-1")]
