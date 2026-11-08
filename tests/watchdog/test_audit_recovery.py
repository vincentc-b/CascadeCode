from __future__ import annotations

import multiprocessing
import os
import subprocess
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.context import set_project_context
from cascade.task.action_recovery import (
    ActionRecoveryUnavailable,
    create_or_load_action,
    recovery_actions,
)
from cascade.task.execution import ExecutionStoreUnavailable, execution_views
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog.audit import project_audit_observation
from cascade.watchdog import audit_recovery
from cascade.watchdog.capabilities import (
    CapabilityDescriptor,
    CapabilityRegistry,
    probe_capability,
)
from cascade.watchdog.incidents import incident_record
from cascade.watchdog.reservations import IncidentReservation
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo, run_audit_recovery_entry


def test_spawned_audit_pass_retains_parent_stall_episode(tmp_path: Path) -> None:
    """A fresh observer process must advance, not reset, parent evidence."""

    from cascade.board.store import read_doc, write_doc

    root = make_repo(tmp_path)
    (root / "cascade.toml").write_text(
        '[automation.health_audit]\ninterval = "1m"\n', encoding="utf-8"
    )
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    epic = read_doc("epic_001", root=root)
    epic.meta.plan_approved_at = datetime(2026, 11, 8, tzinfo=timezone.utc)
    write_doc(epic, root=root)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "audit parent"], cwd=root, check=True)

    first = run_audit_recovery_entry(root)
    assert first.incident_work_ids == ()
    proven = project_audit_observation(
        "epic_001", root=root, monotonic=lambda: time.monotonic() + 61
    )

    assert proven.classification == "proven_incident"
    assert proven.reason == "resume_planning_owner"
    assert proven.evidence.parent_action is not None
    assert proven.evidence.parent_action.observation_count == 2


def _hold_admission_handoff(sender, *args) -> None:
    """Reserve normally, then emulate a child stuck before IPC delivery."""

    class _HeldSender:
        def send(self, _message) -> None:
            while True:
                time.sleep(1)

        def close(self) -> None:
            sender.close()

    audit_recovery._admission_process(_HeldSender(), *args)


def _hold_lifecycle_lock(root: Path, ready, release) -> None:
    with task_lifecycle_lock(root=root):
        ready.set()
        release.wait(10)


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


