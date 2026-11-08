from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

import pytest

from cascade.task.action_recovery import (
    ActionRecoveryUnavailable,
    create_or_load_action,
    recovery_actions,
)
from cascade.task.execution import ExecutionStoreUnavailable, execution_views
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog import audit_recovery
from cascade.watchdog.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    probe_capability,
)
from cascade.watchdog.incidents import incident_record
from cascade.watchdog.reservations import IncidentReservation
from tests.support import add_doc, make_repo


def test_non_regular_lifecycle_store_cannot_starve_recovery_worker(
    tmp_path: Path, monkeypatch
) -> None:
    cascade_dir = tmp_path / ".cascade"
    cascade_dir.mkdir()
    fifo = cascade_dir / "executions.json"
    os.mkfifo(fifo)
    processed = threading.Event()
    errors: list[BaseException] = []

    with pytest.raises(ExecutionStoreUnavailable):
        execution_views({"task_001"}, root=tmp_path)
    with pytest.raises(ActionRecoveryUnavailable):
        recovery_actions(root=tmp_path)

    def dispatch(_root: Path, work_id: str, **_kwargs) -> bool:
        # Exercise both lifecycle readers on the first queued item. A FIFO
        # used to block here forever and starve the second item and shutdown.
        if work_id == "task_001":
            try:
                execution_views({work_id}, root=tmp_path)
            except ExecutionStoreUnavailable:
                pass
            except BaseException as exc:
                errors.append(exc)
        else:
            processed.set()
        return False

    monkeypatch.setattr(audit_recovery, "dispatch_audit_recovery", dispatch)
    worker = audit_recovery.AuditRecoveryWorker(tmp_path)
    worker.submit(("task_001", "task_002"))
    assert processed.wait(1)
    worker.stop(timeout=0.2)
    assert not worker._thread.is_alive()
    assert errors == []


def test_dispatch_admission_is_bounded_by_fifo_and_lifecycle_lock(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )
    comments = root / "docs" / "_comments"
    comments.mkdir(exist_ok=True)
    fifo = comments / "task_001.jsonl"
    os.mkfifo(fifo)

    started = time.monotonic()
    assert not audit_recovery.dispatch_audit_recovery(
        root, "task_001", timeout_seconds=0.5
    )
    assert time.monotonic() - started < 1.5

    fifo.unlink()
    lock_entered = threading.Event()
    release_lock = threading.Event()

    def hold_lock() -> None:
        with task_lifecycle_lock(root=root):
            lock_entered.set()
            assert release_lock.wait(2)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert lock_entered.wait(1)
    started = time.monotonic()
    try:
        assert not audit_recovery.dispatch_audit_recovery(
            root, "task_001", timeout_seconds=0.5
        )
        assert time.monotonic() - started < 1.5
    finally:
        release_lock.set()
        holder.join(1)


def test_probe_refuses_nonregular_authority_without_replacing_it(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="blocked",
        parent="feat_001",
    )
    descriptor = CapabilityDescriptor(
        name="feature.retry_task",
        operation="retry_task",
        executor=lambda *_a, **_k: None,
        tiers=frozenset({"task"}),
        failure_classes=frozenset({"blocked_task_failed"}),
        owner_kinds=frozenset({"feature_team"}),
        required_evidence=("document_revision",),
        durable_store="action_recovery",
        attempt_bound=2,
        lock_protocol="task_lifecycle_lock",
        recheck_protocol="fresh_generation",
        resume_action="Retry after restoring the canonical ledger.",
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="blocked_task_failed",
        generation="sha256:" + "1" * 64,
        evidence={"document_revision": "revision-1"},
        selected_capability="retry_task",
        outcome="deferred",
    )
    sidecars = root / ".cascade"
    sidecars.mkdir(exist_ok=True)
    fifo = sidecars / "executions.json"
    os.mkfifo(fifo)

    probe = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=CapabilityRegistry((descriptor,)),
        persist=True,
    )

    assert probe.state == "missing"
    assert probe.reason == "durable_store_unavailable"
    assert fifo.is_fifo()


def test_recovery_executor_defers_model_kickoff_and_returns_promptly(
    tmp_path: Path, monkeypatch
) -> None:
    from cascade.workspace import kickoff
    from cascade.workspace.types import KickoffReason

    model_entered = threading.Event()
    release_model = threading.Event()
    second_adapter = threading.Event()

    def held_model(_reason, _root) -> None:
        model_entered.set()
        assert release_model.wait(2)

    monkeypatch.setattr(kickoff, "_run_kickoff", held_model)

    def first_adapter(*_args, **_kwargs):
        kickoff.kickoff_turn(
            KickoffReason("queue_event", "task_001", "watchdog", tmp_path)
        )
        return {"ok": True}

    def next_adapter(*_args, **_kwargs):
        second_adapter.set()
        return {"ok": True}

    def descriptor(executor) -> CapabilityDescriptor:
        return CapabilityDescriptor(
            name="feature.retry_task",
            operation="retry_task",
            executor=executor,
            tiers=frozenset({"task"}),
            failure_classes=frozenset({"blocked_task_failed"}),
            owner_kinds=frozenset({"feature_team"}),
            required_evidence=(),
            durable_store="action_recovery",
            attempt_bound=2,
            lock_protocol="task_lifecycle_lock",
            recheck_protocol="fresh_generation",
            resume_action="retry",
        )

    reservation = IncidentReservation(
        reservation_id="reservation",
        claim_token="token",
        work_id="task_001",
        tier="task",
        generation="generation",
        failure_class="blocked_task_failed",
        capability="feature.retry_task",
        durable_store="action_recovery",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_expires_at="2026-01-01T00:05:00+00:00",
    )
    contract = {"accountable_owner": "feature_team:feat_001", "evidence": {}}
    monkeypatch.setattr(audit_recovery, "record_result", lambda *_a, **_k: {})

    started = time.monotonic()
    audit_recovery._execute_reservation(
        reservation, descriptor(first_adapter), contract, root=tmp_path
    )
    assert time.monotonic() - started < 0.2
    assert model_entered.wait(1)
    audit_recovery._execute_reservation(
        reservation, descriptor(next_adapter), contract, root=tmp_path
    )
    assert second_adapter.wait(0.1)
    release_model.set()
    assert kickoff.wait_for_background_kickoffs(2)


def test_integration_action_keeps_authoritative_class_through_reservation(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "snapshot"], cwd=root, check=True)
    action_id = "feat_001:integration_branch_update"
    create_or_load_action(
        action_id,
        "integration_branch_update",
        root=root,
        attempt_bound=2,
        recovery_state="retryable",
        failure_classification="transient_retry",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "feat_001"},
    )
    executed = threading.Event()

    def execute(received_action_id: str, **_kwargs):
        assert received_action_id == action_id
        executed.set()
        return {"ok": True}

    descriptor = CapabilityDescriptor(
        name="feature.retry_integration_branch_update",
        operation="retry_integration_branch_update",
        executor=execute,
        tiers=frozenset({"feature"}),
        failure_classes=frozenset({"integration_branch_update"}),
        owner_kinds=frozenset({"feature_team"}),
        required_evidence=("action_id",),
        durable_store="action_recovery",
        attempt_bound=2,
        lock_protocol="task_lifecycle_lock",
        recheck_protocol="fresh_generation",
        resume_action="retry action",
        action_kind="integration_branch_update",
        requires_action=True,
    )

    assert audit_recovery.dispatch_audit_recovery(
        root,
        "feat_001",
        registry=CapabilityRegistry((descriptor,)),
    )
    assert executed.is_set()
