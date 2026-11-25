from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.watchdog import audit_recovery
from cascade.watchdog import audit
from cascade.watchdog.capabilities import default_capability_registry
from cascade.watchdog.capabilities import CapabilityProbe, CapabilityRegistry
from cascade.watchdog.reservations import IncidentReservation


def test_parent_lifecycle_owner_work_binds_original_task_budget(tmp_path: Path) -> None:
    from cascade.task.action_recovery import create_or_load_action, load_action
    from cascade.task.incident_budget import read_incident_budget

    action_id = "task_001:queued_merge"
    action = create_or_load_action(
        action_id,
        "queued_task_merge",
        root=tmp_path,
        attempt_bound=3,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
    )
    assert (
        audit_recovery._bind_original_incident("task_001", root=tmp_path) == action_id
    )
    assert read_incident_budget(action_id, root=tmp_path) is not None
    assert load_action(action_id, root=tmp_path)["incident_budget_id"] == action_id
    assert action["incident"]["authoritative_generation"] in {
        generation
        for binding in read_incident_budget(action_id, root=tmp_path)["bindings"]
        for generation in binding["generations"]
    }


def test_registry_names_bounded_parent_lifecycle_capability() -> None:
    descriptor = next(
        row
        for row in default_capability_registry().descriptors()
        if row.name == "feature.feature_repair"
    )

    assert descriptor.operation == "feature_repair"
    assert descriptor.tiers == frozenset({"task"})
    assert descriptor.owner_kinds == frozenset({"feature_team"})
    assert descriptor.failure_classes == frozenset({"parent_lifecycle_mismatch"})
    assert descriptor.durable_store == "action_recovery"
    assert descriptor.attempt_bound == 3
    assert descriptor.required_evidence == (
        "document_revision",
        "feature_id",
        "parent_lifecycle_generation",
    )


def test_audit_contract_binds_feature_repair_to_exact_mismatch_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    generation = "sha256:" + "c" * 64
    observation = SimpleNamespace(
        tier="task",
        work_id="task_001",
        generation="sha256:" + "d" * 64,
        identity=SimpleNamespace(
            document_revision="revision",
            git_head="head",
            branch="task/task_001",
        ),
        evidence=SimpleNamespace(
            status="active",
            parent_id="feat_001",
            execution={"phase": "merge_blocked"},
            gates=(),
            unresolved_references=("task_001:queued_merge",),
            local_fingerprint="local",
            parent_action=None,
        ),
        incident=SimpleNamespace(failure_class="parent_lifecycle_mismatch"),
        reason="unresolved_recovery_reference",
    )
    monkeypatch.setattr(
        "cascade.task_rollup._parent_lifecycle_mismatch",
        lambda *_a, **_k: {
            "authoritative_generation": generation,
            "accountable_owner": "feature_team:feat_001",
            "evidence": {"tested_heads": {"current": ["source", "target"]}},
        },
    )
    monkeypatch.setattr(
        audit_recovery,
        "_bind_original_incident",
        lambda *_a, **_k: "task_001:queued_merge",
    )

    contract = audit_recovery._incident_contract(observation, root=tmp_path)

    assert contract is not None
    assert contract["original_incident_id"] == "task_001:queued_merge"
    assert contract["selected_capability"] == "feature_repair"
    assert contract["accountable_owner"] == "feature_team:feat_001"
    assert contract["evidence"]["parent_lifecycle_generation"] == generation


