"""Executable, incident-scoped health auditor authority."""

from dataclasses import replace
from pathlib import Path

from cascade.task.action_recovery import create_or_load_action, load_action, recovery_actions
from cascade.task.supervisor_recovery import supervisor_recover_task_delivery
from cascade.watchdog.capabilities import (
    HEALTH_AUDITOR_ROLE,
    CapabilityDescriptor,
    CapabilityRegistry,
    default_capability_registry,
    probe_capability,
    startup_capability_probes,
)
from cascade.watchdog.incidents import authoritative_generation, incident_record
from cascade.workspace.integration_worktree import IntegrationWorktree, save_registry
from tests.support import add_doc, make_repo


def _incident(*, gate: str | None = None) -> dict[str, object]:
    evidence = {"document_revision": "a" * 40}
    if gate is not None:
        evidence["gate"] = gate
    generation = authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence=evidence,
        capability="supervisor_recover_task_delivery",
    )
    return incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="orphan_delivery",
        generation=generation,
        evidence=evidence,
        selected_capability="supervisor_recover_task_delivery",
        outcome="deferred",
    )


def _registry() -> CapabilityRegistry:
    return CapabilityRegistry(
        (
            CapabilityDescriptor(
                name="task.supervisor_recover_task_delivery",
                operation="supervisor_recover_task_delivery",
                executor=supervisor_recover_task_delivery,
                tiers=frozenset({"task"}),
                failure_classes=frozenset({"orphan_delivery"}),
                owner_kinds=frozenset({"feature_team"}),
                required_evidence=("document_revision",),
                durable_store="orphan_delivery",
                attempt_bound=2,
                lock_protocol="task lifecycle lock",
                recheck_protocol="reread task and generation",
                resume_action="Restore the operation and rerun probe_capability.",
            ),
        )
    )


def _board(tmp_path: Path) -> Path:
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
        status="active",
        parent="feat_001",
    )
    return root


def test_startup_registry_contains_only_callable_bounded_recovery_seams() -> None:
    registry = default_capability_registry()
    probes = startup_capability_probes(registry=registry)

    assert probes
    assert all(row.available and row.role == HEALTH_AUDITOR_ROLE for row in probes)
    assert {row.operation for row in registry.descriptors()} == {
        "supervisor_recover_task_delivery",
        "recover_task",
        "retry_task",
        "retry_integration_branch_update",
        "resume_planning_owner",
        "restore_child_dispatch",
        "publish_integration_review",
        "reconcile_completion_rollup",
    }
    assert all(row.attempt_bound > 0 and callable(row.executor) for row in registry.descriptors())


def test_registry_fingerprint_tracks_authority_and_reachability_requirements() -> None:
    descriptor = next(
        row
        for row in default_capability_registry().descriptors()
        if row.name == "feature.retry_integration_branch_update"
    )
    original = CapabilityRegistry((descriptor,)).fingerprint()

    changes = (
        {"action_kind": "different_action"},
        {"requires_action": False},
        {"requires_worktree": False},
        {"lock_protocol": "different lock protocol"},
        {"recheck_protocol": "different recheck protocol"},
        {"resume_action": "Use a different exact resume action."},
    )
    assert all(
        CapabilityRegistry((replace(descriptor, **change),)).fingerprint() != original
        for change in changes
    )


def test_probe_enforces_concrete_owner_and_protected_gates(tmp_path: Path) -> None:
    root = _board(tmp_path)
    registry = _registry()

    available = probe_capability(
        _incident(),
        {"kind": "feature_team", "work_id": "feat_001"},
        root=root,
        registry=registry,
        persist=False,
    )
    wrong_incident = _incident()
    wrong_incident["accountable_owner"] = "feature_team:feat_999"
    wrong_owner = probe_capability(
        wrong_incident,
        {"kind": "feature_team", "work_id": "feat_999"},
        root=root,
        registry=registry,
        persist=False,
    )
    stale_incident = _incident()
    stale_incident["accountable_owner"] = "feature_team:feat_999"
    owner_mismatch = probe_capability(
        stale_incident,
        "feature_team:feat_001",
        root=root,
        registry=registry,
        persist=False,
    )
    assert available.available
    assert wrong_owner.state == "denied"
    assert wrong_owner.reason == "concrete_owner_not_authorized"
    assert owner_mismatch.reason == "incident_owner_mismatch"
    for gate in (
        "plan_approval",
        "feature_approval",
        "comment_required",
        "dependency_wait",
        "credential_missing",
        "installation_required",
        "destructive_git",
        "ambiguous_conflict",
    ):
        gated = probe_capability(
            _incident(gate=gate),
            "feature:feat_001",
            root=root,
            registry=registry,
            persist=False,
        )
        assert gated.state == "denied"
        assert gated.reason.startswith("protected_gate:")


