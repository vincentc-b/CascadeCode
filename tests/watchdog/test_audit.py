"""Typed, mutation-free canonical audit projections."""

from __future__ import annotations

import json
import subprocess
import time
from datetime import date
from pathlib import Path

import pytest

import cascade.board.gitutil as gitutil
from cascade.board.context import set_project_context
from cascade.task.execution import mark_awaiting_merge, mark_queued
from cascade.task_rollup import invalidate_task_merge, queue_task_merge
from cascade.watchdog.audit import (
    AuditGeneration,
    AuditIdentityError,
    BranchName,
    DocumentRevision,
    FeatureAuditIdentity,
    FeatureId,
    GitHead,
    TaskId,
    project_audit_observation,
    project_audit_observations,
    select_audit_candidates,
)
from cascade.watchdog.audit_recovery import _incident_contract
from cascade.watchdog.incidents import incident_record, project_incident
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


def _commit(root: Path, message: str = "snapshot") -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", message], cwd=root, check=True
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _repository_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.relative_to(root).parts
    }


def test_typed_identity_rejects_interchanged_fields() -> None:
    sha = "a" * 40
    generation = AuditGeneration("sha256:" + "b" * 64)

    with pytest.raises(AuditIdentityError):
        DocumentRevision(FeatureId("feat_001"))  # type: ignore[arg-type]
    with pytest.raises(AuditIdentityError):
        FeatureAuditIdentity(
            document_revision=GitHead(sha),  # type: ignore[arg-type]
            git_head=GitHead(sha),
            branch=BranchName("feature/one"),
            generation=generation,
            work_id=FeatureId("feat_001"),
        )
    with pytest.raises(AuditIdentityError):
        FeatureAuditIdentity(
            document_revision=DocumentRevision(sha),
            git_head=GitHead(sha),
            branch=generation,  # type: ignore[arg-type]
            generation=generation,
            work_id=FeatureId("feat_001"),
        )
    with pytest.raises(AuditIdentityError):
        FeatureAuditIdentity(
            document_revision=DocumentRevision(sha),
            git_head=GitHead(sha),
            branch=BranchName("feature/one"),
            generation=generation,
            work_id=TaskId("task_001"),  # type: ignore[arg-type]
        )


def test_projection_covers_all_tiers_and_preserves_wait_gates(tmp_path: Path) -> None:
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
        id="task_002",
        title="Dependency",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
        depends_on=["task_002"],
    )
    _commit(root)
    mark_queued("task_001", root=root)
    mark_queued("task_002", root=root)

    observations = project_audit_observations(root=root)

    assert {row.identity.tier for row in observations} == {"task", "feature", "epic"}
    task = next(row for row in observations if str(row.identity.work_id) == "task_001")
    epic = next(row for row in observations if str(row.identity.work_id) == "epic_001")
    assert task.classification == "expected_wait"
    assert task.reason == "dependency:task_002"
    assert task.evidence.execution["health"] == "queued"
    assert epic.classification == "expected_wait"
    assert "plan_approval" in epic.evidence.gates


