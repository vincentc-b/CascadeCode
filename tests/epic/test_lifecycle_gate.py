"""Concurrency boundaries for the active-Epic return lifecycle gate."""

from __future__ import annotations

import threading

from cascade.epic.lifecycle_gate import LifecycleGate, LifecycleTurnRejected
from cascade.epic.return_command import return_epic_to_backlog
from cascade.epic.return_eligibility import ReturnEligibilityInput, ReturnGraphMember


def _snapshot(*, status: str = "active") -> ReturnEligibilityInput:
    member = ReturnGraphMember("epic_030", "epic", None, "source", "activation", True, False, True, True)
    return ReturnEligibilityInput(
        epic_id="epic_030", epic_tier="epic", epic_status=status,
        epic_transition_in_progress=False, graph=(member,), graph_complete=True,
        source_brief_revision="brief", lock_order=("epic_030",),
        conflicting_lifecycle_operation=False,
    )


def test_gate_rejects_new_turns_after_quiescence_starts() -> None:
    gate = LifecycleGate()
    with gate.transition("epic_030", ("epic_030",)) as quiesced:
        assert quiesced
        try:
            with gate.turn("epic_030"):
                raise AssertionError("turn should not be admitted")
        except LifecycleTurnRejected:
            pass


def test_gate_rejects_when_an_admitted_turn_does_not_drain() -> None:
    gate = LifecycleGate()
    entered = threading.Event()
    release = threading.Event()

    def active_turn() -> None:
        with gate.turn("epic_030"):
            entered.set()
            release.wait()

    thread = threading.Thread(target=active_turn)
    thread.start()
    assert entered.wait(1)
    with gate.transition("epic_030", ("epic_030",), timeout=0.01) as quiesced:
        assert not quiesced
    release.set()
    thread.join(1)


def test_gate_serializes_transition_attempts_for_an_epic() -> None:
    gate = LifecycleGate()
    first_entered = threading.Event()
    release_first = threading.Event()
    second_entered = threading.Event()

    def first() -> None:
        with gate.transition("epic_030", ("epic_030",)) as quiesced:
            assert quiesced
            first_entered.set()
            release_first.wait()

    def second() -> None:
        with gate.transition("epic_030", ("epic_030",)) as quiesced:
            assert quiesced
            second_entered.set()

    first_thread = threading.Thread(target=first)
    second_thread = threading.Thread(target=second)
    first_thread.start()
    assert first_entered.wait(1)
    second_thread.start()
    assert not second_entered.wait(0.02)
    release_first.set()
    first_thread.join(1)
    second_thread.join(1)
    assert second_entered.is_set()


def test_command_rechecks_eligibility_under_the_lifecycle_lock() -> None:
    snapshots = iter((_snapshot(), _snapshot(status="backlog")))
    calls: list[tuple[str, str]] = []

    result = return_epic_to_backlog(
        "epic_030", "request-1", actor="human", snapshot_loader=lambda _id: next(snapshots),
        transition=lambda *args: calls.append(args), gate=LifecycleGate(),
    )

    assert not result.ok
    assert result.eligibility is not None
    assert result.eligibility.reason_codes == ("epic_not_active",)
    assert calls == []


def test_command_reports_quiescence_timeout_without_transition() -> None:
    gate = LifecycleGate()
    entered = threading.Event()
    release = threading.Event()

    def active_turn() -> None:
        with gate.turn("epic_030"):
            entered.set()
            release.wait()

    thread = threading.Thread(target=active_turn)
    thread.start()
    assert entered.wait(1)
    calls: list[tuple[str, str]] = []
    result = return_epic_to_backlog(
        "epic_030", "request-1", actor="human", snapshot_loader=lambda _id: _snapshot(),
        transition=lambda *args: calls.append(args), gate=gate, quiesce_timeout=0.01,
    )
    release.set()
    thread.join(1)

    assert not result.ok
    assert result.eligibility is not None
    assert result.eligibility.reason_codes == ("turn_not_quiesced",)
    assert calls == []
