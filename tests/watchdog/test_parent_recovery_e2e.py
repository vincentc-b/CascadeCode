"""Isolated-repository acceptance for registered parent recovery."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.store import read_doc, write_doc
from cascade.task.action_recovery import recovery_actions
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.watchdog.audit import project_audit_observation
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import load_registry
from cascade.workspace.kickoff import (
    kickoff_graph_queue_event,
    wait_for_background_kickoffs,
)
from tests.support import add_doc, commit_board, make_repo, run_audit_recovery_entry


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _commit_pending(root: Path, message: str) -> None:
    if _git(root, "status", "--porcelain", "--untracked-files=all"):
        _git(root, "add", "-A")
        _git(root, "commit", "-m", message)


def _prime_parent_incident(root: Path, work_id: str, action: str):
    """Start the no-progress interval; the public audit entry proves it later."""

    first = project_audit_observation(work_id, root=root, monotonic=lambda: 0.0)
    assert first.classification == "expected_wait"
    assert first.reason.startswith("observing:")
    assert first.evidence.parent_action is not None
    assert first.evidence.parent_action.candidate_action == action
    return first


def _successful_reservation(root: Path, work_id: str, capability: str):
    rows = [
        row
        for row in recovery_actions(root=root)
        if row.get("action_kind") == "health_auditor_reservation"
        and row.get("incident", {}).get("work_id") == work_id
        and row.get("incident", {}).get("selected_capability") == capability
    ]
    successful = [row for row in rows if row["incident"]["outcome"] == "success"]
    assert len(successful) == 1
    incident = successful[0]["incident"]
    assert incident["request"]["claim_token"]
    assert incident["acknowledgement"] == {
        "accepted": True,
        "worker": "health-audit-recovery",
    }
    adapter_result = incident["result"]["adapter_result"]
    assert adapter_result.get("durable_result") is True or (
        adapter_result.get("ok") is True
        and adapter_result.get("state") == "reconciled"
    )
    assert len(incident["attempts"]) == 1
    return incident


def _manually_land_owned_branch(root: Path, branch: str) -> None:
    merge = subprocess.run(
        ["git", "merge", "--no-ff", "--no-commit", branch],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if merge.returncode:
        conflicts = _git(root, "diff", "--name-only", "--diff-filter=U").splitlines()
        assert conflicts
        _git(root, "checkout", "--theirs", "--", *conflicts)
        _git(root, "add", "--", *conflicts)
    _git(root, "commit", "-m", "land owned epic branch after manual review")


def test_registered_feature_and_epic_recovery_publish_and_finish_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Cross the real registry, reservations, owned Git branches and rollups."""

    root = make_repo(tmp_path, role_skills=True)
    monkeypatch.setenv("CASCADE_ENABLE_FAKE_PROVIDER", "1")
    (root / "cascade.toml").write_text(
        '[providers]\ndefault = "fake"\n\n'
        '[providers.fake]\nepic = "fast"\nfeature = "fast"\ntask = "fast"\n',
        encoding="utf-8",
    )
    # Provider discovery is outside this acceptance boundary. The lifecycle
    # mutations, Git publication and recovery adapters below remain real.
    monkeypatch.setattr(
        "cascade.watchdog.dispatch._provider_preflight_refusal",
        lambda *_args, **_kwargs: None,
    )
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="ready_to_plan",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    commit_board(root, "acceptance board")
    assert activate_epic("epic_001", "human", root=root).ok
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert wait_for_background_kickoffs(5)

    feature_entry = next(
        row for row in load_registry(root)
        if row.kind == "feature" and row.work_id == "feat_001"
    )
    epic_entry = next(
        row for row in load_registry(root)
        if row.kind == "epic" and row.work_id == "epic_001"
    )
    epic = read_doc("epic_001", root=epic_entry.path)
    epic.meta.plan_approved_at = datetime.now(timezone.utc)
    write_doc(epic, root=epic_entry.path)
    _commit_pending(epic_entry.path, "record epic owner input")
    _commit_pending(feature_entry.path, "record feature owner input")
    feature_head = _git(feature_entry.path, "rev-parse", "HEAD")

    feature_observation = _prime_parent_incident(
        root, "feat_001", "reconcile_completion_rollup"
    )
    assert "feat_001" in run_audit_recovery_entry(root).incident_work_ids
    feature_receipt = _successful_reservation(
        root, "feat_001", "reconcile_completion_rollup"
    )
    assert feature_receipt["authoritative_generation"] == str(
        feature_observation.generation
    )
    assert feature_receipt["evidence"]["parent_action"][
        "candidate_action"
    ] == "reconcile_completion_rollup"
    assert _git(root, "merge-base", "--is-ancestor", feature_head, "epic/epic_001") == ""
    assert not feature_entry.path.exists()
    feature_events, _ = read_events("epic_001", 0, root=root)
    assert len(
        [event for event in feature_events if event.type == "FeatureCompleted"]
    ) == 1

    assert kickoff_graph_queue_event("epic_001", root=root)
    assert wait_for_background_kickoffs(5)
    _commit_pending(epic_entry.path, "acknowledge feature completion")
    epic_head = _git(epic_entry.path, "rev-parse", "HEAD")
    epic_observation = _prime_parent_incident(
        root, "epic_001", "reconcile_completion_rollup"
    )
    assert "epic_001" in run_audit_recovery_entry(root).incident_work_ids
    deferred = [
        row["incident"]
        for row in recovery_actions(root=root)
        if row.get("action_kind") == "health_auditor_reservation"
        and row.get("incident", {}).get("work_id") == "epic_001"
    ]
    assert len(deferred) == 1
    assert deferred[0]["outcome"] == "deferred"
    assert deferred[0]["result"]["adapter_result"]["reason"] == "branch_conflict"
    assert deferred[0]["accountable_owner"] == "epic_team:epic_001"

    _manually_land_owned_branch(root, "epic/epic_001")
    epic_observation = _prime_parent_incident(
        root, "epic_001", "reconcile_completion_rollup"
    )
    assert "epic_001" in run_audit_recovery_entry(root).incident_work_ids
    epic_receipt = _successful_reservation(
        root, "epic_001", "reconcile_completion_rollup"
    )
    assert epic_receipt["authoritative_generation"] == str(epic_observation.generation)
    assert epic_receipt["evidence"]["parent_action"][
        "candidate_action"
    ] == "reconcile_completion_rollup"
    assert _git(root, "merge-base", "--is-ancestor", epic_head, "main") == ""
    assert read_doc("epic_001", root=root).meta.status == "completed"
    assert not epic_entry.path.exists()

    war_events, _ = read_events("war_room", 0, root=root)
    assert len([event for event in war_events if event.type == "EpicCompleted"]) == 1

    # A restarted worker sees terminal state and the durable successful claim;
    # neither adapter, publication, event nor cleanup can run a second time.
    terminal = run_audit_recovery_entry(root)
    assert "feat_001" not in terminal.incident_work_ids
    assert "epic_001" not in terminal.incident_work_ids
    assert len(
        [event for event in read_events("epic_001", 0, root=root)[0]
         if event.type == "FeatureCompleted"]
    ) == 1
    assert len(
        [event for event in read_events("war_room", 0, root=root)[0]
         if event.type == "EpicCompleted"]
    ) == 1
    assert all(
        row.work_id not in {"feat_001", "epic_001"}
        for row in load_registry(root)
    )
