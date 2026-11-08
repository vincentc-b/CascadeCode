"""Real protected waits remain silent through observation and admission."""

import json
from contextlib import contextmanager
from dataclasses import replace

import pytest

from cascade.comments.store import comment, sidecar_path
from cascade.task.action_recovery import create_or_load_action
from cascade.watchdog.audit import local_audit_fingerprint, project_audit_observation
from cascade.watchdog.capabilities import default_capability_registry, probe_capability
from cascade.watchdog.incidents import incident_record
from cascade.watchdog.reservations import reserve_after_recheck
from cascade.workspace.integration_worktree import ensure_integration_worktree
from tests.support import add_doc, make_repo
from tests.watchdog.test_audit import _commit, _repository_bytes
from tests.watchdog.test_reservations import _real_stale_task


def _capability():
    return next(row for row in default_capability_registry().descriptors()
                if row.name == "task.supervisor_recover_task_delivery")


def _incident(observed, capability, *, failure="stalled_execution"):
    return incident_record(
        work_id=observed.work_id.value, tier=observed.tier,
        accountable_owner="feature_team:feat_001", failure_class=failure,
        generation=observed.generation.value,
        evidence={"document_revision": observed.document_revision.value,
                  "gates": list(observed.evidence.gates)},
        selected_capability=capability.name, outcome="deferred",
    )


def _assert_wait_refuses(root, expected_gate):
    before = _repository_bytes(root)
    observed = project_audit_observation("task_001", root=root)
    assert observed.classification == "expected_wait", observed
    assert expected_gate in observed.evidence.gates
    assert observed.incident is None
    capability = _capability()
    # Defensive admission of a stale caller's repair classification must fail.
    incident = _incident(observed, capability)
    probe = probe_capability(incident, "feature_team:feat_001", root=root, persist=False)
    assert probe.state == "denied", probe
    decision = reserve_after_recheck(incident, capability, root=root)
    assert decision.state == "gated", decision
    assert _repository_bytes(root) == before


@pytest.mark.parametrize("comment_owner", ["feat_001", "epic_001"])
@pytest.mark.parametrize("other_task", [False, True])
def test_blocking_comment_beats_failed_task_and_recovery_action(tmp_path, comment_owner, other_task):
    from cascade.board.store import read_doc, write_doc
    from cascade.task.execution import mark_terminal

    root = _real_stale_task(tmp_path)
    mark_terminal("task_001", "failed", root=root)
    doc = read_doc("task_001", root=root)
    doc.meta.status = "blocked"
    write_doc(doc, root=root)
    if other_task:
        add_doc(root, id="task_002", title="Independent failed sibling", tier="task",
                status="blocked", parent="feat_001")
        mark_terminal("task_002", "failed", root=root)
        feature = read_doc("feat_001", root=root)
        feature.meta.children.append("task_002")
        write_doc(feature, root=root)
    create_or_load_action("task_001:delivery", "delivery", root=root,
                          attempt_bound=3, recovery_state="retryable",
                          evidence={"affected_work_id": "task_001"})
    comment(comment_owner, "scope", "Await the human decision", author="human",
            blocking=True, blocks=["task_001"], root=root)
    _assert_wait_refuses(root, "review_threads_blocking")
    parent = project_audit_observation("feat_001", root=root)
    if other_task:
        assert parent.classification == "proven_incident", parent
        assert "task_002" in parent.reason
    else:
        assert parent.classification == "expected_wait", parent
        assert parent.incident is None


def test_explicit_human_action_gate_beats_generic_unresolved_action(tmp_path):
    root = _real_stale_task(tmp_path)
    create_or_load_action("task_001:license", "dependency_install", root=root,
                          attempt_bound=3, recovery_state="awaiting_human_gate",
                          evidence={"affected_work_id": "task_001"},
                          human_blocker={"code": "license_acceptance",
                                         "message": "Human acceptance required",
                                         "required_action": "Accept the license"})
    _assert_wait_refuses(root, "human_gate:task_001:license")


@pytest.mark.parametrize("status", ["active", "cancelled", "missing"])
def test_canonical_dependency_wait_beats_unresolved_action(tmp_path, status):
    from cascade.board.store import read_doc, write_doc

    root = _real_stale_task(tmp_path)
    dependency = add_doc(root, id="task_002", title="Dependency", tier="task",
                         status="active" if status == "missing" else status,
                         parent="feat_001")
    doc = read_doc("task_001", root=root)
    doc.meta.depends_on = ["task_002"]
    write_doc(doc, root=root)
    create_or_load_action("task_001:delivery", "delivery", root=root,
                          attempt_bound=3, recovery_state="retryable",
                          evidence={"affected_work_id": "task_001"})
    if status == "missing":
        dependency.meta.path.unlink()
        observed = project_audit_observation("task_001", root=root)
        assert observed.classification == "unavailable_evidence", observed
        assert "dependency_status_unavailable:task_002" in observed.evidence.errors
        assert observed.incident is None
        incident = _incident(observed, _capability())
        assert not probe_capability(incident, "feature_team:feat_001", root=root, persist=False).available
        assert not reserve_after_recheck(incident, _capability(), root=root).reserved
    else:
        _assert_wait_refuses(root, "dependency:task_002")


