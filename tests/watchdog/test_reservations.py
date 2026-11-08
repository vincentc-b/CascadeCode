"""Locked fresh-recheck and crash-safe reservation contracts."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.task.action_recovery import load_action
from cascade.watchdog.capabilities import CapabilityDescriptor
from cascade.watchdog.incidents import authoritative_generation, incident_record
from cascade.watchdog.reservations import (
    ReservationConflict,
    record_result,
    reserve_after_recheck,
)
from tests.support import add_doc, make_repo


def _real_stale_task(tmp_path):
    from tests.watchdog.test_audit import _commit
    from cascade.task.execution import mark_queued, mark_running
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001", children=["task_001"])
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    _commit(root)
    old = datetime.now(timezone.utc) - timedelta(hours=1)
    mark_queued("task_001", root=root, now=old)
    mark_running("task_001", root=root, now=old)
    return root


def _observed_incident(observation, operation):
    return incident_record(
        work_id=observation.work_id.value, tier=observation.tier,
        accountable_owner="feature_team:feat_001",
        failure_class=observation.incident.failure_class,
        generation=observation.generation.value,
        evidence={"document_revision": observation.document_revision.value},
        selected_capability=operation, outcome="deferred",
    )


def test_real_observation_probe_and_reservation_survive_elapsed_heartbeat_age(tmp_path, monkeypatch):
    from cascade.watchdog.audit import project_audit_observation
    from cascade.watchdog.capabilities import default_capability_registry, probe_capability
    import cascade.watchdog.reservations as reservations
    root = _real_stale_task(tmp_path)
    observed = project_audit_observation("task_001", root=root)
    assert observed.reason == "stale"
    assert observed.incident.failure_class == "stalled_execution"
    capability = next(row for row in default_capability_registry().descriptors() if row.name == "task.supervisor_recover_task_delivery")
    incident = _observed_incident(observed, capability.name)
    assert probe_capability(incident, "feature_team:feat_001", root=root).available
    # Any Git invocation inside the locked recheck violates admission's contract.
    original_recheck = reservations._locked_local_recheck
    def recheck(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Git or subprocess inside lifecycle lock"))
            return original_recheck(*args, **kwargs)
    monkeypatch.setattr(reservations, "_locked_local_recheck", recheck)
    decision = reserve_after_recheck(incident, capability, root=root)
    assert decision.reserved, decision
    assert reserve_after_recheck(incident, capability, root=root).reason == "active_claim"


def test_locked_recheck_refuses_changed_child_authority(tmp_path, monkeypatch):
    from contextlib import contextmanager
    from dataclasses import replace
    from cascade.board.store import read_doc
    from cascade.watchdog.audit import project_audit_observation
    import cascade.watchdog.reservations as reservations
    root = _real_stale_task(tmp_path)
    from cascade.board.store import write_doc
    from cascade.task.execution import mark_terminal
    mark_terminal("task_001", "failed", root=root)
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=root)
    observed = project_audit_observation("feat_001", root=root)
    assert observed.classification == "proven_incident"
    capability = replace(_descriptor(), tiers=frozenset({"feature"}),
                         failure_classes=frozenset({observed.incident.failure_class}))
    incident = _observed_incident(observed, capability.name)
    child = read_doc("task_001", root=root).meta.path
    original_lock = reservations.task_lifecycle_lock
    @contextmanager
    def race(*, root):
        # A canonical plan change lands after projection, before lock admission.
        child.write_text(child.read_text() + "\nNew owner constraint.\n")
        with original_lock(root=root):
            yield
    monkeypatch.setattr(reservations, "task_lifecycle_lock", race)
    decision = reserve_after_recheck(incident, capability, root=root)
    assert decision.state == "stale"


def _root(tmp_path: Path) -> Path:
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
    return root


def _descriptor(*, store: str = "action_recovery") -> CapabilityDescriptor:
    return CapabilityDescriptor(
        name="feature.retry_task",
        operation="retry_task",
        executor=lambda: None,
        tiers=frozenset({"task"}),
        failure_classes=frozenset({"blocked_task_failed"}),
        owner_kinds=frozenset({"feature_team"}),
        required_evidence=("document_revision",),
        durable_store=store,  # type: ignore[arg-type]
        attempt_bound=3,
        lock_protocol="owning lifecycle lock",
        recheck_protocol="fresh generation",
        resume_action="Retry the probe.",
    )


def _incident(*, parent_rev: str = "f" * 40) -> dict[str, object]:
    evidence = {"document_revision": "d" * 40, "parent_rev": parent_rev}
    generation = authoritative_generation(
        work_id="task_001", tier="task", evidence=evidence, capability="retry_task"
    )
    return incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="blocked_task_failed",
        generation=generation,
        evidence=evidence,
        selected_capability="retry_task",
        outcome="deferred",
    )


def _fresh(incident: dict[str, object], **changes: object):
    row = {
        "work_id": incident["work_id"],
        "tier": incident["tier"],
        "generation": incident["authoritative_generation"],
        "classification": "proven_incident",
        "reason": incident["failure_class"],
        "evidence": {"gates": []},
    }
    row.update(changes)
    return lambda _work_id, _root: row


def test_changed_disappeared_and_gated_incidents_do_not_write(tmp_path: Path) -> None:
    root = _root(tmp_path)
    incident = _incident()
    descriptor = _descriptor()

    changed = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        fresh_recheck=_fresh(incident, generation="sha256:" + "0" * 64),
    )
    gated = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        fresh_recheck=_fresh(incident, classification="expected_wait", reason="approval"),
    )
    disappeared = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        fresh_recheck=lambda _work_id, _root: (_ for _ in ()).throw(FileNotFoundError()),
    )

    assert (changed.state, gated.state, disappeared.state) == ("stale", "gated", "stale")
    assert not (root / ".cascade" / "executions.json").exists()


def test_concurrent_claim_and_manual_recovery_cannot_duplicate_action(tmp_path: Path) -> None:
    root = _root(tmp_path)
    incident = _incident()
    descriptor = _descriptor()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)

    first = reserve_after_recheck(
        incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
    )
    duplicate = reserve_after_recheck(
        incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
    )
    manually_recovered = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=now,
        fresh_recheck=_fresh(incident, classification="healthy", reason="healthy"),
    )

    assert first.reserved and first.reservation is not None
    assert (duplicate.state, duplicate.reason) == ("unavailable", "active_claim")
    assert manually_recovered.state == "stale"
    receipt = load_action(first.reservation.reservation_id, root=root)
    assert receipt is not None
    assert len(receipt["incident"]["attempts"]) == 1


def test_expired_interrupted_claim_replays_and_rejects_late_result(tmp_path: Path) -> None:
    root = _root(tmp_path)
    incident = _incident()
    descriptor = _descriptor(store="orphan_delivery")
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=now,
        claim_seconds=5,
        fresh_recheck=_fresh(incident),
    )
    replay = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=now + timedelta(seconds=6),
        claim_seconds=5,
        fresh_recheck=_fresh(incident),
    )
    assert first.reservation is not None and replay.reservation is not None
    assert first.reservation.claim_token != replay.reservation.claim_token

    with pytest.raises(ReservationConflict, match="superseded"):
        record_result(
            first.reservation,
            {"accepted": True},
            {"outcome": "success"},
            root=root,
            now=now + timedelta(seconds=7),
        )
    final = record_result(
        replay.reservation,
        {"accepted": True},
        {"outcome": "success", "detail": "replayed safely"},
        root=root,
        now=now + timedelta(seconds=7),
    )
    assert final["outcome"] == "success"
    assert record_result(
        replay.reservation,
        {"accepted": True},
        {"outcome": "success"},
        root=root,
    )["result"]["detail"] == "replayed safely"


def test_parent_revision_cannot_substitute_for_typed_feature_identity(tmp_path: Path) -> None:
    root = _root(tmp_path)
    incident = _incident(parent_rev="a" * 40)
    reserved = reserve_after_recheck(
        incident,
        _descriptor(),
        root=root,
        fresh_recheck=_fresh(incident),
    )
    assert reserved.reservation is not None
    assert reserved.reservation.work_id == "task_001"
    assert reserved.reservation.tier == "task"

    malformed = dict(incident)
    malformed["work"] = {"work_id": "feat_001", "tier": "task"}
    with pytest.raises(ValueError, match="identities disagree|not a task ID"):
        reserve_after_recheck(
            malformed,
            _descriptor(),
            root=root,
            fresh_recheck=_fresh(incident),
        )


def test_success_and_finite_attempt_bound_prevent_further_claims(tmp_path: Path) -> None:
    root = _root(tmp_path)
    incident = _incident()
    descriptor = _descriptor()
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = reserve_after_recheck(
        incident, descriptor, root=root, now=now, fresh_recheck=_fresh(incident)
    )
    assert first.reservation is not None
    record_result(
        first.reservation,
        {},
        {"outcome": "success"},
        root=root,
        now=now + timedelta(seconds=1),
    )
    suppressed = reserve_after_recheck(
        incident,
        descriptor,
        root=root,
        now=now + timedelta(days=1),
        fresh_recheck=_fresh(incident),
    )
    assert (suppressed.state, suppressed.reason) == ("unavailable", "terminal_success")