def test_task_delivery_queue_loss_is_a_pinned_recovery_incident(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
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
    _commit(root)
    mark_queued("task_001", root=root)
    mark_awaiting_merge("task_001", root=root)
    queue_task_merge("task_001", root=root)

    queued = project_audit_observation("task_001", root=root)
    assert (queued.classification, queued.reason) == (
        "expected_wait",
        "delivery_queued",
    )

    invalidate_task_merge("task_001", root=root)
    missing = project_audit_observation("task_001", root=root)

    assert missing.classification == "proven_incident"
    assert missing.reason == "validated_delivery_missing"
    assert missing.incident is not None
    assert missing.incident.failure_class == "validated_delivery_missing"
    assert missing.evidence.execution["delivery_queued"] is False
    contract = _incident_contract(missing, root=root)
    assert contract is not None
    assert contract["accountable_owner"] == "feature_team:feat_001"
    assert contract["authoritative_generation"] == missing.generation.value
    assert contract["selected_capability"] == "supervisor_recover_task_delivery"
    assert contract["evidence"]["parent_id"] == "feat_001"


def test_projection_resolves_tracking_docs_and_product_git_without_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = make_repo(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    product_head = _commit(product, "product")
    context = ProjectContext.split(product, tracking)
    set_project_context(context)
    try:
        doc = add_doc(
            tracking, id="epic_001", title="Epic", tier="epic", status="completed"
        )
        registry_lock = tracking / ".cascade" / "worktrees.lock"
        registry_lock.unlink(missing_ok=True)
        _commit(tracking, "tracking")

        def mutation_forbidden(*_args, **_kwargs):
            raise AssertionError("audit projection invoked a mutation path")

        monkeypatch.setattr(
            "cascade.watchdog.health.sweep_supervisor_health", mutation_forbidden
        )
        monkeypatch.setattr(
            "cascade.watchdog.health._remediate_if_unchanged", mutation_forbidden
        )
        before = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tracking,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert not registry_lock.exists()

        observation = project_audit_observation("epic_001", root=product)

        after = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=tracking,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        assert observation.identity.document_revision.value == doc.sha
        assert observation.identity.git_head == GitHead(product_head)
        assert observation.evidence.tracking_repository == tracking.resolve()
        assert observation.evidence.product_repository == product.resolve()
        assert observation.classification == "healthy"
        assert before == after == ""
        assert not registry_lock.exists()
    finally:
        set_project_context(None)


def test_projection_bounds_document_revision_git_lookup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    real_popen = gitutil.subprocess.Popen
    hung_commands: list[list[str]] = []

    class HungLog:
        returncode = None
        terminated = False

        def communicate(self, *, timeout=None):
            if not self.terminated:
                time.sleep(timeout or 0)
                raise subprocess.TimeoutExpired(hung_commands[-1], timeout)
            self.returncode = -15
            return "", ""

        def terminate(self):
            self.terminated = True

    def popen(command, *args, **kwargs):
        if command[1:2] == ["log"]:
            hung_commands.append(command)
            return HungLog()
        return real_popen(command, *args, **kwargs)

    monkeypatch.setattr(gitutil.subprocess, "Popen", popen)

    with pytest.raises(subprocess.TimeoutExpired):
        project_audit_observation(
            "epic_001", root=root, timeout_seconds=0.2
        )

    assert hung_commands


def test_healthy_candidate_and_observation_are_byte_silent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    (root / ".cascade" / "worktrees.lock").unlink(missing_ok=True)
    _commit(root)
    cascade_dir = root / ".cascade"
    sentinels = {
        "executions.json": {"actions": {}, "executions": {}},
        "reviews.json": {},
        "resolution_actions.json": {"records": {}},
        "orphan_delivery_recoveries.json": {"recoveries": {}},
        "events.json": {"events": []},
        "notifications.json": {"notifications": []},
        "model_turns.json": {"turns": []},
        "queues.json": {"queues": {}},
    }
    for filename, payload in sentinels.items():
        (cascade_dir / filename).write_text(
            json.dumps(payload, sort_keys=True), encoding="utf-8"
        )
    before = _repository_bytes(root)

    page = select_audit_candidates(root=root)
    observation = project_audit_observation("epic_001", root=root)

    assert any(str(row.work_id) == "epic_001" for row in page.candidates)
    assert observation.classification == "healthy"
    assert _repository_bytes(root) == before
    assert not (cascade_dir / "worktrees.lock").exists()


def test_projection_classifies_unavailable_authoritative_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    monkeypatch.setattr(
        "cascade.watchdog.audit.recovery_actions",
        lambda **_kwargs: (_ for _ in ()).throw(ValueError("malformed sidecar")),
    )

    observation = project_audit_observation("epic_001", root=root)

    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "action_recovery_unavailable"
    assert observation.incident is None


def test_completed_work_with_unresolved_recovery_is_an_incident(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    monkeypatch.setattr(
        "cascade.watchdog.audit._unresolved_references",
        lambda _work_id, _product: (("action_001",), None),
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit.recovery_actions",
        lambda **_kwargs: [
            {
                "action_id": "action_001",
                "action_kind": "integration_branch_update",
            }
        ],
    )

    observation = project_audit_observation("epic_001", root=root)

    assert observation.classification == "proven_incident"
    assert observation.reason == "unresolved_recovery_reference"
    assert observation.incident is not None
    assert observation.incident.failure_class == "integration_branch_update"


@pytest.mark.parametrize(
    ("tier", "work_id", "filename", "source"),
    (
        ("feature", "feat_001", "resolution_actions.json", "reconciliation"),
        ("epic", "epic_001", "orphan_delivery_recoveries.json", "cleanup"),
    ),
)
def test_old_completed_sidecar_reference_is_selected_and_observed_as_incident(
    tmp_path: Path, tier: str, work_id: str, filename: str, source: str
) -> None:
    root = make_repo(tmp_path)
    if tier == "feature":
        add_doc(
            root,
            id="epic_001",
            title="Parent",
            tier="epic",
            status="completed",
            children=[work_id],
        )
    add_doc(
        root,
        id=work_id,
        title="Old completed work",
        tier=tier,
        status="completed",
        parent="epic_001" if tier == "feature" else None,
    )
    _commit(root)
    sidecar = root / ".cascade" / filename
    sidecar.write_text(
        json.dumps({"records": {f"{work_id}:pending": {"work_id": work_id}}}),
        encoding="utf-8",
    )

    page = select_audit_candidates(root=root, today=date(2026, 11, 20))
    candidate = next(row for row in page.candidates if str(row.work_id) == work_id)
    observation = project_audit_observation(work_id, root=root)

    assert f"unresolved_{source}" in candidate.reasons
    assert observation.classification == "proven_incident"
    assert observation.reason == "unresolved_recovery_reference"
    assert f"{source}:{work_id}" in observation.evidence.unresolved_references

    sidecar.write_text(
        json.dumps(
            {
                "records": {
                    f"{work_id}:pending": {
                        "work_id": work_id,
                        "outcome": "success",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    resolved = project_audit_observation(work_id, root=root)
    assert resolved.classification == "healthy"
    assert resolved.generation != observation.generation


@pytest.mark.parametrize("number_present", [True, False])
@pytest.mark.parametrize("review_path", ["pull", "-/merge_requests"])
def test_real_resolution_action_maps_review_identity_to_old_feature(
    tmp_path: Path, number_present: bool, review_path: str,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001",
        title="Old feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    _commit(root)
    sidecars = root / ".cascade"
    (sidecars / "reviews.json").write_text(
        json.dumps(
            {
                "feat_001": {
                    **({"number": "147"} if number_present else {}),
                    "url": f"https://forge.example/repo/{review_path}/147",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    (sidecars / "resolution_actions.json").write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "action_id": "resolution:v1:opaque",
                    "idempotency_key": "resolution:v1:opaque",
                    "status": "blocked",
                    "handoff": {
                        "action_id": "resolution:v1:opaque",
                        "accountable_team": "feature:feat_001",
                        "review_id": "147",
                    },
                    "request": {
                        "review_id": "147",
                        "review_url": f"https://forge.example/repo/{review_path}/147",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    page = select_audit_candidates(root=root, today=date(2026, 11, 20))
    candidate = next(row for row in page.candidates if str(row.work_id) == "feat_001")
    observation = project_audit_observation("feat_001", root=root)

    assert "unresolved_reconciliation" in candidate.reasons
    assert observation.classification == "proven_incident"
    assert "reconciliation:feat_001" in observation.evidence.unresolved_references
    # The nested handoff must not poison observation of unrelated work.
    assert project_audit_observation("epic_001", root=root).classification == "healthy"

    (sidecars / "resolution_actions.json").write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "action_id": "resolution:v1:opaque",
                    "idempotency_key": "resolution:v1:opaque",
                    "status": "success",
                    "request": {
                        "review_id": "147",
                        "review_url": "https://forge.example/repo/pull/147",
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    resolved = project_audit_observation("feat_001", root=root)
    assert resolved.classification == "expected_wait"
    assert "reconciliation:feat_001" not in resolved.evidence.unresolved_references
    assert resolved.generation != observation.generation


@pytest.mark.parametrize("malformed", [True, False])
def test_resolution_action_without_unique_review_owner_is_unavailable(
    tmp_path: Path, malformed: bool
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    review = {
        "number": "147",
        "url": "https://forge.example/repo/pull/147",
        "closed": False,
    }
    reviews = {"epic_001": review}
    if not malformed:
        reviews["feat_001"] = review
    sidecars = root / ".cascade"
    (sidecars / "reviews.json").write_text(json.dumps(reviews), encoding="utf-8")
    request = (
        {}
        if malformed
        else {
            "review_id": "147",
            "review_url": "https://forge.example/repo/pull/147",
        }
    )
    (sidecars / "resolution_actions.json").write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "status": "blocked",
                    "request": request,
                }
            }
        ),
        encoding="utf-8",
    )

    observation = project_audit_observation("epic_001", root=root)

    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "reconciliation:unavailable"


def test_resolution_action_with_conflicting_review_identities_is_unavailable(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001",
        title="Old feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    _commit(root)
    sidecars = root / ".cascade"
    (sidecars / "reviews.json").write_text(
        json.dumps(
            {
                "feat_001": {
                    "number": "147",
                    "url": "https://forge.example/repo/pull/147",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    (sidecars / "resolution_actions.json").write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "action_id": "resolution:v1:opaque",
                    "status": "blocked",
                    "request": {
                        "review_id": "147",
                        "review_url": "https://forge.example/repo/pull/999",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    observation = project_audit_observation("feat_001", root=root)

    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "reconciliation:unavailable"
    assert "reconciliation:feat_001" not in observation.evidence.unresolved_references


@pytest.mark.parametrize(
    "action_request",
    [
        {
            "review_id": "147",
            "review_url": "https://forge.example/repo/pull/147",
        },
        {},
    ],
    ids=("review-identity", "empty-request"),
)
def test_resolution_action_without_review_registry_is_unavailable(
    tmp_path: Path, action_request: dict[str, str]
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Old epic", tier="epic", status="completed")
    _commit(root)
    sidecar = root / ".cascade" / "resolution_actions.json"
    sidecar.write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "action_id": "resolution:v1:opaque",
                    "status": "blocked",
                    "request": action_request,
                }
            }
        ),
        encoding="utf-8",
    )

    page = select_audit_candidates(root=root, today=date(2026, 11, 20))
    observation = project_audit_observation("epic_001", root=root)

    assert not page.candidates
    assert page.unavailable_evidence == ("reconciliation:unavailable",)
    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "reconciliation:unavailable"

    payload = json.loads(sidecar.read_text(encoding="utf-8"))
    payload["resolution:v1:opaque"]["status"] = "success"
    sidecar.write_text(json.dumps(payload), encoding="utf-8")
    resolved = project_audit_observation("epic_001", root=root)
    assert resolved.classification == "healthy"
    assert resolved.generation != observation.generation


def test_resolution_action_without_request_is_unavailable(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    sidecars = root / ".cascade"
    (sidecars / "reviews.json").write_text("{}", encoding="utf-8")
    (sidecars / "resolution_actions.json").write_text(
        json.dumps(
            {
                "resolution:v1:opaque": {
                    "action_id": "resolution:v1:opaque",
                    "status": "blocked",
                }
            }
        ),
        encoding="utf-8",
    )

    observation = project_audit_observation("epic_001", root=root)

    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "reconciliation:unavailable"


def test_unreadable_reconciliation_sidecar_makes_observation_unavailable(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_001",
        title="Parent",
        tier="epic",
        status="completed",
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
    _commit(root)
    sidecar = root / ".cascade" / "resolution_actions.json"
    sidecar.write_text("{broken", encoding="utf-8")
    before = sidecar.read_bytes()

    observation = project_audit_observation("feat_001", root=root)

    assert observation.classification == "unavailable_evidence"
    assert observation.reason == "reconciliation:unavailable"
    assert sidecar.read_bytes() == before


def test_capability_authority_change_invalidates_success_suppression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)

    class Registry:
        def __init__(self, fingerprint: str) -> None:
            self.value = fingerprint

        def fingerprint(self) -> str:
            return self.value

    monkeypatch.setattr(
        "cascade.watchdog.capabilities.default_capability_registry",
        lambda: Registry("authority-v1"),
    )
    first = project_audit_observation("epic_001", root=root)
    success = incident_record(
        work_id="epic_001",
        tier="epic",
        accountable_owner="epic_team:epic_001",
        failure_class="integration_branch_update",
        generation=first.generation.value,
        evidence={},
        selected_capability="retry_integration_branch_update",
        outcome="success",
    )
    assert not project_incident(
        first,
        {"prior": {"incident": success}},
        failure_class="integration_branch_update",
    ).eligible

    monkeypatch.setattr(
        "cascade.watchdog.capabilities.default_capability_registry",
        lambda: Registry("authority-v2"),
    )
    changed = project_audit_observation("epic_001", root=root)

    assert changed.generation != first.generation
    assert project_incident(
        changed,
        {"prior": {"incident": success}},
        failure_class="integration_branch_update",
    ).eligible


def test_old_completed_work_with_unresolved_cleanup_is_observed(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    _commit(root)
    path = root / ".cascade" / "orphan_delivery_recoveries.json"
    path.write_text(
        json.dumps(
            {
                "recoveries": {
                    "task_001:delivery:1": {
                        "decision": "unsafe",
                        "incident": {"work_id": "task_001", "outcome": "unsafe"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    unresolved = project_audit_observation("task_001", root=root)
    assert unresolved.classification == "proven_incident"
    assert "cleanup:task_001" in unresolved.evidence.unresolved_references

    path.write_text(
        json.dumps(
            {
                "recoveries": {
                    "task_001:delivery:1": {
                        "decision": "requeue_commit",
                        "incident": {"work_id": "task_001", "outcome": "success"},
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    recovered = project_audit_observation("task_001", root=root)
    assert recovered.classification == "healthy"
    assert recovered.generation != unresolved.generation


def test_completed_work_with_open_review_remains_an_expected_wait(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    review_path = root / ".cascade" / "reviews.json"
    review_path.write_text(
        json.dumps({"epic_001": {"state": "awaiting_review", "closed": False}}),
        encoding="utf-8",
    )
    before = review_path.read_bytes()

    waiting = project_audit_observation("epic_001", root=root)

    assert waiting.classification == "expected_wait"
    assert waiting.reason == "review_pending"
    assert review_path.read_bytes() == before

    review_path.write_text(
        json.dumps({"epic_001": {"state": "merged", "closed": True}}),
        encoding="utf-8",
    )
    closed = project_audit_observation("epic_001", root=root)
    assert closed.classification == "healthy"
    assert closed.generation != waiting.generation


def test_elapsed_heartbeat_age_does_not_change_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    _commit(root)
    age = [10.0]

    def execution(_task_ids, *, root):
        return {
            "task_001": {
                "phase": "running",
                "health": "healthy",
                "heartbeat_at": "2026-11-08T00:00:00+00:00",
                "heartbeat_age_seconds": age[0],
            }
        }

    monkeypatch.setattr("cascade.watchdog.audit.execution_views", execution)
    first = project_audit_observation("task_001", root=root)
    age[0] = 11.0
    second = project_audit_observation("task_001", root=root)

    assert first.classification == second.classification == "expected_wait"
    assert first.generation == second.generation


def test_supervisor_generation_changes_with_child_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
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
        status="blocked",
        parent="feat_001",
    )
    _commit(root)
    health = ["failed"]
    monkeypatch.setattr(
        "cascade.watchdog.audit.execution_views",
        lambda _ids, *, root: {"task_001": {"health": health[0], "outcome": "failed"}},
    )
    monkeypatch.setattr(
        "cascade.watchdog.audit.compute_feature_readiness",
        lambda *_args, **_kwargs: None,
    )

    first = project_audit_observation("feat_001", root=root)
    health[0] = "stale"
    second = project_audit_observation("feat_001", root=root)

    assert first.classification == second.classification == "proven_incident"
    assert first.reason != second.reason
    assert first.generation != second.generation


def test_registered_worktree_head_changes_authoritative_generation(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    _commit(root)
    worktree = root / ".cascade" / "worktrees" / "epic_epic_001"
    worktree.parent.mkdir(parents=True)
    subprocess.run(
        ["git", "worktree", "add", "-b", "epic/epic_001", str(worktree)],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    (root / ".cascade" / "worktrees.json").write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "kind": "epic",
                        "work_id": "epic_001",
                        "branch": "epic/epic_001",
                        "path": ".cascade/worktrees/epic_epic_001",
                        "base_sha": "a" * 40,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    first = project_audit_observation("epic_001", root=root)
    assert first.classification == "expected_wait"
    assert first.reason == "observing:local_integration_unpublished"
    assert first.evidence.parent_action is not None
    assert first.evidence.parent_action.candidate_action == "publish_integration_review"
    (worktree / "change.txt").write_text("new head", encoding="utf-8")
    _commit(worktree, "advance owned branch")
    second = project_audit_observation("epic_001", root=root)

    assert first.git_head != second.git_head
    assert first.generation != second.generation
    assert second.branch == BranchName("epic/epic_001")


@pytest.mark.parametrize(
    ("tier", "work_id", "parent_id"),
    (
        ("feature", "feat_001", "epic_001"),
        ("epic", "epic_001", None),
    ),
)
def test_parent_owner_absence_requires_unchanged_configured_interval(
    tmp_path: Path,
    tier: str,
    work_id: str,
    parent_id: str | None,
) -> None:
    from datetime import datetime, timezone

    from cascade.board.store import read_doc, write_doc

    root = make_repo(tmp_path)
    (root / "cascade.toml").write_text(
        '[automation.health_audit]\ninterval = "1m"\n', encoding="utf-8"
    )
    if parent_id is not None:
        add_doc(root, id=parent_id, title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id=work_id,
        title="Owner",
        tier=tier,  # type: ignore[arg-type]
        status="active",
        parent=parent_id,
    )
    if tier == "epic":
        epic = read_doc(work_id, root=root)
        epic.meta.plan_approved_at = datetime(2026, 11, 8, tzinfo=timezone.utc)
        write_doc(epic, root=root)
    _commit(root)
    now = {"value": 10.0}

    first = project_audit_observation(
        work_id, root=root, monotonic=lambda: now["value"]
    )
    now["value"] = 69.0
    early = project_audit_observation(
        work_id, root=root, monotonic=lambda: now["value"]
    )
    now["value"] = 70.0
    proven = project_audit_observation(
        work_id, root=root, monotonic=lambda: now["value"]
    )

    assert first.classification == early.classification == "expected_wait"
    assert first.reason == early.reason == "observing:planning_owner_absent"
    assert proven.classification == "proven_incident"
    assert proven.reason == "resume_planning_owner"
    assert first.generation == early.generation == proven.generation
    action = proven.evidence.parent_action
    assert action is not None
    assert action.responsible_work_id == work_id
    assert action.candidate_action == "resume_planning_owner"
    assert action.state == "executable"
    assert action.observation_count == 3
    assert action.unchanged_for_seconds == 60.0
    assert action.required_interval_seconds == 60.0


def test_live_parent_owner_never_becomes_a_stall(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    _commit(root)
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda _work_id: True
    )

    first = project_audit_observation("feat_001", root=root, monotonic=lambda: 0.0)
    later = project_audit_observation(
        "feat_001", root=root, monotonic=lambda: 100_000.0
    )

    assert first.classification == later.classification == "expected_wait"
    assert first.reason == later.reason == "live_owner"
    assert later.evidence.parent_action is not None
    assert later.evidence.parent_action.state == "gated"


@pytest.mark.parametrize("registry_number, registry_url", [
    ("999", "https://forge.example/repo/pull/147"),
    (None, "https://forge.example/repo/unknown/147"),
    (None, "http://[invalid/pull/147"),
])
def test_resolution_url_fallback_never_overrides_conflicting_or_unknown_identity(
    registry_number, registry_url,
):
    from cascade.watchdog.audit import _collect_resolution_review_references

    references = []
    valid = _collect_resolution_review_references(
        {"action_id": "resolution:v1:one", "status": "blocked", "request": {
            "review_id": "147", "review_url": registry_url,
        }},
        {"feat_001": {"number": registry_number, "url": registry_url}},
        references,
    )
    assert not valid
    assert references == []
