"""Monotonic last_queue_offset helper (task_017_001_002)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.feature.graph import clear_feature_graph_sessions, ensure_feature_graph, ingest_queue
from cascade.watchdog import Event, append_event
from cascade.watchdog.events import read_events
from cascade.watchdog.queue_cursor import resolve_last_queue_offset
from tests.harness.queue_delivery import install_queue_delivery_test_isolation
from tests.support import make_repo


def _event(dest: str, **payload: object) -> Event:
    return Event(
        type="DecisionRecorded",
        ts=datetime.now(timezone.utc),
        payload=dict(payload),
        dest=dest,
    )


@pytest.fixture(autouse=True)
def _isolate(monkeypatch: pytest.MonkeyPatch) -> None:
    install_queue_delivery_test_isolation(monkeypatch)
    yield
    clear_feature_graph_sessions()


def test_refuses_lower_cursor_write(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = make_repo(tmp_path, git=False)
    work_id = "feat_001"
    append_event(work_id, _event(dest=work_id, entry="one"), root=root)
    _, eof = read_events(work_id, 0, root=root)
    assert eof > 0

    with caplog.at_level(logging.WARNING):
        resolved = resolve_last_queue_offset(
            work_id,
            current=eof,
            proposed=max(eof - 10, 0),
            root=root,
        )

    assert resolved == eof
    assert any("refused to lower last_queue_offset" in record.message for record in caplog.records)


def test_truncation_reset_allowed_and_logged(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    root = make_repo(tmp_path, git=False)
    feature_id = "feat_017_001"
    ensure_feature_graph(feature_id, root=root)

    append_event(
        feature_id,
        _event(dest=feature_id, section="Decision log", entry="before_truncate"),
        root=root,
    )
    first = ingest_queue(feature_id, root=root)
    stale_offset = int(first["last_queue_offset"])
    assert stale_offset > 0

    line = (
        '{"type":"DecisionRecorded","ts":"2026-01-01T00:00:00+00:00",'
        '"payload":{"section":"Decision log","entry":"after_truncate"},"dest":"'
        + feature_id
        + '"}'
    ).encode("utf-8") + b"\n"
    path = root / "docs" / "_queue" / f"{feature_id}.jsonl"
    path.write_bytes(line)
    assert stale_offset > path.stat().st_size

    with caplog.at_level(logging.WARNING):
        after = ingest_queue(feature_id, root=root)

    new_offset = int(after["last_queue_offset"])
    assert new_offset == path.stat().st_size
    assert new_offset < stale_offset
    assert any(
        "reset last_queue_offset after truncated or replaced queue" in r.message
        for r in caplog.records
    )
    messages = [m for m in after.get("messages") or [] if m.get("role") == "event"]
    assert any("after_truncate" in m.get("content", "") for m in messages)