def test_action_and_owned_worktree_must_both_be_reachable(tmp_path: Path) -> None:
    root = _board(tmp_path)
    descriptor = next(
        row
        for row in default_capability_registry().descriptors()
        if row.name == "feature.retry_integration_branch_update"
    )
    registry = CapabilityRegistry((descriptor,))
    evidence = {"action_id": "task_001:integration_branch_update"}
    generation = authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence=evidence,
        capability="retry_integration_branch_update",
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="transient_retry",
        generation=generation,
        evidence=evidence,
        selected_capability="retry_integration_branch_update",
        outcome="deferred",
    )

    no_action = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=registry,
        persist=False,
    )
    assert no_action.reason == "required_action_unreachable"

    create_or_load_action(
        "task_001:integration_branch_update",
        "integration_branch_update",
        root=root,
        attempt_bound=2,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
    )
    no_worktree = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=registry,
        persist=False,
    )
    assert no_worktree.reason == "required_worktree_unreachable"

    worktree = root / ".cascade" / "worktrees" / "feat_feat_001"
    worktree.mkdir(parents=True)
    save_registry(
        root,
        [
            IntegrationWorktree(
                "feature", "feat_001", "feat/feat_001", worktree, "a" * 40
            )
        ],
    )
    available = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=registry,
        persist=False,
    )
    assert available.available


def test_probe_resolves_action_kind_from_ledger_incident(tmp_path: Path) -> None:
    root = _board(tmp_path)
    action_id = "task_001:integration_branch_update"
    action = create_or_load_action(
        action_id,
        "integration_branch_update",
        root=root,
        attempt_bound=2,
        failure_classification="transient_retry",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
    )
    worktree = root / ".cascade" / "worktrees" / "feat_feat_001"
    worktree.mkdir(parents=True)
    save_registry(
        root,
        [
            IntegrationWorktree(
                "feature", "feat_001", "feat/feat_001", worktree, "a" * 40
            )
        ],
    )

    incident = action["incident"]
    assert incident["selected_capability"] == "integration_branch_update"

    probe = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        persist=False,
    )

    assert probe.available
    assert probe.capability == "feature.retry_integration_branch_update"


def test_required_action_must_belong_to_incident_work_id(tmp_path: Path) -> None:
    root = _board(tmp_path)
    add_doc(
        root,
        id="task_002",
        title="Other Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    action_id = "task_002:integration_branch_update"
    create_or_load_action(
        action_id,
        "integration_branch_update",
        root=root,
        attempt_bound=2,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_002"},
    )
    evidence = {"action_id": action_id}
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature_team:feat_001",
        failure_class="transient_retry",
        generation=authoritative_generation(
            work_id="task_001",
            tier="task",
            evidence=evidence,
            capability="retry_integration_branch_update",
        ),
        evidence=evidence,
        selected_capability="retry_integration_branch_update",
        outcome="deferred",
    )

    probe = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        persist=False,
    )

    assert probe.state == "missing"
    assert probe.reason == "required_action_work_mismatch"


def test_probe_resolves_health_retry_task_incident(tmp_path: Path) -> None:
    root = _board(tmp_path)
    evidence = {"document_revision": "a" * 40}
    generation = authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence=evidence,
        capability="retry_task",
    )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature:feat_001",
        failure_class="blocked_task_failed",
        generation=generation,
        evidence=evidence,
        selected_capability="retry_task",
        outcome="deferred",
    )

    probe = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        persist=False,
    )

    assert probe.available
    assert probe.capability == "feature.retry_task"


