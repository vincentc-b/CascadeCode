"""Execution and action writers share a cross-process transaction boundary."""

import subprocess
import sys

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
