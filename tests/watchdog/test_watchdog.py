"""Illegal 2_active appearances are reverted. Authorized work stays."""

import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.board import move_doc, read_doc, write_doc
from cascade.watchdog import (
    Event,
    activate_epic,
    append_event,
    dispatch_feature,
    dispatch_task,
    read_events,
    run_watchdog,
    watchdog_tick,
)
from tests.support import add_doc, commit_board, make_repo, approve_board_feature


def test_watchdog_queue_kickoff_does_not_wait_for_model_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    entered = threading.Event()
    release = threading.Event()

    def slow_turn(_reason, _repo) -> None:
        entered.set()
        release.wait(timeout=5)

    def deliver(repo: Path) -> None:
        from cascade.workspace.kickoff import kickoff_turn
        from cascade.workspace.types import KickoffReason

        kickoff_turn(KickoffReason(kind="queue_event", work_id="task_001", by="watchdog", root=repo))

    monkeypatch.setattr("cascade.workspace.kickoff._run_kickoff", slow_turn)
    monkeypatch.setattr("cascade.workspace.kickoff.deliver_queue_kickoffs", deliver)
    monkeypatch.setattr("cascade.automation.advance_work", lambda _root: {})
    monkeypatch.setattr("cascade.automation.poll_reviews", lambda _root: None)
    monkeypatch.setattr("cascade.automation.maybe_sync_briefs", lambda _root: None)

    started = time.monotonic()
    watchdog_tick(root)
    elapsed = time.monotonic() - started
    try:
        assert entered.wait(timeout=1)
        assert elapsed < 0.5
    finally:
        release.set()


def test_periodic_stale_task_reclaim_enqueues_one_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    restores = iter([[('task_001', 'feat_001')], []])
    kicked: list[str] = []
    monkeypatch.setattr(
        "cascade.task.wiring.restore_active_task_runs",
        lambda _root: next(restores),
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_graph_queue_event",
        lambda work_id, **_kwargs: kicked.append(work_id) or True,
    )
    from cascade.watchdog.loop import _resume_reclaimable_task_runs

    _resume_reclaimable_task_runs(root)
    _resume_reclaimable_task_runs(root)

    events, _ = read_events("task_001", 0, root=root)
    assert [event.type for event in events] == ["TaskResumeRequested"]
    assert kicked == ["task_001"]


def test_authorized_dispatch_stays_without_git_history(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Legal task", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Rogue task", tier="task", parent="feat_001")

    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    move_doc("task_002", "active", root=root)

    watchdog_tick(root)

    legal = read_doc("task_001", root=root)
    assert legal.meta.status == "active"
    assert legal.meta.path.parent.name == "2_active"
    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "active"
    assert epic.meta.path.parent.name == "2_active"
    rogue = read_doc("task_002", root=root)
    assert rogue.meta.status == "backlog"
    assert rogue.meta.path.parent.name == "1_backlog"


