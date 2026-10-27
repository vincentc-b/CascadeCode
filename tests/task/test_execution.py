from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from cascade.task.execution import (
    execution_view,
    execution_views,
    execution_lease_is_live,
    heartbeat,
    mark_queued,
    mark_awaiting_merge,
    mark_merge_blocked,
    mark_running,
    mark_terminal,
    mark_validation_retry,
)
from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo


def test_execution_health_is_persisted_and_exposed_on_task_board(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001", status="active")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001", status="active")
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)

    queued = mark_queued("task_001", root=root, now=started)
    assert queued["attempt"] == 1
    assert execution_view("task_001", root=root, now=started)["health"] == "queued"
    assert execution_view(
        "task_001", root=root, now=started + timedelta(minutes=3)
    )["health"] == "stale"

    mark_running("task_001", root=root, now=started)
    assert execution_view("task_001", root=root, now=started + timedelta(seconds=30))["health"] == "healthy"
    assert execution_view("task_001", root=root, now=started + timedelta(minutes=3))["health"] == "stale"

    heartbeat("task_001", root=root, now=started + timedelta(minutes=3))
    assert execution_view("task_001", root=root, now=started + timedelta(minutes=3))["health"] == "healthy"

    payload = board_view_from_index(merged_board(root), root=root)
    item = payload["tasks"]["2_active"][0]
    assert item["execution"]["phase"] == "running"
    assert item["execution"]["health"] == "stale"  # the fixture timestamp is intentionally old

    recovery = item["recovery"]
    assert recovery["phase"] == "running"
    assert recovery["reason"] == "in_progress"
    assert recovery["attempt_count"] == 1
    assert isinstance(recovery["owner"], int)
    assert recovery["affected"] == {"branch": "task/task_001"}
    assert recovery["next_safe_step"] == "Wait for the original execution path to report progress."
    assert recovery["terminal_blocker"] == {"retryable": False}
    assert recovery["action"] == "none"

    mark_terminal("task_001", "failed", root=root, error="tests_red", now=started)
    failed = execution_view("task_001", root=root, now=started)
    assert failed["phase"] == "terminal"
    assert failed["health"] == "failed"
    assert failed["last_error"] == "tests_red"


def test_execution_views_reads_sidecar_once(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    mark_queued("task_001", root=root)
    mark_queued("task_002", root=root)

    import cascade.task.execution as execution

    calls = 0
    real_read = execution._read

    def counting_read(repo: Path):
        nonlocal calls
        calls += 1
        return real_read(repo)

    monkeypatch.setattr(execution, "_read", counting_read)
    views = execution_views({"task_001", "task_002"}, root=root)

    assert calls == 1
    assert views["task_001"]["health"] == "queued"
    assert views["task_002"]["health"] == "queued"


def test_merge_states_remain_actionable_after_heartbeat_expires(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001", status="active")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001", status="active")
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    mark_queued("task_001", root=root, now=started)
    mark_running("task_001", root=root, now=started)
    mark_awaiting_merge("task_001", root=root, now=started)
    awaiting = execution_view("task_001", root=root, now=started + timedelta(hours=1))
    assert awaiting["health"] == "awaiting_merge"
    assert awaiting["owner_pid"] is None

    kwargs = dict(
        root=root, reason="branch_conflict", conflict_paths=("cascade/workspace/worker.py",),
        source_sha="source1", target_sha="target1", now=started,
    )
    assert mark_merge_blocked("task_001", **kwargs)
    assert not mark_merge_blocked("task_001", **kwargs)
    blocked = execution_view("task_001", root=root, now=started + timedelta(hours=1))
    assert blocked["health"] == "merge_blocked"
    assert blocked["merge_blocker"]["conflict_paths"] == ["cascade/workspace/worker.py"]
    item = board_view_from_index(merged_board(root), root=root)["tasks"]["2_active"][0]
    assert item["execution"]["merge_blocker"] == blocked["merge_blocker"]

    mark_terminal("task_001", "succeeded", root=root)
    assert "merge_blocker" not in execution_view("task_001", root=root)


def test_new_queue_attempt_increments_and_clears_terminal_error(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    mark_queued("task_001", root=root)
    mark_terminal("task_001", "failed", root=root, error="boom")
    second = mark_queued("task_001", root=root)
    assert second["attempt"] == 2
    assert second["phase"] == "queued"
    assert second["last_error"] is None


def test_validation_failure_count_is_durable_and_reset_by_new_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    mark_queued("task_001", root=root)
    assert mark_validation_retry("task_001", "tests_not_run", root=root) == 1
    assert mark_validation_retry("task_001", "tests_red", root=root) == 2
    assert execution_view("task_001", root=root)["validation_failures"] == 2

    next_dispatch = mark_queued("task_001", root=root)
    assert next_dispatch["attempt"] == 2
    assert next_dispatch["validation_failures"] == 0


def test_running_lease_requires_fresh_heartbeat(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    started = datetime.now(timezone.utc)
    mark_queued("task_001", root=root, now=started)
    record = mark_running("task_001", root=root, now=started)
    assert record["owner_pid"] is not None
    assert execution_lease_is_live("task_001", root=root, now=started + timedelta(seconds=30))
    assert not execution_lease_is_live("task_001", root=root, now=started + timedelta(minutes=3))


def test_fresh_lease_fences_restart_even_when_owner_pid_is_dead(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    started = datetime.now(timezone.utc)
    mark_queued("task_001", root=root, now=started)
    mark_running("task_001", root=root, now=started)
    path = root / ".cascade" / "executions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["executions"]["task_001"]["owner_pid"] = 999_999_999
    payload["executions"]["task_001"]["owner_start_token"] = "dead-owner"
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert execution_lease_is_live("task_001", root=root, now=started + timedelta(seconds=30))
    assert not execution_lease_is_live("task_001", root=root, now=started + timedelta(minutes=3))
