from cascade.task.orphan_delivery import (
    DeliveryEvidence,
    OrphanDeliveryState,
    PinnedExecutionInputs,
    TaskGitState,
    derive_orphan_delivery_incident,
)


def _state(**changes):
    values = {
        "task_id": "task_001",
        "task_active": True,
        "owner_live": False,
        "execution_phase": "running",
        "checkpoint_present": True,
        "pinned_inputs": PinnedExecutionInputs("codex", "gpt-5"),
        "delivery": DeliveryEvidence(),
        "git": TaskGitState(True, True, True),
    }
    values.update(changes)
    return OrphanDeliveryState(**values)


def test_live_owner_fences_all_recovery_actions():
    incident = derive_orphan_delivery_incident(
        _state(owner_live=True, delivery=DeliveryEvidence("a", "b", True))
    )

    assert (incident.outcome, incident.reason) == ("live_owner", "execution_lease_live")


def test_matching_validated_commit_is_requeued_unless_already_queued():
    evidence = DeliveryEvidence("a", "b", current=True)
    assert derive_orphan_delivery_incident(_state(delivery=evidence)).outcome == "requeue_validated_commit"
    assert derive_orphan_delivery_incident(
        _state(delivery=DeliveryEvidence("a", "b", current=True, queued=True))
    ).outcome == "noop_replay"


def test_resumable_execution_preserves_dirty_worktree():
    incident = derive_orphan_delivery_incident(_state(git=TaskGitState(True, True, True, True)))

    assert incident.outcome == "resume_execution"
    assert incident.state.git.worktree_dirty


def test_missing_or_stale_state_is_refused():
    assert derive_orphan_delivery_incident(_state(checkpoint_present=False)).outcome == "unsafe_or_missing_state"
    assert derive_orphan_delivery_incident(
        _state(delivery=DeliveryEvidence("a", "b", current=False))
    ).reason == "validated_delivery_no_longer_matches_git"