def test_final_claim_acceptance_is_bounded_by_lock_and_fifo(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    reservation = IncidentReservation(
        reservation_id="task_001:health_reservation:test",
        claim_token="test-token",
        work_id="task_001",
        tier="task",
        generation="sha256:" + "0" * 64,
        failure_class="blocked_task_failed",
        capability="feature.retry_task",
        durable_store="action_recovery",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_expires_at="2026-01-01T00:05:00+00:00",
    )
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    holder = context.Process(
        target=_hold_lifecycle_lock,
        args=(root, ready, release),
    )
    holder.start()
    assert ready.wait(5)
    started = time.monotonic()
    try:
        assert not audit_recovery._bounded_accept_claim(
            root,
            reservation,
            deadline=time.monotonic() + 0.5,
            cancel_event=None,
        )
        assert time.monotonic() - started < 1.5
    finally:
        release.set()
        holder.join(5)
        holder.close()

    fifo = root / ".cascade" / "executions.json"
    fifo.parent.mkdir(exist_ok=True)
    os.mkfifo(fifo)
    started = time.monotonic()
    assert not audit_recovery._bounded_accept_claim(
        root,
        reservation,
        deadline=time.monotonic() + 0.5,
        cancel_event=None,
    )
    assert time.monotonic() - started < 1.5


def test_admission_timeout_reaps_git_descendants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    pid_file = tmp_path / "git-helper.pid"
    fake_git = fake_bin / "git"
    fake_git.write_text(
        "#!/usr/bin/env python3\n"
        "import os, signal, time\n"
        "pid = os.fork()\n"
        "if pid == 0:\n"
        "    signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "    with open(os.environ['AUDIT_HELPER_PID'], 'w') as handle:\n"
        "        handle.write(str(os.getpid()))\n"
        "    while True: time.sleep(1)\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "while True: time.sleep(1)\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("AUDIT_HELPER_PID", str(pid_file))
    monkeypatch.setenv("PATH", f"{fake_bin}{os.pathsep}{os.environ['PATH']}")

    started = time.monotonic()
    assert not audit_recovery.dispatch_audit_recovery(
        root, "task_001", timeout_seconds=5
    )
    assert time.monotonic() - started < 6.5
    helper_pid = int(pid_file.read_text(encoding="utf-8"))
    deadline = time.monotonic() + 1
    status = Path(f"/proc/{helper_pid}/status")
    while status.exists() and time.monotonic() < deadline:
        if "State:\tZ" in status.read_text(encoding="utf-8"):
            break
        time.sleep(0.01)
    assert not status.exists() or "State:\tZ" in status.read_text(encoding="utf-8")


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


def test_delivery_recovery_passes_pinned_feature_identity_without_model_turn(
    tmp_path: Path, monkeypatch
) -> None:
    received: list[dict[str, object]] = []
    model_started = threading.Event()

    def execute(task_id: str, **kwargs: object) -> dict[str, object]:
        received.append({"task_id": task_id, **kwargs})
        return {"ok": True}

    descriptor = CapabilityDescriptor(
        name="task.supervisor_recover_task_delivery",
        operation="supervisor_recover_task_delivery",
        executor=execute,
        tiers=frozenset({"task"}),
        failure_classes=frozenset({"validated_delivery_missing"}),
        owner_kinds=frozenset({"feature_team"}),
        required_evidence=(),
        durable_store="orphan_delivery",
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
        failure_class="validated_delivery_missing",
        capability=descriptor.name,
        durable_store="orphan_delivery",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_expires_at="2026-01-01T00:05:00+00:00",
    )
    contract = {
        "accountable_owner": "feature_team:feat_001",
        "evidence": {"parent_id": "feat_001"},
    }
    monkeypatch.setattr(audit_recovery, "record_result", lambda *_a, **_k: {})
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_turn",
        lambda *_a, **_k: model_started.set(),
    )

    audit_recovery._execute_reservation(
        reservation, descriptor, contract, root=tmp_path
    )

    assert received == [
        {
            "task_id": "task_001",
            "root": tmp_path,
            "observed_incident": "reservation",
            "feature_id": "feat_001",
        }
    ]
    assert not model_started.is_set()


@pytest.mark.parametrize(
    ("descriptor_name", "tier", "owner", "evidence", "expected"),
    (
        (
            "feature.restore_child_dispatch",
            "feature",
            "feature_team:feat_001",
            {"child_id": "task_001"},
            {
                "args": ("task_001",),
                "feature_id": "feat_001",
                "generation": "sha256:" + "2" * 64,
            },
        ),
        (
            "epic.resume_planning_owner",
            "epic",
            "epic_team:epic_001",
            {},
            {
                "args": ("reservation",),
                "epic_id": "epic_001",
                "expected_generation": "sha256:" + "2" * 64,
            },
        ),
    ),
)
def test_parent_executor_preserves_generation_and_original_action_identity(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    descriptor_name: str,
    tier: str,
    owner: str,
    evidence: dict[str, object],
    expected: dict[str, object],
) -> None:
    received: list[dict[str, object]] = []
    recorded: list[dict[str, object]] = []

    def execute(*args: object, **kwargs: object) -> dict[str, object]:
        received.append({"args": args, **kwargs})
        return {"ok": True, "durable_result": False, "outcome": "pending"}

    descriptor = CapabilityDescriptor(
        name=descriptor_name,
        operation=(
            "restore_child_dispatch"
            if descriptor_name.endswith("restore_child_dispatch")
            else "resume_planning_owner"
        ),
        executor=execute,
        tiers=frozenset({tier}),
        failure_classes=frozenset({"parent_stalled"}),
        owner_kinds=frozenset({owner.partition(":")[0]}),
        required_evidence=(),
        durable_store="action_recovery",
        attempt_bound=2,
        lock_protocol="lifecycle lock",
        recheck_protocol="fresh generation",
        resume_action="retry exact action",
    )
    reservation = IncidentReservation(
        reservation_id="reservation",
        claim_token="token",
        work_id=owner.partition(":")[2],
        tier=tier,
        generation="sha256:" + "2" * 64,
        failure_class="parent_stalled",
        capability=descriptor_name,
        durable_store="action_recovery",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_expires_at="2026-01-01T00:05:00+00:00",
    )

    def capture(_reservation, acknowledgement, result, **_kwargs):
        recorded.append(
            {"acknowledgement": acknowledgement, "result": dict(result)}
        )
        return dict(result)

    monkeypatch.setattr(audit_recovery, "record_result", capture)
    audit_recovery._execute_reservation(
        reservation,
        descriptor,
        {"accountable_owner": owner, "evidence": evidence},
        root=tmp_path,
    )

    assert received == [{**expected, "root": tmp_path}]
    assert recorded[0]["result"]["outcome"] == "deferred"


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
    executions: list[str] = []

    def execute(received_action_id: str, **_kwargs):
        assert received_action_id == action_id
        executions.append(received_action_id)
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
    missing = CapabilityDescriptor(
        name="task.missing_adapter",
        operation="missing_adapter",
        executor=None,
        tiers=frozenset({"task"}),
        failure_classes=frozenset({"blocked_task_failed"}),
        owner_kinds=frozenset({"feature_team"}),
        required_evidence=(),
        durable_store="action_recovery",
        attempt_bound=1,
        lock_protocol="task_lifecycle_lock",
        recheck_protocol="fresh_generation",
        resume_action="install adapter",
    )

    unavailable = replace(descriptor, executor=None)
    first = run_audit_recovery_entry(
        root, registry=CapabilityRegistry((unavailable, missing))
    )
    assert first.incident_work_ids == ("feat_001",)
    assert executions == []
    missing_receipt = next(
        row
        for row in recovery_actions(root=root)
        if row.get("action_kind") == "health_auditor_capability_probe"
        and row.get("metadata", {}).get("responsible_work_id") == "feat_001"
    )
    assert missing_receipt["metadata"]["original_action_identity"] == (
        "retry_integration_branch_update"
    )
    assert missing_receipt["metadata"]["resume_action"] == "retry action"

    second = run_audit_recovery_entry(
        root, registry=CapabilityRegistry((descriptor, missing))
    )
    assert second.incident_work_ids == ("feat_001",)
    assert executions == [action_id]
    run_audit_recovery_entry(
        root, registry=CapabilityRegistry((descriptor, missing))
    )
    assert executions == [action_id]


def test_admission_timeout_reconciles_split_tracking_claim_without_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    set_project_context(ProjectContext.split(root, tracking))
    add_doc(
        tracking,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        tracking,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    subprocess.run(["git", "add", "-A"], cwd=tracking, check=True)
    subprocess.run(["git", "commit", "-m", "snapshot"], cwd=tracking, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "product"], cwd=root, check=True
    )
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

    descriptor = CapabilityDescriptor(
        name="feature.retry_integration_branch_update",
        operation="retry_integration_branch_update",
        executor=lambda *_args, **_kwargs: executed.set(),
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
    monkeypatch.setattr(audit_recovery, "_admission_process", _hold_admission_handoff)

    started = time.monotonic()
    assert not audit_recovery.dispatch_audit_recovery(
        root,
        "feat_001",
        registry=CapabilityRegistry((descriptor,)),
        timeout_seconds=15,
    )
    assert (
        time.monotonic() - started
        < 15 + audit_recovery._ADMISSION_RECONCILE_SECONDS + 0.75
    )
    assert not executed.is_set()
    # The real spawned cleanup must publish in tracking; an in-process callback
    # assertion cannot prove ownership across this process boundary.
    assert (tracking / ".cascade" / "executions.json").is_file()
    reservation = next(
        row
        for row in recovery_actions(root=tracking)
        if row.get("action_kind") == "health_auditor_reservation"
    )
    assert reservation["incident"]["outcome"] == "refused"
    assert (
        reservation["incident"]["result"]["reason"] == "admission_handoff_interrupted"
    )
    assert reservation["incident"]["attempts"][-1]["adapter_executed"] is False
    assert not (root / ".cascade" / "executions.json").exists()
