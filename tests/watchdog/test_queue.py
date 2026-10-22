"""Append-only JSONL queues."""

from datetime import datetime, timezone
from pathlib import Path

from cascade.watchdog import Event, append_event, read_events
from cascade.watchdog.events import prune_completed_work_queues, remove_queue_if_unchanged
from tests.support import add_doc, make_repo


def _event(event_type: str, dest: str, **payload: object) -> Event:
    return Event(
        type=event_type,
        ts=datetime.now(timezone.utc),
        payload=dict(payload),
        dest=dest,
    )


def test_round_trip_offset_and_append_only(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    missing, missing_offset = read_events("war_room", 0, root=root)
    assert missing == []
    assert missing_offset == 0

    first = _event("EpicActivated", "war_room", epic_id="epic_001", by="human")
    append_event("war_room", first, root=root)
    path = root / "docs" / "_queue" / "war_room.jsonl"
    snapshot = path.read_bytes()

    events, offset = read_events("war_room", 0, root=root)
    assert len(events) == 1
    assert events[0].type == "EpicActivated"
    assert events[0].dest == "war_room"
    assert events[0].payload == {"epic_id": "epic_001", "by": "human"}
    assert events[0].ts.tzinfo is not None
    assert events[0].ts.utcoffset() is not None
    assert offset == len(snapshot)

    second = _event("FeatureReadyToPlan", "war_room", id="feat_001", feature_id="feat_001", by="boss")
    append_event("war_room", second, root=root)
    resumed, next_offset = read_events("war_room", offset, root=root)
    assert [event.type for event in resumed] == ["FeatureReadyToPlan"]
    assert resumed[0].payload["by"] == "boss"
    assert next_offset > offset

    data = path.read_bytes()
    assert data.startswith(snapshot)
    assert snapshot in data
    assert data.count(b"\n") == 2


def test_malformed_lines_are_skipped(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    append_event("boss", _event("CommentPosted", "boss", doc_id="feat_001"), root=root)
    path = root / "docs" / "_queue" / "boss.jsonl"
    with path.open("ab") as handle:
        handle.write(b"this is not json\n")
        handle.write(b"{}\n")
        handle.write(b'{"type": "Nope", "payload": []}\n')
    append_event("boss", _event("DecisionRecorded", "boss", doc_id="feat_001"), root=root)

    events, offset = read_events("boss", 0, root=root)
    assert [event.type for event in events] == ["CommentPosted", "DecisionRecorded"]
    again, again_offset = read_events("boss", offset, root=root)
    assert again == []
    assert again_offset == offset


def test_trailing_partial_line_waits_for_completion(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    append_event("war_room", _event("EpicActivated", "war_room", epic_id="epic_001"), root=root)
    path = root / "docs" / "_queue" / "war_room.jsonl"
    first_batch, offset = read_events("war_room", 0, root=root)
    assert len(first_batch) == 1

    partial = b'{"type":"FeatureReadyToPlan","ts":"2026-01-01T00:00:00+00:00","payload":{"id":"feat_001"},"dest":"war_room"'
    with path.open("ab") as handle:
        handle.write(partial)

    partial_events, partial_offset = read_events("war_room", offset, root=root)
    assert partial_events == []
    assert partial_offset == offset

    with path.open("ab") as handle:
        handle.write(b"}\n")

    completed, next_offset = read_events("war_room", partial_offset, root=root)
    assert len(completed) == 1
    assert completed[0].type == "FeatureReadyToPlan"
    assert completed[0].payload == {"id": "feat_001"}
    assert next_offset > partial_offset


def test_missing_file_and_stale_offset_reread(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    stale = 4096

    missing, missing_offset = read_events("boss", stale, root=root)
    assert missing == []
    assert missing_offset == 0

    append_event("boss", _event("CommentPosted", "boss", doc_id="feat_001"), root=root)
    path = root / "docs" / "_queue" / "boss.jsonl"
    data = path.read_bytes()

    events, offset = read_events("boss", stale, root=root)
    assert len(events) == 1
    assert events[0].type == "CommentPosted"
    assert offset == len(data)


def test_remove_queue_if_unchanged_preserves_concurrent_suffix(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    append_event("boss", _event("BossDrainRequested", "boss"), root=root)
    path = root / "docs" / "_queue" / "boss.jsonl"
    acknowledged_size = path.stat().st_size
    append_event("boss", _event("BossDispatchRequested", "boss"), root=root)

    assert not remove_queue_if_unchanged(
        "boss", expected_size=acknowledged_size, root=root
    )
    assert path.is_file()
    assert len(read_events("boss", acknowledged_size, root=root)[0]) == 1


def test_prune_removes_only_terminal_work_queues(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Done", tier="epic", status="completed")
    add_doc(
        root,
        id="feat_001",
        title="Active",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Blocked",
        tier="task",
        status="blocked",
        parent="feat_001",
    )
    for dest in ("epic_001", "feat_001", "task_001", "war_room"):
        append_event(dest, _event("Lifecycle", dest), root=root)

    assert prune_completed_work_queues(root=root) == ["epic_001"]
    assert not (root / "docs/_queue/epic_001.jsonl").exists()
    for dest in ("feat_001", "task_001", "war_room"):
        assert (root / "docs" / "_queue" / f"{dest}.jsonl").is_file()


def test_prune_recognizes_hierarchical_work_id(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    task_id = "task_007_001_001"
    add_doc(root, id="epic_007", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_007_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_007",
    )
    add_doc(
        root,
        id=task_id,
        title="Done",
        tier="task",
        status="completed",
        parent="feat_007_001",
    )
    append_event(task_id, _event("Lifecycle", task_id), root=root)

    assert prune_completed_work_queues(root=root) == [task_id]
    assert not (root / "docs" / "_queue" / f"{task_id}.jsonl").exists()


def test_prune_keeps_completed_feature_awaiting_review(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Review",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    append_event("feat_001", _event("MergeRequestComment", "feat_001"), root=root)
    monkeypatch.setattr("cascade.review.feature_review_pending", lambda *_args, **_kwargs: True)

    assert prune_completed_work_queues(root=root) == []
    assert (root / "docs/_queue/feat_001.jsonl").is_file()
