"""Execution and action writers share a cross-process transaction boundary."""

import subprocess
import sys

import pytest

from cascade.task.action_recovery import recovery_actions
from cascade.task.execution import execution_view
from tests.support import make_repo


def test_concurrent_execution_and_action_writers_preserve_both_histories(tmp_path):
    root = make_repo(tmp_path, git=False)
    program = """
from pathlib import Path
import sys
from cascade.task.execution import mark_queued
from cascade.task.action_recovery import create_or_load_action
root = Path(sys.argv[1])
worker = sys.argv[2]
for i in range(10):
    mark_queued("task_001", root=root)
    create_or_load_action(f"worker-{worker}-{i}", "test", root=root, attempt_bound=1)
"""
    children = [
        subprocess.Popen(
            [sys.executable, "-c", program, str(root), str(i)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for i in range(4)
    ]
    for child in children:
        stdout, stderr = child.communicate(timeout=30)
        assert child.returncode == 0, (stdout, stderr)
    execution = execution_view("task_001", root=root)
    assert execution["attempt"] == 40
    assert len(execution["attempt_history"]) == 39
    assert len(recovery_actions(root=root)) == 40


def _acquire_from_worktree(root, ready, acquired):
    from pathlib import Path
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    ready.set()
    with task_lifecycle_lock(root=Path(root)):
        acquired.set()


@pytest.mark.parametrize(
    "kind,work_id,branch",
    [
        ("task", "task_001_001_001", "task/task_001_001_001"),
        ("feature", "feat_001_001", "feat/feat_001_001"),
    ],
)
def test_worktree_and_trunk_contend_on_same_lifecycle_lock(
    tmp_path, kind, work_id, branch
):
    import multiprocessing
    from cascade.task.lifecycle_lock import task_lifecycle_lock
    from cascade.workspace.integration_worktree import create_integration_worktree

    root = make_repo(tmp_path)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Seed worktree fixture"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    checkout = create_integration_worktree(
        kind, work_id, branch=branch, base_ref="HEAD", trunk=root
    )
    context = multiprocessing.get_context("spawn")
    ready, acquired = context.Event(), context.Event()
    worker = context.Process(
        target=_acquire_from_worktree, args=(str(checkout.path), ready, acquired)
    )
    try:
        with task_lifecycle_lock(root=root):
            # Mixed-root nesting must also be reentrant on this thread.
            with task_lifecycle_lock(root=checkout.path):
                worker.start()
                assert ready.wait(10)
                assert not acquired.wait(0.2), (
                    "worktree bypassed the supervisor transaction lock"
                )
        assert acquired.wait(10)
        worker.join(10)
        assert worker.exitcode == 0
        assert not (checkout.path / ".cascade/task-lifecycle.lock").exists()
    finally:
        if worker.is_alive():
            worker.terminate()
            worker.join()


@pytest.mark.parametrize("split", [False, True])
def test_mixed_checkout_writers_share_execution_action_queue_and_ledger(
    tmp_path, split
):
    from cascade.task.lifecycle_lock import lifecycle_root
    from cascade.task.supervisor_recovery import _read_ledger
    from cascade.task_rollup import pending_task_merges
    from cascade.workspace.integration_worktree import create_integration_worktree
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext

    tracking = make_repo(tmp_path / "tracking")
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "Seed fixture"],
        cwd=tracking,
        check=True,
        capture_output=True,
    )
    owned = create_integration_worktree(
        "task", "task_001", branch="task/task_001", base_ref="HEAD", trunk=tracking
    )
    target = make_repo(tmp_path / "target") if split else tracking
    set_project_context(ProjectContext.split(target, tracking))
    program = """
from pathlib import Path
import sys
from cascade.board.context import set_project_context
from cascade.workspace.types import ProjectContext
from cascade.task.execution import mark_queued
from cascade.task.action_recovery import create_or_load_action
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.task.supervisor_recovery import _read_ledger, _write_ledger
from cascade.task_rollup import queue_task_merge
root, target, tracking = map(Path, sys.argv[1:4])
worker = sys.argv[4]
set_project_context(ProjectContext.split(target, tracking))
for index in range(3):
    mark_queued("task_001", root=root)
    create_or_load_action(f"writer-{worker}-{index}", "test", root=root, attempt_bound=1)
    with task_lifecycle_lock(root=root):
        ledger = _read_ledger(root)
        ledger[f"{worker}-{index}"] = {"state": "preserved"}
        _write_ledger(root, ledger)
    queue_task_merge(f"task_{int(worker) + 1:03d}", root=root)
"""
    processes = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                program,
                str(caller),
                str(target),
                str(tracking),
                str(index),
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for index, caller in enumerate((target, owned.path))
    ]
    for worker in processes:
        stdout, stderr = worker.communicate(timeout=30)
        assert worker.returncode == 0, (stdout, stderr)
    assert lifecycle_root(target) == lifecycle_root(owned.path) == tracking
    assert execution_view("task_001", root=tracking)["attempt"] == 6
    assert len(execution_view("task_001", root=owned.path)["attempt_history"]) == 5
    assert len(recovery_actions(root=tracking)) == 8  # six probes and two queue actions
    assert len(_read_ledger(target)) == 6
    assert pending_task_merges(target) == {"task_001", "task_002"}
    for name in (
        "executions.json",
        "orphan_delivery_recoveries.json",
        "pending-task-merges.json",
    ):
        assert (tracking / ".cascade" / name).is_file()
        assert not (owned.path / ".cascade" / name).exists()
        if split:
            assert not (target / ".cascade" / name).exists()
