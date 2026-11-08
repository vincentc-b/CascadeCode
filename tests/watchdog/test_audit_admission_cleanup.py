"""Interrupted admission must neither leak workers nor spend unstarted repairs."""

import multiprocessing
import threading
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from cascade.board.context import set_project_context
from cascade.task.action_recovery import load_action
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog import audit_recovery, reservations
from cascade.watchdog.reservations import (
    record_interrupted_claim,
    record_result,
    reserve_after_recheck,
)
from cascade.workspace.types import ProjectContext
from tests.watchdog.test_reservations import _descriptor, _fresh, _incident, _root


class _BrokenAcceptSender:
    def send(self, _accepted):
        raise BrokenPipeError

    def close(self):
        pass


def _accept_then_break_pipe(root, reservation):
    audit_recovery._accept_claim_process(
        _BrokenAcceptSender(), root, reservation, None
    )


def test_unaccepted_interruptions_retain_history_and_cooldown_without_spending_repairs(
    tmp_path,
    monkeypatch,
):
    root = _root(tmp_path)
    incident, descriptor = _incident(), _descriptor()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    clock = [now]

    class ClockDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(reservations, "datetime", ClockDateTime)
    interruptions = descriptor.attempt_bound + 1
    for _ in range(interruptions):
        decision = reserve_after_recheck(
            incident,
            descriptor,
            root=root,
            now=now,
            handoff_pending=True,
            fresh_recheck=_fresh(incident),
        )
        assert decision.reservation is not None
        clock[0] = now + timedelta(seconds=1)
        assert record_interrupted_claim(
            decision.reservation.claim_token, ("action_recovery",), root=root
        )
        receipt = load_action(decision.reservation.reservation_id, root=root)[
            "incident"
        ]
        assert (
            reserve_after_recheck(
                incident,
                descriptor,
                root=root,
                now=now + timedelta(seconds=2),
                fresh_recheck=_fresh(incident),
            ).reason
            == "reassessment_cooldown"
        )
        now += timedelta(seconds=62)
    assert len(receipt["attempts"]) == interruptions
    assert all(row["adapter_executed"] is False for row in receipt["attempts"])

    # Accepted repair failures still have exactly the original finite budget.
    for _ in range(descriptor.attempt_bound):
        decision = reserve_after_recheck(
            incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
        )
        assert decision.reservation is not None
        receipt = record_result(
            decision.reservation,
            {"worker": "health-audit-recovery", "accepted": True},
            {"outcome": "error", "reason": "adapter_failed"},
            root=root,
            now=now + timedelta(seconds=1),
        )
        now += timedelta(seconds=62)
    assert len(receipt["attempts"]) == interruptions + descriptor.attempt_bound
    assert [row["attempt"] for row in receipt["attempts"]] == list(range(1, 8))
    assert (
        reserve_after_recheck(
            incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
        ).reason
        == "attempt_bound_exhausted"
    )


@pytest.mark.parametrize(
    "acknowledgement",
    [
        {},
        {"worker": "health-audit-admission", "accepted": True},
        {"worker": "health-audit-recovery", "accepted": False},
        {"worker": "health-audit-admission", "accepted": False},
    ],
)
def test_ambiguous_or_accepted_attempts_are_not_refunded(tmp_path, acknowledgement):
    root = _root(tmp_path)
    incident, descriptor = _incident(), replace(_descriptor(), attempt_bound=1)
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    decision = reserve_after_recheck(
        incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
    )
    record_result(
        decision.reservation,
        acknowledgement,
        {"outcome": "refused", "reason": "admission_handoff_interrupted"},
        root=root,
        now=now + timedelta(seconds=1),
    )
    assert (
        reserve_after_recheck(
            incident,
            descriptor,
            root=root,
            now=now + timedelta(seconds=62),
            fresh_recheck=_fresh(incident),
        ).reason
        == "attempt_bound_exhausted"
    )


def test_live_parent_refunds_accepted_claim_when_accept_ipc_is_lost(tmp_path):
    root = _root(tmp_path)
    incident = _incident()
    descriptor = replace(_descriptor(), attempt_bound=1)
    now = datetime.now(timezone.utc)
    decision = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=now,
        claim_seconds=30,
        handoff_pending=True,
        fresh_recheck=_fresh(incident),
    )
    assert decision.reservation is not None

    context = multiprocessing.get_context("spawn")
    child = context.Process(
        target=_accept_then_break_pipe,
        args=(root, decision.reservation),
    )
    child.start()
    child.join(10)
    assert child.exitcode == 0
    accepted = load_action(decision.reservation.reservation_id, root=root)["incident"]
    assert accepted["attempts"][-1]["adapter_executed"] is True

    # The live parent reaped the accept child and has not called the adapter,
    # so only this private exact-token disposition may refund the attempt.
    audit_recovery._reconcile_interrupted_claim(
        root,
        decision.reservation.claim_token,
        ("action_recovery",),
        accepted_handoff=True,
    )
    receipt = load_action(decision.reservation.reservation_id, root=root)["incident"]
    assert receipt["attempts"][-1]["adapter_executed"] is False

    retry_at = datetime.fromisoformat(receipt["next_reassessment_at"]) + timedelta(
        seconds=1
    )
    retry = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=retry_at,
        fresh_recheck=_fresh(incident),
    )
    assert retry.reservation is not None


def test_blocked_cleanup_leaves_no_waiting_thread_or_child_process(
    tmp_path, monkeypatch
):
    root = _root(tmp_path)
    incident = _incident()
    decision = reserve_after_recheck(
        incident,
        _descriptor(),
        root=root,
        handoff_pending=True,
        fresh_recheck=_fresh(incident),
    )
    before = {child.pid for child in multiprocessing.active_children()}
    monkeypatch.setattr(audit_recovery, "_ADMISSION_RECONCILE_SECONDS", 0.2)
    started = time.monotonic()
    # The real cross-process lock blocks any spawned cleanup that gets to it.
    with task_lifecycle_lock(root=root):
        for _ in range(3):
            audit_recovery._reconcile_interrupted_claim(
                root, decision.reservation.claim_token, ("action_recovery",)
            )
            assert {child.pid for child in multiprocessing.active_children()} == before
            assert not any(
                thread.name == "health-audit-admission-reconcile"
                for thread in threading.enumerate()
            )
    assert time.monotonic() - started < 3
    # Killing cleanup does not mutate or release a claim it could not inspect.
    assert (
        load_action(decision.reservation.reservation_id, root=root)["incident"][
            "outcome"
        ]
        == "claimed"
    )


def test_cleanup_process_restores_split_project_context(tmp_path):
    tracking = _root(tmp_path / "tracking")
    product = tmp_path / "product"
    product.mkdir()
    incident = _incident()
    decision = reserve_after_recheck(
        incident,
        _descriptor(),
        root=tracking,
        handoff_pending=True,
        fresh_recheck=_fresh(incident),
    )
    set_project_context(ProjectContext.split(product, tracking))
    try:
        audit_recovery._reconcile_interrupted_claim(
            product, decision.reservation.claim_token, ("action_recovery",)
        )
        receipt = load_action(decision.reservation.reservation_id, root=tracking)
        assert (
            receipt["incident"]["result"]["reason"] == "admission_handoff_interrupted"
        )
        assert receipt["incident"]["acknowledgement"]["accepted"] is False
        assert not (product / ".cascade/executions.json").exists()
    finally:
        set_project_context(None)
