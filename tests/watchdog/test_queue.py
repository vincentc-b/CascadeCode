"""Append-only JSONL queues."""

from datetime import datetime, timezone
from pathlib import Path

from cascade.watchdog import Event, append_event, read_events
from tests.support import make_repo


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