def test_rogue_move_is_reverted_and_legal_dispatch_stays(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Legal epic", tier="epic")
    add_doc(root, id="epic_002", title="Rogue epic", tier="epic")
    add_doc(root, id="feat_001", title="Legal feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Rogue feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Legal task", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Rogue task", tier="task", parent="feat_001")
    commit_board(root)

    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "boss", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    move_doc("epic_002", "active", root=root)
    move_doc("feat_002", "active", root=root)
    move_doc("task_002", "active", root=root)

    watchdog_tick(root)

    for work_id in ("epic_001", "feat_001", "task_001"):
        doc = read_doc(work_id, root=root)
        assert doc.meta.status == "active"
        assert doc.meta.path.parent.name == "2_active"
    for work_id in ("epic_002", "feat_002", "task_002"):
        doc = read_doc(work_id, root=root)
        assert doc.meta.status == "backlog", work_id
        assert doc.meta.path.parent.name == "1_backlog"

    events, _offset = read_events("war_room", 0, root=root)
    toasts = [event for event in events if event.type == "Toast"]
    assert {event.payload["id"] for event in toasts} == {"epic_002", "feat_002", "task_002"}
    for toast in toasts:
        assert toast.dest == "war_room"
        assert toast.payload["kind"] == "illegal_move"
        assert toast.payload["reason"] == "unauthorized"
        assert toast.payload["message"]

    watchdog_tick(root)
    again, _again_offset = read_events("war_room", 0, root=root)
    assert len([event for event in again if event.type == "Toast"]) == 3


def test_task_failed_does_not_authorize(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Failed task", tier="task", parent="feat_001")
    append_event(
        "task_001",
        Event(
            type="TaskFailed",
            ts=datetime.now(timezone.utc),
            payload={"id": "task_001", "task_id": "task_001", "reason": "tests"},
            dest="task_001",
        ),
        root=root,
    )
    move_doc("task_001", "active", root=root)
    watchdog_tick(root)
    doc = read_doc("task_001", root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.path.parent.name == "1_backlog"
    toasts, _offset = read_events("war_room", 0, root=root)
    assert len(toasts) == 1
    assert toasts[0].type == "Toast"
    assert toasts[0].payload["id"] == "task_001"


def test_run_watchdog_stops_after_a_tick(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_002", title="Rogue epic", tier="epic")
    move_doc("epic_002", "active", root=root)
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    run_watchdog(root=root, poll_interval=0.01, stop_when=stop)
    assert calls["n"] == 2
    assert read_doc("epic_002", root=root).meta.status == "backlog"
    import inspect

    assert inspect.signature(run_watchdog).parameters["poll_interval"].default == 0.5


def test_run_watchdog_survives_a_failed_tick(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    root = make_repo(tmp_path)
    attempts = 0

    def tick(_root: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient tick failure")

    monkeypatch.setattr("cascade.watchdog.loop.watchdog_tick", tick)
    monkeypatch.setattr("cascade.watchdog.loop.time.sleep", lambda _seconds: None)

    run_watchdog(
        root=root,
        poll_interval=0,
        stop_when=lambda: attempts >= 2,
    )

    assert attempts == 2
    assert "transient tick failure" in capsys.readouterr().err


def test_run_watchdog_uses_light_event_ticks_between_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    ticks: list[str] = []
    checks = 0

    monkeypatch.setattr("cascade.watchdog.loop.watchdog_tick", lambda _root: ticks.append("full"))
    monkeypatch.setattr("cascade.watchdog.loop._event_tick", lambda _root: ticks.append("event"))
    monkeypatch.setattr("cascade.watchdog.loop._resume_reclaimable_task_runs", lambda _root: None)
    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        lambda **_kwargs: {},
    )
    monkeypatch.setattr("cascade.automation.advance_work", lambda _root: {})
    monkeypatch.setattr("cascade.watchdog.loop.time.sleep", lambda _seconds: None)

    def stop() -> bool:
        nonlocal checks
        checks += 1
        return checks >= 6

    run_watchdog(root=root, poll_interval=0, stop_when=stop)

    assert ticks == ["full", "event", "event"]


def test_event_tick_only_delivers_changed_work_queues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    delivered: list[Path] = []
    monkeypatch.setattr("cascade.watchdog.loop.tick_boss_consumer", lambda: 0)
    monkeypatch.setattr(
        "cascade.workspace.kickoff.deliver_queue_kickoffs",
        lambda repo: delivered.append(repo),
    )
    from cascade.watchdog.loop import _event_tick

    _event_tick(root)
    _event_tick(root)
    queue = root / "docs" / "_queue" / "task_001.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("{}\n", encoding="utf-8")
    _event_tick(root)

    assert delivered == [root, root]


def test_event_tick_retries_unchanged_queue_after_delivery_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    queue = root / "docs" / "_queue" / "task_001.jsonl"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text("{}\n", encoding="utf-8")
    attempts = 0

    def flaky_delivery(_repo: Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError("transient queue read failure")

    monkeypatch.setattr("cascade.watchdog.loop.tick_boss_consumer", lambda: 0)
    monkeypatch.setattr("cascade.workspace.kickoff.deliver_queue_kickoffs", flaky_delivery)
    from cascade.watchdog.loop import _event_tick

    with pytest.raises(OSError, match="transient"):
        _event_tick(root)
    _event_tick(root)

    assert attempts == 2


def test_war_room_event_does_not_authorize(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Forged", tier="task", parent="feat_001")
    append_event(
        "war_room",
        Event(
            type="TaskDispatched",
            ts=datetime.now(timezone.utc),
            payload={
                "id": "task_001",
                "task_id": "task_001",
                "feature_id": "feat_001",
                "by": "human",
                "skills": [],
            },
            dest="war_room",
        ),
        root=root,
    )
    move_doc("task_001", "active", root=root)
    watchdog_tick(root)
    doc = read_doc("task_001", root=root)
    assert doc.meta.status == "backlog"
    assert doc.meta.path.parent.name == "1_backlog"
    toasts, _offset = read_events("war_room", 0, root=root)
    assert any(event.type == "Toast" and event.payload["id"] == "task_001" for event in toasts)


def test_stale_authorization_and_blocked_edit(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Comes back", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Stays blocked", tier="task", parent="feat_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    assert dispatch_task("task_002", "boss", root=root).ok
    move_doc("task_001", "completed", root=root)

    queue = root / "docs" / "_queue" / "task_001.jsonl"
    lines = [json.loads(line) for line in queue.read_text(encoding="utf-8").splitlines() if line]
    lines[-1]["ts"] = (datetime.now(timezone.utc) - timedelta(seconds=30)).isoformat()
    queue.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")

    move_doc("task_001", "active", root=root)
    blocked = read_doc("task_002", root=root)
    blocked.meta.status = "blocked"
    write_doc(blocked, root=root)
    watchdog_tick(root)

    returned = read_doc("task_001", root=root)
    assert returned.meta.status == "backlog"
    assert returned.meta.path.parent.name == "1_backlog"
    stayed = read_doc("task_002", root=root)
    assert stayed.meta.status == "blocked"
    assert stayed.meta.path.parent.name == "2_active"
    toasts, _offset = read_events("war_room", 0, root=root)
    assert any(event.type == "Toast" and event.payload["id"] == "task_001" for event in toasts)
    assert not any(event.type == "Toast" and event.payload.get("id") == "task_002" for event in toasts)


def test_duplicate_toast_suppressed_when_revert_blocked(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    garbage = root / "docs" / "tasks" / "2_active" / "task_099_garbage.md"
    backlog = root / "docs" / "tasks" / "1_backlog" / "task_099_garbage.md"
    backlog.write_bytes(b"blocks rename")
    garbage.write_bytes(b"\xff\xfe not utf-8")

    watchdog_tick(root)
    watchdog_tick(root)

    events, _offset = read_events("war_room", 0, root=root)
    toasts = [event for event in events if event.type == "Toast"]
    assert len(toasts) == 1
    assert toasts[0].payload["id"] == "task_099"
    assert garbage.is_file()


def test_orphan_toast_enqueued_once_and_retries_after_append_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Open task", tier="task", parent="feat_001")
    move_doc("feat_001", "completed", root=root)

    append_calls = {"n": 0}

    def flaky_append(dest: str, event: Event, *, root: Path | None = None) -> None:
        append_calls["n"] += 1
        if append_calls["n"] == 1:
            raise OSError("simulated queue write failure")
        append_event(dest, event, root=root)

    monkeypatch.setattr("cascade.watchdog.loop.append_event", flaky_append)

    watchdog_tick(root)
    events, _offset = read_events("war_room", 0, root=root)
    assert not [event for event in events if event.payload.get("kind") == "orphan"]

    watchdog_tick(root)
    events, _offset = read_events("war_room", 0, root=root)
    orphan_toasts = [event for event in events if event.payload.get("kind") == "orphan"]
    assert len(orphan_toasts) == 1
    assert orphan_toasts[0].payload["id"] == "task_001"

    watchdog_tick(root)
    again, _again_offset = read_events("war_room", 0, root=root)
    assert len([event for event in again if event.payload.get("kind") == "orphan"]) == 1


def test_non_utf8_file_does_not_escape_or_stay_active(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    garbage = root / "docs" / "tasks" / "2_active" / "task_099_garbage.md"
    garbage.write_bytes(b"\xff\xfe not utf-8 \x80\x81")
    calls = {"n": 0}

    def stop() -> bool:
        calls["n"] += 1
        return calls["n"] >= 2

    run_watchdog(root=root, poll_interval=0.01, stop_when=stop)
    assert calls["n"] == 2
    assert not garbage.exists()
    assert (root / "docs" / "tasks" / "1_backlog" / "task_099_garbage.md").is_file()
