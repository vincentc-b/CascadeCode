"""Recovery admission releases global locks before boot and model execution."""

import subprocess
import sys
import threading

import pytest

from cascade.board.lock import process_lock
from cascade.feature.recovery import retry_task
from cascade.task.execution import execution_view
from cascade.watchdog.health import sweep_supervisor_health
from cascade.watchdog.hooks import register_boot_hook
from tests.watchdog.test_health import _active_feature_with_blocked_task


@pytest.mark.parametrize("entrypoint", ["retry", "health"])
def test_recovery_boot_and_model_release_lifecycle_and_sweep_locks(tmp_path, monkeypatch, entrypoint):
    root = _active_feature_with_blocked_task(tmp_path, monkeypatch)
    boot_read = threading.Event()
    model_entered = threading.Event()
    model_read = threading.Event()
    release_model = threading.Event()
    returned = threading.Event()
    errors = []
    calls = []

    def read_from_mcp():
        # An independent process must see queued state while the provider is
        # still running, as real MCP tools do. Timeout prevents test deadlock.
        result = subprocess.run(
            [sys.executable, "-c", """
import sys
from pathlib import Path
from cascade.feature.recovery import recovery_status
status = recovery_status('task_001', feature_id='feat_001', root=Path(sys.argv[1]))
assert status['phase'] == 'queued', status
""", str(root)], capture_output=True, text=True, timeout=5,
        )
        assert result.returncode == 0, result.stderr

    def boot(_work_id):
        def local_reader():
            with process_lock:
                assert execution_view("task_001", root=root)["phase"] == "queued"
                boot_read.set()

        reader = threading.Thread(target=local_reader, daemon=True)
        reader.start()
        assert boot_read.wait(2), "boot still holds the broad process lock"
        reader.join(2)
        read_from_mcp()

    def provider(reason, repo):
        calls.append(reason.work_id)
        model_entered.set()
        try:
            read_from_mcp()
            model_read.set()
            assert release_model.wait(10), "test did not release the model turn"
        except BaseException as exc:
            errors.append(exc)
        return True

    def invoke():
        try:
            if entrypoint == "retry":
                assert retry_task("task_001", feature_id="feat_001", root=root)["ok"]
            else:
                sweep_supervisor_health(root)
        except BaseException as exc:
            errors.append(exc)
        finally:
            returned.set()

    register_boot_hook("task", boot)
    monkeypatch.setattr("cascade.workspace.kickoff._kickoff_turn", provider)
    request = threading.Thread(target=invoke, daemon=True)
    request.start()
    try:
        assert model_entered.wait(8), errors
        assert model_read.wait(8), errors
        assert returned.wait(2), "recovery waited for the provider turn"
        assert not release_model.is_set()
        # Repeated recovery while the model is pending must not enqueue a
        # second dispatch or grant a second attempt.
        assert not retry_task("task_001", feature_id="feat_001", root=root)["ok"]
        assert calls == ["task_001"]
        assert not errors
    finally:
        release_model.set()
        request.join(8)


def test_retry_rechecks_direct_parent_at_dispatch_boundary(tmp_path, monkeypatch):
    from cascade.board.store import read_doc, write_doc
    from cascade.feature import recovery
    from tests.support import add_doc

    root = _active_feature_with_blocked_task(tmp_path, monkeypatch)
    add_doc(root, id="feat_002", title="Other owner", tier="feature", status="active", parent="epic_001")
    original = recovery.recovery_status
    raced = False

    def owner_changes(*args, **kwargs):
        nonlocal raced
        result = original(*args, **kwargs)
        if not raced:
            raced = True
            task = read_doc("task_001", root=root)
            task.meta.parent = "feat_002"
            write_doc(task, root=task.meta.path.parents[3])
        return result

    monkeypatch.setattr(recovery, "recovery_status", owner_changes)
    # Final status projection correctly refuses the old owner too; the key
    # assertion is that no transition happened under the stale authorization.
    with pytest.raises(ValueError, match="not a child"):
        retry_task("task_001", feature_id="feat_001", root=root)
    assert read_doc("task_001", root=root).meta.status == "blocked"
