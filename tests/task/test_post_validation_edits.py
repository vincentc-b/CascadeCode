"""A green commit cannot finalize or destroy later work in its checkout."""

import pytest

from cascade.board.store import read_doc
from cascade.task import invoke_tool
from cascade.task.action_recovery import load_action
from cascade.task.execution import execution_view
from cascade.task.graph import _auto_merge_finished_task
from cascade.task.worktree import (
    get_task_run, install_task_worktree_teardown_hook, remove_task_worktree,
)
from cascade.task_rollup import (
    delivery_evidence_is_current, pending_task_merges, retry_pending_task_merges,
)
from cascade.watchdog.events import read_events
from tests.task.test_delivery_blocker_validation import _delivery, _git
from tests.task.test_delivery_blocker_validation import _isolate_runs as _isolate_runs


def _validate(root):
    result = invoke_tool("task_001", "swe_run_tests",
                         {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                         root=root, feature_id="feat_001")
    assert result["exit_code"] == 0
    return result["final_validation"]


@pytest.mark.parametrize("entry", ["finalizer", "queue"])
@pytest.mark.parametrize("edit", ["tool", "native", "staged", "untracked"])
def test_later_edits_preserved_then_same_task_revalidated_and_merged(tmp_path, entry, edit):
    root, feature, task = _delivery(tmp_path)
    install_task_worktree_teardown_hook(root)
    evidence = _validate(root)
    before = _git(feature.path, "rev-parse", "HEAD")
    path = task.path / ("later.py" if edit == "untracked" else "implementation.py")
    content = "value = 42  # later correction must be committed and tested\n"
    if edit == "tool":
        invoke_tool("task_001", "swe_write", {"path": path.name, "content": content},
                    root=root, feature_id="feat_001")
        assert "task_001" not in pending_task_merges(root)
    else:
        path.write_text(content)
        if edit == "staged":
            _git(task.path, "add", path.name)
    assert not delivery_evidence_is_current("task_001", evidence, root=root)
    if entry == "finalizer" or edit == "tool":
        _auto_merge_finished_task("task_001", root)
    else:
        assert retry_pending_task_merges(root) == []
    assert read_doc("task_001", root=root).meta.status == "active"
    assert path.read_text() == content
    assert _git(feature.path, "rev-parse", "HEAD") == before
    assert "task_001" not in pending_task_merges(root)
    execution = execution_view("task_001", root=root)
    assert execution["phase"] == "queued"
    assert execution["attempt"] == 1
    assert execution["validation_failures"] == 0
    assert load_action("task_001:queued_merge", root=root)["attempt_count"] == 0
    _auto_merge_finished_task("task_001", root)
    events, _ = read_events("task_001", 0, root=root)
    assert sum(event.type == "TaskValidationRetryRequested" for event in events) == 1

    # Repair the same Task through the real commit/test/merge boundaries.
    _git(task.path, "add", path.name)
    _git(task.path, "commit", "-m", "Finish later correction\n\nCascade-Task: task_001")
    assert _git(task.path, "status", "--porcelain") == ""
    replacement = _validate(root)
    assert replacement["deliverable_sha"] != evidence["deliverable_sha"]
    _auto_merge_finished_task("task_001", root)
    assert read_doc("task_001", root=root).meta.status == "completed"
    assert (feature.path / path.name).read_text() == content
    assert not task.path.exists()
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TaskMerged" for event in events) == 1


def test_direct_merge_and_teardown_preserve_dirty_source(tmp_path):
    from cascade.boss.merge import merge_task_branch
    root, feature, task = _delivery(tmp_path)
    _validate(root)
    path = task.path / "later.py"
    path.write_text("valuable = True\n")
    before = _git(feature.path, "rev-parse", "HEAD")
    result = merge_task_branch("task_001", root=root)
    assert not result.ok and result.reason == "source_dirty"
    assert _git(feature.path, "rev-parse", "HEAD") == before
    run = get_task_run("task_001")
    run.state = "merged"  # Even an erroneous caller cannot authorize data loss.
    remove_task_worktree(run, root=root)
    assert path.read_text() == "valuable = True\n"
    assert get_task_run("task_001") is run


@pytest.mark.parametrize("messages", [[], [{"role": "task_swe", "content": "prior turn"}]])
def test_real_pending_task_checkpoint_fences_delivery(tmp_path, messages):
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph
    from cascade.workspace.kickoff import _graph_has_inflight_turn
    root, feature, task = _delivery(tmp_path)
    _validate(root)
    before = _git(feature.path, "rev-parse", "HEAD")
    graph = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    graph.update_state(thread_config("task_001"),
                       {"task_id": "task_001", "feature_id": "feat_001", "messages": messages},
                       as_node="ingest")
    assert graph.get_state(thread_config("task_001")).next == ("task_swe",)
    assert _graph_has_inflight_turn("task_001", "task", root=root, feature_id="feat_001")
    assert retry_pending_task_merges(root) == []
    assert "task_001" in pending_task_merges(root)
    assert load_action("task_001:queued_merge", root=root)["attempt_count"] == 0
    assert _git(feature.path, "rev-parse", "HEAD") == before
    graph.update_state(thread_config("task_001"), {}, as_node="task_swe")
    assert not _graph_has_inflight_turn("task_001", "task", root=root, feature_id="feat_001")
    assert retry_pending_task_merges(root) == ["task_001"]
    assert read_doc("task_001", root=root).meta.status == "completed"


def test_write_arriving_after_queue_preflight_returns_to_same_task(tmp_path, monkeypatch):
    from cascade.boss import merge
    root, feature, task = _delivery(tmp_path)
    _validate(root)
    original = merge.merge_task_branch

    def write_before_locked_merge(task_id, *, root):
        (task.path / "later.py").write_text("valuable = True\n")
        return original(task_id, root=root)

    monkeypatch.setattr(merge, "merge_task_branch", write_before_locked_merge)
    assert retry_pending_task_merges(root) == []
    assert read_doc("task_001", root=root).meta.status == "active"
    assert (task.path / "later.py").read_text() == "valuable = True\n"
    assert execution_view("task_001", root=root)["phase"] == "queued"
    assert load_action("task_001:queued_merge", root=root)["recovery_state"] == "retryable"
    assert "task_001" not in pending_task_merges(root)


def test_dirty_source_check_from_owned_checkout_without_process_cache(tmp_path):
    from cascade.task.worktree import clear_task_runs, task_worktree_has_changes
    root, feature, task = _delivery(tmp_path)
    (task.path / "later.py").write_text("valuable = True\n")
    clear_task_runs()
    assert task_worktree_has_changes("task_001", root=root)
    assert task_worktree_has_changes("task_001", root=task.path)
    assert task_worktree_has_changes("task_001", root=feature.path)
    assert not (task.path / ".cascade/worktrees.lock").exists()
