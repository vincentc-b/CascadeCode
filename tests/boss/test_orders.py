"""Boss order consumer: dispatch requests, drain, idle ticks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from cascade.board import move_doc, read_doc, write_doc
from cascade.boss.graph import (
    install_boss_consumer,
    process_boss_queue,
    reset_boss_consumer_offset,
    tick_boss_consumer,
)
from cascade.watchdog import activate_epic, append_event, dispatch_feature, dispatch_task
from cascade.watchdog.types import Event
from tests.support import add_doc, commit_board, make_repo, approve_board_feature


def test_kickoff_imports_before_watchdog_in_fresh_process() -> None:
    result = subprocess.run(
        [sys.executable, "-c", "from cascade.workspace.kickoff import deferred_kickoffs"],
        cwd=Path(__file__).resolve().parents[2],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def _boss_event(event_type: str, **payload: object) -> Event:
    return Event(
        type=event_type,
        ts=datetime.now(timezone.utc),
        payload=dict(payload),
        dest="boss",
    )


def _enqueue(root: Path, event: Event) -> None:
    append_event("boss", event, root=root)


@pytest.fixture
def board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature A", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Feature B", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task A1", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Task A2", tier="task", parent="feat_001")
    add_doc(root, id="task_003", title="Task B1", tier="task", parent="feat_002")
    reset_boss_consumer_offset(0)
    install_boss_consumer(root)
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    approve_board_feature(root, "feat_002")
    return root


def test_dispatch_requested_dispatches_exactly_once(board: Path) -> None:
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )
    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task, patch(
        "cascade.boss.orders.dispatch_feature"
    ) as mock_feature:
        new_offset = process_boss_queue(root=board, offset=0)
        assert new_offset == 0
        mock_task.assert_called_once_with("task_001", "boss", root=board)
        mock_feature.assert_not_called()

    doc = read_doc("task_001", root=board)
    assert doc.meta.status == "active"
    assert doc.meta.path.parent.name == "2_active"
    assert not (board / "docs/_queue/boss.jsonl").exists()


def test_drain_dispatches_only_feature_backlog_in_order(board: Path) -> None:
    add_doc(
        board,
        id="task_004",
        title="Waiting",
        tier="task",
        parent="feat_001",
        depends_on=["task_002"],
    )
    _enqueue(
        board,
        _boss_event("BossDrainRequested", feature_id="feat_001", by="human"),
    )
    dispatched: list[str] = []
    real_dispatch = dispatch_task

    def record(task_id: str, by: str, *, root: Path | None = None, skills=None):
        dispatched.append(task_id)
        return real_dispatch(task_id, by, root=root, skills=skills)

    with patch("cascade.boss.orders.dispatch_task", side_effect=record):
        process_boss_queue(root=board, offset=0)

    assert dispatched == ["task_001", "task_002"]
    assert read_doc("task_003", root=board).meta.status == "backlog"
    assert read_doc("task_004", root=board).meta.status == "backlog"


def test_idle_tick_zero_dispatches(board: Path) -> None:
    offset = process_boss_queue(root=board, offset=0)
    with patch("cascade.boss.orders.dispatch_task") as mock_task, patch(
        "cascade.boss.orders.dispatch_feature"
    ) as mock_feature:
        again = tick_boss_consumer()
        assert again == offset
        mock_task.assert_not_called()
        mock_feature.assert_not_called()


def test_drain_skips_blocked_task_explicit_dispatch_allowed(board: Path) -> None:
    assert dispatch_task("task_001", "human", root=board).ok
    blocked = read_doc("task_001", root=board)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=board)
    add_doc(board, id="task_005", title="Ready sibling", tier="task", parent="feat_001")

    _enqueue(
        board,
        _boss_event("BossDrainRequested", feature_id="feat_001", by="human"),
    )
    with patch("cascade.boss.orders.dispatch_task") as mock_task:
        process_boss_queue(root=board, offset=0)
        drained = [call.args[0] for call in mock_task.call_args_list]
        assert "task_001" not in drained
        assert "task_005" in drained
        assert "task_002" in drained

    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )
    process_boss_queue(root=board, offset=0)
    doc = read_doc("task_001", root=board)
    assert doc.meta.status == "active"


def test_dispatch_feature_request(board: Path) -> None:
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="feature", id="feat_001", by="human"),
    )
    process_boss_queue(root=board, offset=0)
    doc = read_doc("feat_001", root=board)
    assert doc.meta.status == "active"


def test_drain_stops_when_parallelism_cap_hit(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parallelism=1)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature A", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task A1", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Task A2", tier="task", parent="feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    reset_boss_consumer_offset(0)
    install_boss_consumer(root)
    _enqueue(
        root,
        _boss_event("BossDrainRequested", feature_id="feat_001", by="human"),
    )
    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task:
        process_boss_queue(root=root, offset=0)
        assert mock_task.call_count == 2
        assert mock_task.call_args_list[1].args[0] == "task_002"

    assert read_doc("task_001", root=root).meta.status == "active"
    assert read_doc("task_002", root=root).meta.status == "backlog"


def test_consumed_boss_queue_does_not_redispatch_after_restart(board: Path) -> None:
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )
    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task:
        offset = process_boss_queue(root=board, offset=0)
        assert mock_task.call_count == 1

    queue_path = board / "docs" / "_queue" / "boss.jsonl"
    assert offset == 0
    assert not queue_path.exists()
    reset_boss_consumer_offset(0)
    install_boss_consumer(board)

    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task:
        again = process_boss_queue(root=board, offset=offset)
        assert mock_task.call_count == 0
        assert again == 0


def test_legacy_dispatch_for_completed_task_is_acknowledged_without_boot(
    board: Path,
) -> None:
    move_doc("task_001", "completed", root=board)
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )

    with patch("cascade.watchdog.dispatch.invoke_boot") as boot, patch(
        "cascade.workspace.kickoff.kickoff_turn"
    ) as kickoff:
        assert process_boss_queue(root=board, offset=0) == 0

    boot.assert_not_called()
    kickoff.assert_not_called()
    assert read_doc("task_001", root=board).meta.status == "completed"
    assert not (board / "docs/_queue/boss.jsonl").exists()


def test_boss_queue_keeps_event_appended_during_processing(board: Path) -> None:
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )
    real_process = __import__(
        "cascade.boss.graph", fromlist=["process_boss_event"]
    ).process_boss_event
    appended = False

    def process_and_append(event, *, root):
        nonlocal appended
        real_process(event, root=root)
        if not appended:
            appended = True
            _enqueue(
                board,
                _boss_event("BossDispatchRequested", kind="task", id="task_002", by="human"),
            )

    with patch("cascade.boss.graph.process_boss_event", side_effect=process_and_append):
        offset = process_boss_queue(root=board, offset=0)

    assert offset > 0
    assert (board / "docs/_queue/boss.jsonl").is_file()
    reset_boss_consumer_offset(0)
    install_boss_consumer(board)
    process_boss_queue(root=board, offset=0)
    assert read_doc("task_002", root=board).meta.status == "active"
    assert not (board / "docs/_queue/boss.jsonl").exists()
