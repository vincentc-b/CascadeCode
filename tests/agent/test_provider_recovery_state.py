"""Provider recovery state is durable-safe and has explicit control contracts."""

from __future__ import annotations

from cascade.provider_recovery_state import provider_recovery_state, recovery_actions


def _blocker(*, classification: str = "transient") -> dict[str, object]:
    return {
        "work_id": "task_001",
        "active": True,
        "classification": classification,
        "reason_code": "provider_unavailable",
        "recommended_remedy": "retry_provider_setup",
        "affected_roles": ["swe"],
        "first_attempt": "2026-11-02T00:00:00+00:00",
        "last_attempt": "2026-11-02T00:01:00+00:00",
        "message": "secret provider exception",
    }


def test_serialized_recovery_state_has_safe_reason_and_no_provider_detail() -> None:
    state = provider_recovery_state(
        _blocker(), tier="task", status="active", turn_stoppable=True
    )

    assert state is not None
    assert state["reason_code"] == "provider_unavailable"
    assert state["reason"] == "The selected provider is unavailable. Check provider setup or credentials, then retry."
    assert "secret" not in repr(state)
    assert state["actions"]["retry"] == {"eligible": True}
    assert state["actions"]["provider_setup"] == {"eligible": True}
    assert state["actions"]["return_to_backlog"]["reason_code"] == "not_epic"


def test_non_stoppable_turn_refuses_mutating_recovery_actions() -> None:
    actions = recovery_actions(
        tier="feature", status="active", blocker=_blocker(), turn_stoppable=False
    )

    assert actions["change_provider"]["reason_code"] == "turn_not_stoppable"
    assert actions["retry"]["reason_code"] == "turn_not_stoppable"
    # Setup instructions do not mutate the turn and remain available.
    assert actions["provider_setup"] == {"eligible": True}


def test_active_epic_return_remains_a_distinct_eligibility_contract() -> None:
    actions = recovery_actions(
        tier="epic",
        status="active",
        blocker=_blocker(classification="deterministic"),
        turn_stoppable=True,
        return_to_backlog={"eligible": True},
    )

    assert actions["retry"]["reason_code"] == "selection_change_required"
    assert actions["provider_setup"]["reason_code"] == "provider_setup_not_required"
    assert actions["return_to_backlog"] == {"eligible": True}


def test_clean_and_dirty_tasks_share_non_destructive_recovery_contract() -> None:
    # Git cleanliness is intentionally evaluated only by the separate Epic
    # return contract; provider recovery does not reset or replace a Task tree.
    clean = recovery_actions(tier="task", status="active", blocker=_blocker(), turn_stoppable=True)
    dirty = recovery_actions(tier="task", status="active", blocker=_blocker(), turn_stoppable=True)
    assert clean == dirty


def test_continue_without_flex_is_only_projected_for_a_concrete_action() -> None:
    absent = recovery_actions(
        tier="task", status="active", blocker=_blocker(), turn_stoppable=True
    )
    eligible = recovery_actions(
        tier="task",
        status="active",
        blocker=_blocker(classification="deterministic"),
        turn_stoppable=True,
        continue_without_flex={
            "eligible": True,
            "reason_code": "eligible",
            "action_id": "attempt-7",
        },
    )

    assert "continue_without_flex" not in absent
    assert eligible["continue_without_flex"] == {
        "eligible": True,
        "reason_code": "eligible",
        "action_id": "attempt-7",
    }
