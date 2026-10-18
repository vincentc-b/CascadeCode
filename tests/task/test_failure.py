"""Task failure policy: classify, retry budget, fail_task side effects."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import cascade.task.boot as task_boot
import cascade.task.failure as failure_mod
from cascade.agent.errors import CursorAgentError
from cascade.agent.types import RoleResult
from cascade.task.failure import classify_error, fail_task, maybe_retry
from cascade.task.registry import clear_task_tools, register_task_tool, task_tools
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks, invoke_boot, register_teardown_hook
from cascade.watchdog.types import Event
from tests.support import add_doc, make_repo

@pytest.fixture(autouse=True)
def _failure_test_isolation() -> None:
    clear_hooks()
    clear_task_tools()
    register_task_tool("fail_task", failure_mod.fail_task)
    task_boot._boot_root = None
    task_boot._last_fail_closed = None
    yield
    clear_hooks()
    clear_task_tools()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None


def test_infra_retry_budget(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert maybe_retry("task_001", "infra", 0, root=root) is True
    assert maybe_retry("task_001", "infra", 1, root=root) is True
    assert maybe_retry("task_001", "infra", 2, root=root) is False
    assert maybe_retry("task_001", "infra", 3, root=root) is False


def test_spec_never_retries(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    for attempt in (0, 1, 2, 5):
        assert maybe_retry("task_001", "spec", attempt, root=root) is False


def test_classify_uncertain_as_spec() -> None:
    assert classify_error({"exit_code": 1, "output": "FAILED tests"}) == "spec"
    assert classify_error(ValueError("bad spec")) == "spec"
    assert classify_error("unexpected string") == "spec"
    assert classify_error(None) == "spec"


def test_classify_infra_signals() -> None:
    assert classify_error({"kind": "infra"}) == "infra"
    assert classify_error(TimeoutError()) == "infra"
    assert classify_error(ConnectionError()) == "infra"


def test_classify_cursor_agent_startup_errors() -> None:
    assert classify_error(CursorAgentError("flake", retryable=True)) == "infra"
    assert classify_error(CursorAgentError("bad auth", retryable=False)) == "spec"


def test_classify_swe_run_error_result() -> None:
    assert classify_error(RoleResult(text="", status="error")) == "spec"
    assert classify_error(RoleResult(text="ok", status="finished")) == "spec"


def test_fail_task_queue_and_toast(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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

    fail_task("task_001", "tests_red", root=root)

    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload == {"task_id": "task_001", "reason": "tests_red"}

    toasts_raw, _ = read_events("war_room", 0, root=root)
    assert len(toasts_raw) == 1
    assert toasts_raw[0].type == "Toast"
    assert toasts_raw[0].payload["kind"] == "task_failed"
    assert toasts_raw[0].payload["id"] == "task_001"
    assert "tests_red" in toasts_raw[0].payload["message"]

    mapped = events_to_toasts(toasts_raw)
    assert mapped[0]["kind"] == "task_failed"
    assert "tests_red" in mapped[0]["body"]
    assert mapped[0]["link"] == "/api/doc/task_001"


def test_fail_task_already_blocked_skips_duplicate_events(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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
    fail_task("task_001", "first", root=root)
    events_after_first, offset = read_events("feat_001", 0, root=root)
    toasts_after_first, _ = read_events("war_room", 0, root=root)
    assert len([e for e in events_after_first if e.type == "TaskFailed"]) == 1
    assert len(toasts_after_first) == 1

    seen: list[str] = []

    def teardown(work_id: str) -> None:
        seen.append(work_id)

    register_teardown_hook("task", teardown)
    fail_task("task_001", "second", root=root)

    events_after_second, _ = read_events("feat_001", offset, root=root)
    toasts_after_second, _ = read_events("war_room", len(toasts_after_first), root=root)
    assert events_after_second == []
    assert toasts_after_second == []
    assert seen == ["task_001"]


def test_fail_task_blocked_stays_in_active(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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
    before = read_doc("task_001", root=root)

    fail_task("task_001", "spec_miss", root=root)

    after = read_doc("task_001", root=root)
    assert after.meta.status == "blocked"
    assert after.meta.path == before.meta.path
    assert after.meta.path.parent.name == "2_active"


def test_fail_task_invokes_teardown_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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
    seen: list[str] = []

    def teardown(work_id: str) -> None:
        seen.append(work_id)

    register_teardown_hook("task", teardown)
    fail_task("task_001", "cleanup", root=root)
    assert seen == ["task_001"]


def test_fail_task_does_not_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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
    with patch("cascade.watchdog.dispatch.dispatch_task") as mocked:
        fail_task("task_001", "no_redispatch", root=root)
    mocked.assert_not_called()


def test_fail_task_registered_on_task_tools() -> None:
    assert "fail_task" in task_tools()


def test_stale_parent_rev_via_fail_closed_boot(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
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
        title="Stale",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_001", "feat_001", root=root)
    stale_rev = read_doc("task_001", root=root).meta.parent_rev

    feature = read_doc("feat_001", root=root)
    feature.body = feature.body + "\nRevised.\n"
    write_doc(feature, root=root)

    from cascade.task.boot import install_task_boot_hook, last_fail_closed_boot

    install_task_boot_hook(root)
    invoke_boot("task", "task_001")

    assert last_fail_closed_boot() == ("task_001", "stale_parent_rev")
    events, _ = read_events("feat_001", 0, root=root)
    assert not any(e.type == "TaskActivated" for e in events)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "stale_parent_rev"
    assert read_doc("task_001", root=root).meta.status == "blocked"
