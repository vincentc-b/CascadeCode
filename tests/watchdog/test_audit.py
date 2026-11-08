"""Typed, mutation-free canonical audit projections."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.context import set_project_context
from cascade.task.execution import mark_queued
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
)
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, make_repo


def _commit(root: Path, message: str = "snapshot") -> str:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "--allow-empty", "-m", message], cwd=root, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True,
        capture_output=True, text=True,
    ).stdout.strip()


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
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active", children=["feat_001"])
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001", children=["task_001"])
    add_doc(root, id="task_002", title="Dependency", tier="task", status="active", parent="feat_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001", depends_on=["task_002"])
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


def test_projection_resolves_tracking_docs_and_product_git_without_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    product = make_repo(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    product_head = _commit(product, "product")
    context = ProjectContext.split(product, tracking)
    set_project_context(context)
    try:
        doc = add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="completed")
        _commit(tracking, "tracking")

        def mutation_forbidden(*_args, **_kwargs):
            raise AssertionError("audit projection invoked a mutation path")

        monkeypatch.setattr("cascade.watchdog.health.sweep_supervisor_health", mutation_forbidden)
        monkeypatch.setattr("cascade.watchdog.health._remediate_if_unchanged", mutation_forbidden)
        before = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tracking, check=True,
            capture_output=True, text=True,
        ).stdout

        observation = project_audit_observation("epic_001", root=product)

        after = subprocess.run(
            ["git", "status", "--porcelain"], cwd=tracking, check=True,
            capture_output=True, text=True,
        ).stdout
        assert observation.identity.document_revision.value == doc.sha
        assert observation.identity.git_head == GitHead(product_head)
        assert observation.evidence.tracking_repository == tracking.resolve()
        assert observation.evidence.product_repository == product.resolve()
        assert observation.classification == "healthy"
        assert before == after == ""
    finally:
        set_project_context(None)


def test_projection_classifies_unavailable_authoritative_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
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
