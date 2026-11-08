from cascade.task.action_recovery import create_or_load_action, load_action
from cascade.task_rollup import retry_pending_task_merges, queue_task_merge
from tests.support import add_doc, make_repo


def test_completed_task_reconciles_historical_blocker_even_without_queue(tmp_path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
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
    original = create_or_load_action(
        "task_001:queued_merge",
        "queued_task_merge",
        root=root,
        attempt_bound=3,
        recovery_state="blocked",
        metadata={"task_id": "task_001"},
    )
    assert retry_pending_task_merges(root) == []
    action = load_action("task_001:queued_merge", root=root)
    assert action["recovery_state"] == "completed"
    assert action["attempts"] == original["attempts"]
    assert retry_pending_task_merges(root) == []
    assert load_action("task_001:queued_merge", root=root) == action


def test_derived_parent_not_active_refusal_remains_retryable(tmp_path, monkeypatch):
    from cascade.boss.merge import MergeResult

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    monkeypatch.setattr(
        "cascade.boss.merge.merge_task_branch",
        lambda *a, **k: MergeResult(ok=False, reason="not_active"),
    )
    queue_task_merge("task_001", root=root)
    assert retry_pending_task_merges(root) == []
    action = load_action("task_001:queued_merge", root=root)
    assert action["recovery_state"] == "retryable"
    assert action["failure_classification"] == "transient_retry"