@pytest.mark.parametrize("comment_owner,kind", [("feat_001", "feature"), ("epic_001", "epic")])
@pytest.mark.parametrize("split", [False, True])
def test_canonical_worktree_comment_arrival_invalidates_locked_admission(tmp_path, monkeypatch, comment_owner, kind, split):
    import cascade.watchdog.reservations as reservations
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext

    tracking = _real_stale_task(tmp_path)
    owner = ensure_integration_worktree(kind, comment_owner,
        branch=f"{'feat' if kind == 'feature' else 'epic'}/{comment_owner}",
        base_ref="main", trunk=tracking)
    root = make_repo(tmp_path / "product") if split else tracking
    if split:
        _commit(root, "product source")
        set_project_context(ProjectContext.split(root, tracking))
    registry_lock = tracking / ".cascade" / "worktrees.lock"
    registry_lock.unlink(missing_ok=True)
    observed = project_audit_observation("task_001", root=root)
    assert not registry_lock.exists()
    assert observed.classification == "proven_incident", observed
    before = local_audit_fingerprint("task_001", root=root)
    original_lock = reservations.task_lifecycle_lock
    original_recheck = reservations._locked_local_recheck

    @contextmanager
    def racing_lock(*, root):
        comment(comment_owner, "scope", "New protected decision", author="human",
                blocking=True, blocks=["task_001"], root=tracking)
        assert sidecar_path(comment_owner, root=tracking).is_relative_to(owner.path)
        assert local_audit_fingerprint("task_001", root=root) != before
        with original_lock(root=root):
            yield

    def no_subprocess_recheck(*args, **kwargs):
        with monkeypatch.context() as patch:
            patch.setattr("subprocess.run", lambda *a, **k: pytest.fail("subprocess under admission lock"))
            return original_recheck(*args, **kwargs)

    monkeypatch.setattr(reservations, "task_lifecycle_lock", racing_lock)
    monkeypatch.setattr(reservations, "_locked_local_recheck", no_subprocess_recheck)
    decision = reserve_after_recheck(_incident(observed, _capability()), _capability(), root=root)
    assert decision.state == "stale", decision
    monkeypatch.setattr(reservations, "task_lifecycle_lock", original_lock)
    _assert_wait_refuses(root, "review_threads_blocking")


def test_review_pending_keeps_retained_worktree_quiet_but_permits_concrete_repair(tmp_path):
    from cascade.board.store import move_doc

    root = _real_stale_task(tmp_path)
    move_doc("feat_001", "completed", root=root)
    ensure_integration_worktree("feature", "feat_001", branch="feat/feat_001",
                                base_ref="main", trunk=root)
    (root / ".cascade" / "reviews.json").write_text(json.dumps({
        "feat_001": {"number": "123", "closed": False}}))
    waiting = project_audit_observation("feat_001", root=root)
    assert waiting.classification == "expected_wait", waiting
    assert waiting.reason == "review_pending"
    create_or_load_action("feat_001:integration_branch_update", "integration_branch_update",
        root=root, attempt_bound=3, recovery_state="awaiting_owner_decision",
        evidence={"affected_work_id": "feat_001"})
    observed = project_audit_observation("feat_001", root=root)
    assert observed.classification == "proven_incident", observed
    assert observed.evidence.gates == ("review_pending",)
    # Exercise admission's generic contract with an adapter for the concrete
    # review repair; review_pending cannot veto an otherwise authorized owner.
    capability = replace(_capability(), tiers=frozenset({"feature"}),
                         failure_classes=frozenset({observed.incident.failure_class}))
    incident = _incident(observed, capability, failure=observed.incident.failure_class)
    assert reserve_after_recheck(incident, capability, root=root).reserved


def test_observation_reads_fresh_owned_task_copy_without_registry_writes(tmp_path):
    from cascade.board.store import read_doc, write_doc

    root = _real_stale_task(tmp_path)
    owner = ensure_integration_worktree("feature", "feat_001", branch="feat/feat_001",
                                       base_ref="main", trunk=root)
    doc = read_doc("task_001", root=owner.path)
    doc.meta.status = "blocked"
    write_doc(doc, root=owner.path)
    registry_lock = root / ".cascade" / "worktrees.lock"
    registry_lock.unlink(missing_ok=True)
    before = _repository_bytes(root)
    observed = project_audit_observation("task_001", root=root)
    assert observed.evidence.status == "blocked"
    assert observed.classification == "proven_incident", observed
    assert observed.reason == "blocked"
    assert not registry_lock.exists()
    assert _repository_bytes(root) == before