def test_missing_capability_is_durable_and_arrival_is_reprobed(tmp_path: Path) -> None:
    root = _board(tmp_path)
    incident = _incident()
    missing_registry = CapabilityRegistry()

    missing = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=missing_registry,
    )

    assert missing.state == "missing"
    assert "Register executable operation" in str(missing.resume_action)
    assert missing.receipt_action_id is not None
    missing_receipt = load_action(missing.receipt_action_id, root=root)
    assert missing_receipt is not None
    assert missing_receipt["recovery_state"] == "retryable"
    assert missing_receipt["metadata"]["resume_action"] == missing.resume_action
    assert missing_receipt["incident"]["request"]
    assert missing_receipt["incident"]["result"]

    arrived = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=_registry(),
    )

    assert arrived.available
    assert arrived.receipt_action_id != missing.receipt_action_id
    finalized_missing = load_action(str(missing.receipt_action_id), root=root)
    assert finalized_missing is not None
    assert finalized_missing["recovery_state"] == "completed"
    assert finalized_missing["attempts"][-1]["completion_metadata"] == {
        "probe_state": "available",
        "resolution": "capability_arrived",
        "superseded_by_action_id": arrived.receipt_action_id,
    }
    receipt = load_action(str(arrived.receipt_action_id), root=root)
    assert receipt is not None
    assert receipt["recovery_state"] == "completed"
    assert receipt["incident"]["outcome"] == "success"
    assert receipt["incident"]["request"]
    assert receipt["incident"]["acknowledgement"]
    assert receipt["incident"]["result"]


def test_missing_parent_capability_escalates_with_exact_resume_identity(
    tmp_path: Path,
) -> None:
    root = _board(tmp_path)
    evidence = {
        "document_revision": "a" * 40,
        "parent_action": {
            "responsible_work_id": "feat_001",
            "candidate_action": "resume_planning_owner",
        },
    }
    incident = incident_record(
        work_id="feat_001",
        tier="feature",
        accountable_owner="feature_team:feat_001",
        failure_class="parent_owner_stalled",
        generation=authoritative_generation(
            work_id="feat_001",
            tier="feature",
            evidence=evidence,
            capability="resume_planning_owner",
        ),
        evidence=evidence,
        selected_capability="resume_planning_owner",
        outcome="deferred",
    )

    missing = probe_capability(
        incident,
        "feature_team:feat_001",
        root=root,
        registry=CapabilityRegistry(),
    )

    assert missing.state == "missing"
    receipt = load_action(str(missing.receipt_action_id), root=root)
    assert receipt is not None
    assert receipt["recovery"]["owning_team"] == {
        "kind": "epic_team",
        "work_id": "epic_001",
    }
    assert receipt["metadata"]["responsible_work_id"] == "feat_001"
    assert receipt["metadata"]["original_action_identity"] == "resume_planning_owner"
    assert receipt["metadata"]["escalated_to"] == "epic_team:epic_001"
    assert "resume_planning_owner" in receipt["metadata"]["resume_action"]


def test_missing_operation_is_not_persisted_for_unauthorized_owner(
    tmp_path: Path,
) -> None:
    root = _board(tmp_path)
    incident = _incident()
    incident["accountable_owner"] = "feature_team:feat_999"

    denied = probe_capability(
        incident,
        "feature_team:feat_999",
        root=root,
        registry=CapabilityRegistry(),
    )

    assert denied.state == "denied"
    assert denied.reason == "concrete_owner_not_authorized"
    assert denied.receipt_action_id is None
    assert recovery_actions(root=root) == []


def test_real_observations_do_not_hash_probe_receipts_and_arrival_retires_old_generation(tmp_path, monkeypatch):
    from cascade.watchdog.audit import project_audit_observation

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001", status="active")
    add_doc(root, id="task_001", title="Blocked", tier="task", parent="feat_001", status="blocked")
    missing_registry = CapabilityRegistry()
    monkeypatch.setattr("cascade.watchdog.capabilities.default_capability_registry", lambda: missing_registry)
    initial = project_audit_observation("task_001", root=root)
    receipt_ids = set()
    for _ in range(3):
        observed = project_audit_observation("task_001", root=root)
        assert observed.generation == initial.generation
        assert observed.reason == initial.reason
        incident = _incident()
        incident["authoritative_generation"] = observed.generation.value
        missing = probe_capability(incident, "feature_team:feat_001", root=root)
        assert missing.state == "missing"
        receipt_ids.add(missing.receipt_action_id)
    assert len(receipt_ids) == 1

    monkeypatch.setattr("cascade.watchdog.capabilities.default_capability_registry", _registry)
    arrived_observation = project_audit_observation("task_001", root=root)
    assert arrived_observation.generation != initial.generation
    incident = _incident()
    incident["authoritative_generation"] = arrived_observation.generation.value
    available = probe_capability(incident, "feature_team:feat_001", root=root)
    assert available.available
    assert load_action(str(next(iter(receipt_ids))), root=root)["recovery_state"] == "completed"
    assert project_audit_observation("task_001", root=root).generation == arrived_observation.generation
