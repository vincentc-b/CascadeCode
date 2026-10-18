"""Boss order consumer: dispatch requests, drain, idle ticks."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from cascade.board import read_doc, write_doc
from cascade.boss.graph import (
    boss_consumer_offset,
    install_boss_consumer,
    process_boss_queue,
    reset_boss_consumer_offset,
    tick_boss_consumer,
)
from cascade.watchdog import activate_epic, append_event, dispatch_feature, dispatch_task
from cascade.watchdog.types import Event
from tests.support import add_doc, commit_board, make_repo


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
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_feature("feat_002", "human", root=root).ok
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
        assert new_offset > 0
        mock_task.assert_called_once_with("task_001", "boss", root=board)
        mock_feature.assert_not_called()

    doc = read_doc("task_001", root=board)
    assert doc.meta.status == "active"
    assert doc.meta.path.parent.name == "2_active"


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
    offset = boss_consumer_offset()
    process_boss_queue(root=board, offset=offset)
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


def test_truncated_boss_queue_does_not_redispatch(board: Path) -> None:
    _enqueue(
        board,
        _boss_event("BossDispatchRequested", kind="task", id="task_001", by="human"),
    )
    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task:
        offset = process_boss_queue(root=board, offset=0)
        assert mock_task.call_count == 1

    queue_path = board / "docs" / "_queue" / "boss.jsonl"
    prefix = queue_path.read_bytes()[: max(1, offset // 2)]
    queue_path.write_bytes(prefix)

    with patch("cascade.boss.orders.dispatch_task", wraps=dispatch_task) as mock_task:
        again = process_boss_queue(root=board, offset=offset)
        assert mock_task.call_count == 0
        assert again == len(prefix)
