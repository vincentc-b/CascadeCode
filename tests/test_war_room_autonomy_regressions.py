"""Liveness regressions from the war-room autonomy investigation.

Use real Git/worktree and durable execution records; no provider processes run.
"""

from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from cascade.board import move_doc, read_doc
from cascade.board.store import list_board
from cascade.task import execution
from cascade.task.git_tools import swe_run_tests
from cascade.task.worktree import TaskRun
from cascade.watchdog.events import (
    append_event,
    prune_completed_work_queues,
    read_events,
)
from cascade.watchdog.loop import _authorized
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import create_integration_worktree
from tests.support import add_doc, make_repo


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    "phase,expected",
    [
        ("awaiting_merge", 0),
        ("merge_blocked", 0),
        ("terminal", 0),
        ("queued", 1),
        ("running", 1),
        ("unrecorded", 1),
    ],
)
def test_delivery_wait_does_not_consume_execution_capacity(
    tmp_path: Path, phase: str, expected: int
) -> None:
    from cascade.watchdog.dispatch import _active_task_count

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    task_id = "task_001_001_001"
    add_doc(
        root,
        id=task_id,
        title="Owned task",
        tier="task",
        status="active",
        parent="feat_001_001",
    )
    if phase != "unrecorded":
        execution.mark_queued(task_id, root=root)
    if phase == "running":
        execution.mark_running(task_id, root=root)
    elif phase == "awaiting_merge":
        execution.mark_awaiting_merge(task_id, root=root)
    elif phase == "merge_blocked":
        execution.mark_merge_blocked(
            task_id,
            root=root,
            reason="branch_conflict",
            conflict_paths=("app.py",),
            source_sha="a",
            target_sha="b",
        )
    elif phase == "terminal":
        execution.mark_terminal(task_id, "failed", root=root, error="scope_blocked")
    assert _active_task_count(list_board(root), root=root) == expected


def test_validation_cannot_certify_feature_changes_absent_from_tested_tree(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    feature_id, task_id = "feat_001_001", "task_001_001_001"
    add_doc(
        root,
        id=feature_id,
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root, id=task_id, title="Task", tier="task", status="active", parent=feature_id
    )
    feature = create_integration_worktree(
        "feature", feature_id, branch=f"feat/{feature_id}", base_ref="HEAD", trunk=root
    )
    task = create_integration_worktree(
        "task", task_id, branch=f"task/{task_id}", base_ref=feature.branch, trunk=root
    )
    run = TaskRun(
        task_id=task_id,
        branch=task.branch,
        worktree=task.path,
        base_sha=task.base_sha,
        parent_rev=None,
        skills=[],
    )
    (task.path / "test_local.py").write_text("def test_local():\n    assert True\n")
    (task.path / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    _git(task.path, "add", "-A")
    _git(task.path, "commit", "-m", "Task implementation")
    (feature.path / "feature_change.txt").write_text(
        "Feature moved after the task started\n"
    )
    _git(feature.path, "add", "feature_change.txt")
    _git(feature.path, "commit", "-m", "Advance Feature")
    assert not (task.path / "feature_change.txt").exists()

    from cascade.task.git_tools import _validation_target

    assert _validation_target(task_id, run, root=root) is None
    # Supervised validation first integrates the actual current Feature tree.
    result = swe_run_tests(
        task_id=task_id,
        task_run=run,
        root=root,
        cmd=["python3", "-m", "pytest", "-q", "test_local.py"],
    )
    assert result["exit_code"] == 0
    assert (task.path / "feature_change.txt").is_file()
    feature_head = _git(feature.path, "rev-parse", "HEAD")
    _git(task.path, "merge-base", "--is-ancestor", feature_head, "HEAD")
    assert result["final_validation"]["feature_base_sha"] == feature_head
    assert result["final_validation"]["deliverable_sha"] == _git(
        task.path, "rev-parse", "HEAD"
    )


@pytest.mark.parametrize("feature_id", ["feat_038_003", "feat_039_001", "feat_039_003"])
def test_local_completion_does_not_revoke_parent_copy_dispatch_authority(
    tmp_path: Path, feature_id: str
) -> None:
    root = make_repo(tmp_path)
    epic_id = "epic_" + feature_id.split("_")[1]
    add_doc(root, id=epic_id, title="Epic", tier="epic", status="active")
    parent_copy = add_doc(
        root,
        id=feature_id,
        title="Feature",
        tier="feature",
        status="active",
        parent=epic_id,
    )
    append_event(
        feature_id,
        Event(
            type="FeatureReadyToPlan",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id, "by": "human"},
            dest=feature_id,
        ),
        root=root,
    )
    assert _authorized(root, parent_copy.meta)
    feature = create_integration_worktree(
        "feature", feature_id, branch=f"feat/{feature_id}", base_ref="HEAD", trunk=root
    )
    # Local completion is published before the forge-review record exists.
    move_doc(feature_id, "completed", root=feature.path)
    assert read_doc(feature_id, root=feature.path).meta.status == "completed"
    # Consume the dispatch event, then exercise ordinary periodic pruning.
    events, offset = read_events(feature_id, 0, root=root)
    assert events and offset > 0
    assert read_events(feature_id, offset, root=root)[0] == []
    prune_completed_work_queues(root=root)
    assert _authorized(root, parent_copy.meta), (
        "local completion must not make the legitimate active parent copy illegal"
    )
    assert _authorized(root, parent_copy.meta), (
        "authorization must survive repeated scans/restarts"
    )


def test_registered_worktree_alone_does_not_authorize_illegal_active_move(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_099", title="Epic", tier="epic", status="active")
    feature_id = "feat_099_001"
    doc = add_doc(
        root,
        id=feature_id,
        title="Undispatched feature",
        tier="feature",
        status="active",
        parent="epic_099",
    )
    create_integration_worktree(
        "feature", feature_id, branch=f"feat/{feature_id}", base_ref="HEAD", trunk=root
    )
    assert not _authorized(root, doc.meta)
