from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

from cascade.task.execution import (
    execution_view,
    execution_lease_is_live,
    heartbeat,
    mark_queued,
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

    mark_terminal("task_001", "failed", root=root, error="tests_red", now=started)
    failed = execution_view("task_001", root=root, now=started)
    assert failed["phase"] == "terminal"
    assert failed["health"] == "failed"
    assert failed["last_error"] == "tests_red"


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