def test_audit_classifies_mismatch_before_ordinary_delivery_wait(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    doc = SimpleNamespace(
        meta=SimpleNamespace(id="task_001", tier="task", status="active")
    )
    evidence = SimpleNamespace(
        errors=(),
        parent_action=None,
        gates=(),
        unresolved_references=("task_001:queued_merge",),
        execution={"phase": "awaiting_merge", "delivery_queued": True},
        product_repository=tmp_path,
    )
    monkeypatch.setattr(
        "cascade.task_rollup._parent_lifecycle_mismatch",
        lambda *_a, **_k: {"authoritative_generation": "mismatch"},
    )

    assert audit._classification(doc, SimpleNamespace(), evidence) == (
        "proven_incident",
        "parent_lifecycle_mismatch",
    )


def test_audit_executor_records_unverified_repair_as_deferred(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, object]] = []

    def executor(task_id: str, **kwargs):
        calls.append({"task_id": task_id, **kwargs})
        return {
            "ok": True,
            "selected_operation": "feature_repair.admit",
            "accountable_owner": "feature_team:feat_001",
            "admitted_or_requested": True,
            "acknowledged": True,
            "executed": True,
            "verified": False,
            "refusal": None,
            "next_prerequisite": "resume_original_task_delivery",
        }

    descriptor = next(
        row
        for row in default_capability_registry().descriptors()
        if row.name == "feature.feature_repair"
    )
    descriptor = descriptor.__class__(
        **{
            field: getattr(descriptor, field)
            for field in descriptor.__dataclass_fields__
            if field != "executor"
        },
        executor=executor,
    )
    reservation = IncidentReservation(
        reservation_id="reservation",
        claim_token="claim",
        work_id="task_001",
        tier="task",
        generation="audit-generation",
        failure_class="parent_lifecycle_mismatch",
        capability=descriptor.name,
        durable_store="action_recovery",
        claimed_at="2026-01-01T00:00:00+00:00",
        claim_expires_at="2026-01-01T00:05:00+00:00",
    )
    recorded: list[dict[str, object]] = []
    monkeypatch.setattr(
        audit_recovery,
        "record_result",
        lambda _reservation, _ack, result, **_k: (
            recorded.append(dict(result)) or result
        ),
    )

    audit_recovery._execute_reservation(
        reservation,
        descriptor,
        {
            "accountable_owner": "feature_team:feat_001",
            "evidence": {"parent_lifecycle_generation": "mismatch-generation"},
        },
        root=tmp_path,
    )

    assert calls[0]["expected_generation"] == "mismatch-generation"
    assert recorded[0]["outcome"] == "deferred"
    assert recorded[0]["adapter_result"]["executed"] is True
    assert recorded[0]["adapter_result"]["verified"] is False


def test_missing_repair_capability_creates_scoped_handoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    observation = SimpleNamespace(
        classification="proven_incident",
        generation="audit-generation",
        incident=SimpleNamespace(failure_class="parent_lifecycle_mismatch"),
    )
    contract = {
        "work_id": "task_001",
        "tier": "task",
        "failure_class": "parent_lifecycle_mismatch",
        "authoritative_generation": "audit-generation",
        "selected_capability": "feature_repair",
        "accountable_owner": "feature_team:feat_001",
        "evidence": {"parent_lifecycle_generation": "mismatch-generation"},
    }
    monkeypatch.setattr(
        audit_recovery, "_bounded_observation", lambda *_a, **_k: observation
    )
    monkeypatch.setattr(audit_recovery, "_repair_target", lambda *_a, **_k: observation)
    monkeypatch.setattr(
        audit_recovery, "_incident_contract", lambda *_a, **_k: contract
    )
    monkeypatch.setattr(
        audit_recovery,
        "project_incident",
        lambda *_a, **_k: SimpleNamespace(eligible=True),
    )
    monkeypatch.setattr(
        audit_recovery,
        "probe_capability",
        lambda *_a, **_k: CapabilityProbe(
            "missing",
            "feature_repair",
            "operation_not_registered",
            "register the exact capability",
        ),
    )
    handoffs: list[tuple[str, str, dict]] = []
    monkeypatch.setattr(
        "cascade.watchdog.audit_investigation.request_investigation",
        lambda work_id, reason, evidence, **_k: handoffs.append(
            (work_id, reason, dict(evidence))
        ),
    )

    result = audit_recovery._admit_inline(
        tmp_path,
        "task_001",
        CapabilityRegistry(()),
        deadline=10**9,
        cancel_event=None,
    )

    assert result is None
    assert handoffs == [
        (
            "task_001",
            "capability_unavailable:operation_not_registered",
            {
                "failure_class": "parent_lifecycle_mismatch",
                "generation": "audit-generation",
                "selected_capability": "feature_repair",
                "owner_id": "feat_001",
                "evidence": {"parent_lifecycle_generation": "mismatch-generation"},
            },
        )
    ]
