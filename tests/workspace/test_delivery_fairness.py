"""Real delivery must get a safe turn between consecutive parent model turns."""

import subprocess
from datetime import datetime, timezone

from cascade.board.store import read_doc
from cascade.task.action_recovery import capture_and_route_action_failure, load_action
from cascade.task_rollup import queue_task_merge, retry_pending_task_merges
from cascade.team_branch_recovery import retry_team_integration_branch_update
from cascade.workspace.integration_worktree import create_integration_worktree
from tests.support import add_doc, make_repo


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True).stdout.strip()


def test_owner_can_acknowledge_repaired_branch_during_its_own_turn(tmp_path, monkeypatch):
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    epic = create_integration_worktree("epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=root)
    action_id = "epic_001:integration_branch_update"
    capture_and_route_action_failure(action_id, "integration_branch_update", affected_work_id="epic_001",
        intended_target_ref="main", root=root, failure_code="branch_conflict", safe_summary="Resolve owned conflict")
    monkeypatch.setattr("cascade.workspace.branch_synchronization._graph_has_inflight_turn", lambda *a, **k: True)
    before = git(epic.path, "rev-parse", "HEAD")
    result = retry_team_integration_branch_update(action_id, team_kind="epic_team", team_id="epic_001", root=root)
    assert result["recovery_state"] == "completed"
    assert git(epic.path, "rev-parse", "HEAD") == before
    assert retry_team_integration_branch_update(action_id, team_kind="epic_team", team_id="epic_001", root=root) == result

    from cascade.workspace.branch_synchronization import update_integration_branch
    (epic.path / "unfinished.py").write_text("unfinished\n")
    assert update_integration_branch("epic_001", root=root).reason == "local_changes"
    (epic.path / "unfinished.py").unlink()
    (root / "new.py").write_text("new base\n")
    git(root, "add", "new.py")
    git(root, "commit", "-m", "base advances")
    assert update_integration_branch("epic_001", root=root).reason == "busy"


def test_validated_delivery_precedes_next_parent_queue_turn(tmp_path, monkeypatch):
    import cascade.workspace.kickoff as kickoff
    from cascade.watchdog.events import append_event
    from cascade.watchdog.types import Event
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", status="active", parent="feat_001")
    add_doc(root, id="feat_002", title="Sibling", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_002", title="Sibling Task", tier="task", status="active", parent="feat_002")
    feature = create_integration_worktree("feature", "feat_001", branch="feat/feat_001", base_ref="HEAD", trunk=root)
    task = create_integration_worktree("task", "task_001", branch="task/task_001", base_ref=feature.branch, trunk=root)
    (task.path / "delivery.py").write_text("VALUE = 1\n")
    git(task.path, "add", "delivery.py")
    git(task.path, "commit", "-m", "validated Task", "-m", "Cascade-Task: task_001")
    queue_task_merge("task_001", root=root, delivery_evidence={"task_id":"task_001",
        "deliverable_sha":git(task.path,"rev-parse","HEAD"), "feature_base_sha":git(feature.path,"rev-parse","HEAD")})
    queue_task_merge("task_002", root=root)
    busy = True
    monkeypatch.setattr(kickoff, "_graph_has_inflight_turn", lambda *a, **k: busy)
    monkeypatch.setattr("cascade.workspace.branch_synchronization._graph_has_inflight_turn", lambda *a, **k: busy)
    for _ in range(3):
        assert retry_pending_task_merges(root) == []
    assert load_action("task_001:queued_merge", root=root)["attempt_count"] == 0

    busy = False
    append_event("feat_001", Event("TeamMessage", datetime.now(timezone.utc), {"body":"Continue planning"}, "feat_001"), root=root)
    turns = []
    def model_turn(reason):
        repo = reason.root
        assert read_doc("task_001", root=repo).meta.status == "completed"
        assert (feature.path / "delivery.py").read_text() == "VALUE = 1\n"
        turns.append(reason.work_id)
    monkeypatch.setattr(kickoff, "kickoff_turn", model_turn)
    kickoff._run_queue_delivery("feat_001", "feature", root, None)
    assert turns == ["feat_001"]
    action = load_action("task_001:queued_merge", root=root)
    assert action["recovery_state"] == "completed"
    assert action["attempt_count"] == 1
    assert load_action("task_002:queued_merge", root=root)["attempt_count"] == 0
