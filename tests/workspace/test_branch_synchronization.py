"""Branch synchronization domain service (task_016_001_001)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from cascade.stacked_dispatch import read_feature_dispatch_selection
from cascade.board.parse import render_doc
from cascade.board.store import list_board, move_doc, read_doc
from cascade.epic.branch_recovery import retry_integration_branch_update
from cascade.task.action_recovery import load_action
from cascade.task.worktree import clear_task_runs
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.watchdog.events import read_events
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.workspace.branch_synchronization import (
    inspect_branch_synchronization,
    update_integration_branch,
)
from cascade.workspace.integration_worktree import create_integration_worktree, integration_branch, integration_worktree_path
from tests.support import add_doc, approve_board_feature, make_repo


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_task_runs()
    yield
    clear_task_runs()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _stacked_board(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok


def _commit_on_branch(repo: Path, branch: str, rel: str, content: str, message: str) -> None:
    subprocess.run(["git", "checkout", branch], cwd=repo, check=True, capture_output=True)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def test_feature_update_merges_epic_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_on_branch(epic_wt, "epic/epic_001", "epic.txt", "epic work\n", "on epic")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.ok
    assert inspection.state is not None
    assert inspection.state.behind > 0
    assert inspection.update_blocked_reason is None

    result = update_integration_branch("feat_001", root=root)
    assert result.ok
    assert result.reason is None
    assert result.no_op is False

    follow_up = inspect_branch_synchronization("feat_001", root=root)
    assert follow_up.ok and follow_up.state is not None
    assert follow_up.state.behind == 0


def test_already_current_is_no_op(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    result = update_integration_branch("feat_001", root=root)
    assert result.ok
    assert result.no_op is True


def test_completed_feature_can_receive_its_active_repair_before_rollup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from datetime import datetime, timezone

    from cascade.watchdog.events import append_event
    from cascade.watchdog.types import Event
    from cascade.workspace.branch_synchronization import (
        merge_lifecycle_source,
        preflight_lifecycle_merge_target,
    )

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active",
            parent="epic_001", children=["task_001"])
    add_doc(root, id="task_001", title="Repair", tier="task", status="active",
            parent="feat_001")
    feature = create_integration_worktree("feature", "feat_001", branch="feat/feat_001",
                                          base_ref="HEAD", trunk=root)
    task = create_integration_worktree("task", "task_001", branch="task/task_001",
                                       base_ref=feature.branch, trunk=root)
    (task.path / "repair.py").write_text("fixed = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "repair.py"], cwd=task.path, check=True)
    subprocess.run(["git", "commit", "-m", "Repair review snapshot"], cwd=task.path,
                   check=True, capture_output=True)
    monkeypatch.setattr("cascade.stacked_dispatch.refusal_if_feature_completion_without_pr",
                        lambda *args, **kwargs: None)
    move_doc("feat_001", "completed", root=feature.path)
    move_doc("feat_001", "completed", root=root)

    assert not preflight_lifecycle_merge_target("feat_001", root=root).ok
    assert preflight_lifecycle_merge_target(
        "feat_001", source_work_id="task_001", root=root
    ).ok
    merged = merge_lifecycle_source("feat_001", "task/task_001",
                                    source_work_id="task_001", root=root)
    assert merged.ok
    assert (feature.path / "repair.py").read_text() == "fixed = True\n"

    append_event("epic_001", Event(type="FeatureCompleted", ts=datetime.now(timezone.utc),
                                   payload={"feature_id": "feat_001"}, dest="epic_001"), root=root)
    assert preflight_lifecycle_merge_target(
        "feat_001", source_work_id="task_001", root=root
    ).reason == "not_active"


def test_epic_update_keeps_live_spec_over_managed_trunk_pointer(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")

    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    inspection = inspect_branch_synchronization("epic_001", root=root)
    assert inspection.ok and inspection.state is not None
    assert inspection.state.behind > 0

    result = update_integration_branch("epic_001", root=root)

    assert result.ok
    assert result.reason is None
    live = (epic_wt / "docs/epics/2_active/epic_001_epic.md").read_text(
        encoding="utf-8"
    )
    assert "integration_worktree:" not in live
    assert "Live epic spec is on branch" not in live
    follow_up = inspect_branch_synchronization("epic_001", root=root)
    assert follow_up.ok and follow_up.state is not None
    assert follow_up.state.behind == 0


def test_epic_update_drops_stale_pointer_when_base_completes_another_epic(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="First", tier="epic", status="ready_to_plan")
    add_doc(root, id="epic_002", title="Second", tier="epic", status="ready_to_plan")
    assert activate_epic("epic_001", "human", root=root).ok
    assert activate_epic("epic_002", "human", root=root).ok
    # First sync the new Epic's own managed pointer, as normal activation does.
    assert update_integration_branch("epic_002", root=root).ok

    second = integration_worktree_path("epic", "epic_002", trunk=root)
    active_rel = "docs/epics/2_active/epic_001_first.md"
    completed_rel = "docs/epics/3_completed/epic_001_first.md"
    assert (second / active_rel).is_file()

    first = integration_worktree_path("epic", "epic_001", trunk=root)
    completed = read_doc("epic_001", root=first)
    completed.meta.status = "completed"
    completed.meta.path = root / completed_rel
    completed.body += "\n" + ("Completed implementation detail unique to this plan.\n" * 100)
    completed.meta.path.parent.mkdir(parents=True, exist_ok=True)
    completed.meta.path.write_text(render_doc(completed), encoding="utf-8")
    subprocess.run(["git", "rm", "--", active_rel], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "add", "--", completed_rel], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "complete first epic", "--", active_rel, completed_rel],
        cwd=root, check=True, capture_output=True,
    )

    result = update_integration_branch("epic_002", root=root)
    assert result.ok
    assert not (second / active_rel).exists()
    assert list_board(second).by_id["epic_001"].status == "completed"
    assert read_doc("epic_002", root=second).meta.status == "active"
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=second, check=True,
        capture_output=True, text=True,
    ).stdout == ""


def _seed_predecessor_review(root: Path, feature_id: str) -> None:
    path = root / ".cascade" / "reviews.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    state: dict[str, object] = {}
    if path.is_file():
        state = json.loads(path.read_text(encoding="utf-8"))
    state[feature_id] = {
        "url": f"https://github.example/o/r/pull/{feature_id}",
        "number": "1",
        "forge": "github",
        "source_branch": integration_branch("feature", feature_id),
        "target_branch": integration_branch("epic", "epic_001"),
        "draft": False,
        "closed": False,
    }
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def test_persisted_feature_base_survives_room_settings_change(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature A", tier="feature", parent="epic_001")
    assert activate_epic("epic_001", "human", root=root).ok
    write_stacked_pr_enabled("epic_001", True, root=root)
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    from cascade.board.store import move_doc

    move_doc("feat_001", "completed", root=root)
    add_doc(
        root,
        id="feat_002",
        title="Feature B",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    _seed_predecessor_review(root, "feat_001")
    approve_board_feature(root, "feat_002")
    assert dispatch_feature("feat_002", "human", root=root).ok

    write_stacked_pr_enabled("epic_001", False, root=root)

    selection = read_feature_dispatch_selection("feat_002", root=root)
    assert selection is not None
    assert selection.base_branch == integration_branch("feature", "feat_001")

    inspection = inspect_branch_synchronization("feat_002", root=root)
    assert inspection.ok and inspection.state is not None
    assert inspection.state.base_branch == integration_branch("feature", "feat_001")


def test_dirty_index_blocks_update(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    (feat_wt / "dirty.txt").write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "dirty.txt"], cwd=feat_wt, check=True, capture_output=True)

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason == "dirty_index"
    result = update_integration_branch("feat_001", root=root)
    assert not result.ok and result.reason == "dirty_index"
    action = load_action("feat_001:integration_branch_update", root=root)
    assert action is not None
    assert action["recovery"]["owning_team"] == {
        "kind": "epic_team",
        "work_id": "epic_001",
    }
    events, _ = read_events("epic_001", 0, root=root)
    assert [event.type for event in events].count("BranchActionRecoveryRequested") == 1

    assert not update_integration_branch("feat_001", root=root).ok
    events, _ = read_events("epic_001", 0, root=root)
    assert [event.type for event in events].count("BranchActionRecoveryRequested") == 1


def test_untracked_reports_local_changes(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    (feat_wt / "scratch.txt").write_text("untracked\n", encoding="utf-8")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason == "local_changes"


def test_untracked_managed_runtime_sidecar_does_not_block_update(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    sidecar = feat_wt / "docs/_war_room/chat/feat_001.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text('{"author":"system"}\n', encoding="utf-8")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason is None


def test_untracked_comment_sidecar_does_not_block_update(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    sidecar = feat_wt / "docs/_comments/feat_001.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text('{"author":"human"}\n', encoding="utf-8")

    inspection = inspect_branch_synchronization("feat_001", root=root)
    assert inspection.update_blocked_reason is None


def test_conflict_aborts_and_restores_head(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    rel = "conflict.txt"
    _commit_on_branch(epic_wt, "epic/epic_001", rel, "base side\n", "epic change")
    _commit_on_branch(feat_wt, "feat/feat_001", rel, "work side\n", "feature change")

    pre = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    result = update_integration_branch("feat_001", root=root)
    assert not result.ok
    assert result.reason == "branch_conflict"
    assert result.conflict_paths == (rel,)

    post = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert post == pre
    merge_head = subprocess.run(
        ["git", "rev-parse", "-q", "MERGE_HEAD"],
        cwd=feat_wt,
        capture_output=True,
    )
    assert merge_head.returncode != 0


def test_epic_team_can_retry_owned_branch_update_and_complete_incident(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    assert activate_epic("epic_001", "human", root=root).ok
    assert update_integration_branch("epic_001", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)

    _commit_on_branch(
        epic_wt, "epic/epic_001", "conflict.txt", "epic side\n", "epic change"
    )
    _commit_on_branch(root, "main", "conflict.txt", "trunk side\n", "trunk change")

    failed = update_integration_branch("epic_001", root=root)
    assert not failed.ok and failed.reason == "branch_conflict"
    action_id = "epic_001:integration_branch_update"
    action = load_action(action_id, root=root)
    assert action is not None
    assert action["recovery_state"] == "awaiting_owner_decision"

    merge = subprocess.run(
        ["git", "merge", "main", "--no-edit"],
        cwd=epic_wt,
        check=False,
        capture_output=True,
    )
    assert merge.returncode != 0
    (epic_wt / "conflict.txt").write_text("resolved\n", encoding="utf-8")
    subprocess.run(["git", "add", "conflict.txt"], cwd=epic_wt, check=True)
    subprocess.run(
        ["git", "commit", "-m", "resolve owned branch update"],
        cwd=epic_wt,
        check=True,
        capture_output=True,
    )
    move_doc("epic_001", "completed", root=epic_wt)
    assert inspect_branch_synchronization("epic_001", root=root).reason == "not_active"

    completed = retry_integration_branch_update(
        action_id, epic_id="epic_001", root=root
    )
    assert completed["recovery_state"] == "completed"
    assert completed["attempt_count"] == 1
    recovered_inspection = inspect_branch_synchronization(
        "epic_001", root=root, allow_completed_recovery=True
    )
    assert recovered_inspection.state is not None
    assert recovered_inspection.state.behind == 0

    assert retry_integration_branch_update(
        action_id, epic_id="epic_001", root=root
    ) == completed
    with pytest.raises(PermissionError, match="different team"):
        retry_integration_branch_update(action_id, epic_id="epic_999", root=root)


def test_task_update_uses_parent_feature_base(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_on_branch(feat_wt, "feat/feat_001", "feature.txt", "feature\n", "feature work")

    inspection = inspect_branch_synchronization("task_001", root=root)
    assert inspection.ok and inspection.state is not None
    assert inspection.state.base_branch == integration_branch("feature", "feat_001")
    assert inspection.state.behind > 0

    assert update_integration_branch("task_001", root=root).ok
