"""Cross-process and crash-boundary coverage for the transcript writer."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest

from cascade.war_room import chat_store
from cascade.war_room.chat_store import (
    TranscriptPendingError,
    append_transcript_message,
    fenced_transcript_source_acknowledgement,
    move_transcript_room,
    read_messages,
    remove_message,
)
from tests.support import add_doc, make_repo


def _line(message_id: str, body: str, source_key: str) -> bytes:
    return (
        json.dumps(
            {
                "id": message_id,
                "graph_id": "epic_001",
                "author": "system",
                "body": body,
                "ts": "2026-01-01T00:00:00+00:00",
                "event_schema_version": 1,
                "source_key": source_key,
                "occurred_at": None,
                "appended_at": "2026-01-01T00:00:00+00:00",
                "provenance": "direct",
            },
            separators=(",", ":"),
        )
        + "\n"
    ).encode()


def _seed_intent(root: Path, line: bytes, *, written: int) -> None:
    path = root / "docs" / "_war_room" / "chat" / "epic_001.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(line[:written])
    connection = chat_store._connect_index("epic_001", root=root)
    try:
        value = json.loads(line)
        connection.execute(
            "UPDATE state SET room_path = ?, indexed_end = 0 WHERE singleton = 1",
            (str(path.resolve()),),
        )
        connection.execute(
            """INSERT INTO pending_intent
               (singleton, room_path, expected_offset, line, digest, message_id, source_key)
               VALUES (1, ?, 0, ?, ?, ?, ?)""",
            (
                str(path.resolve()),
                line,
                hashlib.sha256(line).hexdigest(),
                value["id"],
                value["source_key"],
            ),
        )
        connection.commit()
    finally:
        connection.close()


def test_fenced_source_lookup_leaves_pending_intent_for_writer_repair(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    intended = _line("message-1", "durable", "receipt-1")
    _seed_intent(root, intended, written=len(intended))

    with pytest.raises(TranscriptPendingError, match="routing is pending"):
        with fenced_transcript_source_acknowledgement(
            "epic_001", source_key="receipt-1", root=root
        ):
            pytest.fail("pending routing must not be yielded")

    connection = chat_store._connect_index("epic_001", root=root)
    try:
        assert (
            connection.execute("SELECT count(*) FROM pending_intent").fetchone()[0] == 1
        )
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    finally:
        connection.close()


def test_fenced_source_lookup_does_not_initialize_missing_index(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    index = chat_store._index_path("epic_001", root=root)

    with pytest.raises(TranscriptPendingError, match="index is unavailable"):
        with fenced_transcript_source_acknowledgement(
            "epic_001",
            source_key="receipt-1",
            root=root,
            deadline=time.monotonic() + 0.2,
        ):
            pytest.fail("missing index cannot produce routing")

    assert not index.exists()


@pytest.mark.parametrize("written", [0, 17, -1])
def test_repairs_intent_empty_partial_or_complete_tail(
    tmp_path: Path, written: int
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    intended = _line("message-1", "durable", "receipt-1")
    _seed_intent(root, intended, written=len(intended) if written == -1 else written)

    row = append_transcript_message(
        "epic_001",
        author="system",
        body="ignored duplicate presentation",
        root=root,
        message_id="message-1",
        source_key="receipt-1",
    )

    assert row["body"] == "durable"
    assert (root / "docs/_war_room/chat/epic_001.jsonl").read_bytes() == intended


def test_complete_pending_line_is_fsynced_before_index_commit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    intended = _line("message-1", "durable", "receipt-1")
    _seed_intent(root, intended, written=len(intended))
    synced = False
    real_sync = chat_store._fsync_file_and_parent
    real_commit = chat_store._commit_intent

    def observe_sync(path: Path) -> None:
        nonlocal synced
        real_sync(path)
        synced = True

    def observe_commit(connection: sqlite3.Connection, intent: sqlite3.Row) -> None:
        assert synced
        real_commit(connection, intent)

    monkeypatch.setattr(chat_store, "_fsync_file_and_parent", observe_sync)
    monkeypatch.setattr(chat_store, "_commit_intent", observe_commit)

    append_transcript_message(
        "epic_001", author="system", body="replay", root=root,
        message_id="message-1", source_key="receipt-1",
    )

    assert synced


def test_complete_pending_line_fsync_failure_keeps_intent_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    intended = _line("message-1", "durable", "receipt-1")
    _seed_intent(root, intended, written=len(intended))
    real_sync = chat_store._fsync_file_and_parent

    def fail_sync(_path: Path) -> None:
        raise OSError("injected fsync failure")

    monkeypatch.setattr(chat_store, "_fsync_file_and_parent", fail_sync)
    with pytest.raises(OSError, match="injected fsync failure"):
        append_transcript_message(
            "epic_001",
            author="system",
            body="replay",
            root=root,
            message_id="message-1",
            source_key="receipt-1",
        )

    connection = chat_store._connect_index("epic_001", root=root)
    try:
        assert connection.execute("SELECT count(*) FROM pending_intent").fetchone()[0] == 1
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 0
    finally:
        connection.close()

    monkeypatch.setattr(chat_store, "_fsync_file_and_parent", real_sync)
    replay = append_transcript_message(
        "epic_001",
        author="system",
        body="replay",
        root=root,
        message_id="message-1",
        source_key="receipt-1",
    )

    assert replay["body"] == "durable"
    assert (root / "docs/_war_room/chat/epic_001.jsonl").read_bytes() == intended


def test_unexpected_tail_stays_pending_without_truncation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    intended = _line("message-1", "durable", "receipt-1")
    unrelated = b'{"id":"unrelated"}\n'
    _seed_intent(root, intended, written=0)
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    path.write_bytes(intended + unrelated)

    with pytest.raises(TranscriptPendingError, match="pending transcript"):
        append_transcript_message(
            "epic_001", author="system", body="later", root=root,
            source_key="receipt-2",
        )

    assert path.read_bytes() == intended + unrelated


def test_replay_after_index_commit_returns_the_committed_line(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    committed = append_transcript_message(
        "epic_001",
        author="system",
        body="committed",
        root=root,
        message_id="message-1",
        source_key="receipt-1",
    )
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    before = path.read_bytes()

    replay = append_transcript_message(
        "epic_001",
        author="system",
        body="duplicate delivery",
        root=root,
        message_id="message-1",
        source_key="receipt-1",
    )

    assert replay == committed
    assert path.read_bytes() == before


def test_human_rollback_rebuild_preserves_other_source_keys(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    human = append_transcript_message(
        "epic_001", author="human", body="remove me", root=root
    )
    append_transcript_message(
        "epic_001",
        author="epic_manager",
        body="keep me",
        root=root,
        source_key="role_reply:epic_001:message:reply-1",
    )

    remove_message("epic_001", human["id"], root=root)
    append_transcript_message(
        "epic_001",
        author="epic_manager",
        body="duplicate presentation",
        root=root,
        source_key="role_reply:epic_001:message:reply-1",
    )

    assert [row["body"] for row in read_messages("epic_001", root=root)] == [
        "keep me"
    ]


def test_rewrite_restarts_after_replacement_before_index_reset(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    human = append_transcript_message(
        "epic_001", author="human", body="remove me", root=root
    )
    committed = append_transcript_message(
        "epic_001",
        author="system",
        body="keep me",
        root=root,
        message_id="message-1",
        source_key="receipt-1",
    )
    crashed = False

    def fault(stage: str) -> None:
        nonlocal crashed
        if stage == "after_replace" and not crashed:
            crashed = True
            raise RuntimeError("crash after transcript replacement")

    monkeypatch.setattr(chat_store, "_rewrite_fault", fault)
    with pytest.raises(RuntimeError, match="after transcript replacement"):
        remove_message("epic_001", human["id"], root=root)

    connection = chat_store._connect_index("epic_001", root=root)
    try:
        target_incarnation = connection.execute(
            "SELECT target_incarnation FROM rewrite_intent WHERE singleton = 1"
        ).fetchone()[0]
    finally:
        connection.close()

    replay = append_transcript_message(
        "epic_001",
        author="system",
        body="duplicate presentation",
        root=root,
        source_key="receipt-1",
    )

    assert replay == committed
    assert [row["body"] for row in read_messages("epic_001", root=root)] == [
        "keep me"
    ]
    connection = chat_store._connect_index("epic_001", root=root)
    try:
        assert connection.execute("SELECT count(*) FROM rewrite_intent").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
        assert connection.execute(
            "SELECT incarnation FROM state WHERE singleton = 1"
        ).fetchone()[0] == target_incarnation
    finally:
        connection.close()


def test_rewrite_recovery_preserves_conflicting_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    human = append_transcript_message(
        "epic_001", author="human", body="remove me", root=root
    )
    crashed = False

    def fault(stage: str) -> None:
        nonlocal crashed
        if stage == "after_replace" and not crashed:
            crashed = True
            raise RuntimeError("crash after transcript replacement")

    monkeypatch.setattr(chat_store, "_rewrite_fault", fault)
    with pytest.raises(RuntimeError, match="after transcript replacement"):
        remove_message("epic_001", human["id"], root=root)
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    conflict = b'{"id":"unrelated"}\n'
    path.write_bytes(conflict)

    with pytest.raises(TranscriptPendingError, match="pending rewrite"):
        append_transcript_message(
            "epic_001", author="system", body="must wait", root=root
        )

    assert path.read_bytes() == conflict


def test_two_real_processes_deduplicate_one_source(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    script = """
from pathlib import Path
from cascade.war_room.chat_store import append_transcript_message
append_transcript_message('epic_001', author='system', body='once', root=Path(__import__('sys').argv[1]), source_key='receipt-1')
"""
    environment = {**os.environ, "PYTHONPATH": str(Path.cwd())}
    processes = [
        subprocess.Popen([sys.executable, "-c", script, str(root)], env=environment)
        for _ in range(2)
    ]
    assert [process.wait(timeout=20) for process in processes] == [0, 0]

    assert [row["body"] for row in read_messages("epic_001", root=root)] == ["once"]
    connection = sqlite3.connect(chat_store._index_path("epic_001", root=root))
    try:
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    finally:
        connection.close()


def test_fenced_lookup_second_process_flock_obeys_deadline(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_transcript_message(
        "epic_001", author="system", body="once", root=root, source_key="receipt-1"
    )
    lock_path = chat_store._index_path("epic_001", root=root).with_suffix(".lock")
    script = """
import fcntl, sys
with open(sys.argv[1], 'a+b') as handle:
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    print('locked', flush=True)
    sys.stdin.read(1)
"""
    blocker = subprocess.Popen(
        [sys.executable, "-c", script, str(lock_path)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert blocker.stdout is not None
        assert blocker.stdout.readline().strip() == "locked"
        started = time.monotonic()
        with pytest.raises(TranscriptPendingError, match="deadline"):
            with fenced_transcript_source_acknowledgement(
                "epic_001",
                source_key="receipt-1",
                root=root,
                deadline=started + 0.2,
            ):
                pytest.fail("contended OS fence must remain pending")
        elapsed = time.monotonic() - started
        assert 0.12 <= elapsed < 0.75
    finally:
        assert blocker.stdin is not None
        blocker.stdin.write("x")
        blocker.stdin.flush()
        assert blocker.wait(timeout=5) == 0

    with fenced_transcript_source_acknowledgement(
        "epic_001",
        source_key="receipt-1",
        root=root,
        deadline=time.monotonic() + 1.0,
    ) as acknowledgement:
        assert acknowledgement["message_id"]


def test_append_sqlite_writer_contention_obeys_deadline_then_replays(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_transcript_message(
        "epic_001", author="system", body="first", root=root, source_key="receipt-1"
    )
    blocker = sqlite3.connect(chat_store._index_path("epic_001", root=root))
    blocker.execute("BEGIN IMMEDIATE")
    try:
        started = time.monotonic()
        with pytest.raises(TranscriptPendingError, match="index is busy"):
            append_transcript_message(
                "epic_001",
                author="system",
                body="second",
                root=root,
                source_key="receipt-2",
                deadline=started + 0.2,
            )
        elapsed = time.monotonic() - started
        assert 0.12 <= elapsed < 0.75
    finally:
        blocker.rollback()
        blocker.close()

    append_transcript_message(
        "epic_001", author="system", body="second", root=root, source_key="receipt-2"
    )
    assert [row["source_key"] for row in read_messages("epic_001", root=root)] == [
        "receipt-1",
        "receipt-2",
    ]


def test_index_schema_and_fenced_lookup_refresh_remaining_budget_per_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_transcript_message(
        "epic_001", author="system", body="once", root=root, source_key="receipt-1"
    )
    observed: list[int] = []
    original = chat_store._set_index_deadline
    ticks = iter(range(1_000, 10_000, 10))
    monkeypatch.setattr(chat_store.time, "monotonic", lambda: next(ticks) / 1_000)

    def record(
        connection: sqlite3.Connection, deadline: float | None
    ) -> None:
        original(connection, deadline)
        if deadline is not None:
            observed.append(
                int(connection.execute("PRAGMA busy_timeout").fetchone()[0])
            )

    monkeypatch.setattr(chat_store, "_set_index_deadline", record)
    schema = chat_store._connect_index(
        "epic_002", root=root, deadline=9.0
    )
    schema.close()
    schema_refreshes = len(observed)
    assert schema_refreshes == 11

    with fenced_transcript_source_acknowledgement(
        "epic_001", source_key="receipt-1", root=root, deadline=9.0
    ) as acknowledgement:
        assert acknowledgement["message_id"]

    assert len(observed) - schema_refreshes == 12
    assert all(later < earlier for earlier, later in zip(observed, observed[1:]))


def test_split_roots_keep_jsonl_with_product_and_fence_with_tracking(
    tmp_path: Path,
) -> None:
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext

    product = make_repo(tmp_path / "product", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    set_project_context(ProjectContext.split(product, tracking))
    try:
        append_transcript_message(
            "epic_001", author="human", body="split", root=product
        )
        key = hashlib.sha256(b"epic_001").hexdigest()
        assert (product / "docs/_war_room/chat/epic_001.jsonl").is_file()
        assert (tracking / f".cascade/transcript_index/{key}.lock").is_file()
        assert (tracking / f".cascade/transcript_index/{key}.sqlite").is_file()
        assert not (product / f".cascade/transcript_index/{key}.sqlite").exists()
    finally:
        set_project_context(None)


def test_legacy_import_is_resumable_and_retains_rows(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    path.parent.mkdir(parents=True)
    legacy = [
        {"id": f"old-{index}", "graph_id": "epic_001", "author": "human", "body": str(index), "ts": "2020-01-01T00:00:00Z"}
        for index in range(101)
    ]
    original = b"".join((json.dumps(row) + "\n").encode() for row in legacy)
    path.write_bytes(original)

    with pytest.raises(TranscriptPendingError, match="import is incomplete"):
        append_transcript_message("epic_001", author="system", body="new", root=root)
    append_transcript_message("epic_001", author="system", body="new", root=root)

    assert path.read_bytes().startswith(original)
    assert read_messages("epic_001", root=root)[100] == legacy[100]


def test_oversize_legacy_line_import_resumes_without_rewriting(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    path.parent.mkdir(parents=True)
    legacy = {
        "id": "oversize",
        "graph_id": "epic_001",
        "author": "human",
        "body": "x" * (1024 * 1024),
        "ts": "2020-01-01T00:00:00Z",
    }
    original = (json.dumps(legacy) + "\n").encode()
    path.write_bytes(original)

    with pytest.raises(TranscriptPendingError, match="import is incomplete"):
        append_transcript_message("epic_001", author="system", body="new", root=root)
    append_transcript_message("epic_001", author="system", body="new", root=root)

    assert path.read_bytes().startswith(original)
    assert read_messages("epic_001", root=root)[0] == legacy


def test_torn_legacy_line_remains_pending_and_unchanged(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    path = root / "docs/_war_room/chat/epic_001.jsonl"
    path.parent.mkdir(parents=True)
    torn = b'{"id":"legacy","body":"unfinished"'
    path.write_bytes(torn)

    with pytest.raises(TranscriptPendingError, match="import is incomplete"):
        append_transcript_message("epic_001", author="system", body="new", root=root)

    assert path.read_bytes() == torn


def test_room_move_is_retry_safe_and_changes_incarnation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_transcript_message("epic_001", author="human", body="before", root=root)
    connection = chat_store._connect_index("epic_001", root=root)
    try:
        before = connection.execute(
            "SELECT incarnation FROM state WHERE singleton = 1"
        ).fetchone()[0]
    finally:
        connection.close()
    destination = root / ".cascade/worktrees/epic_epic_001"
    destination.mkdir(parents=True)

    move_transcript_room(
        "epic_001", source_root=root, destination_root=destination, root=root
    )
    # A crash after the copy but before source cleanup is represented by a
    # restored matching source. Retrying must not duplicate or reject it.
    source = root / "docs/_war_room/chat/epic_001.jsonl"
    source.parent.mkdir(parents=True, exist_ok=True)
    destination_path = destination / "docs/_war_room/chat/epic_001.jsonl"
    source.write_bytes(destination_path.read_bytes())
    move_transcript_room(
        "epic_001", source_root=root, destination_root=destination, root=root
    )

    connection = chat_store._connect_index("epic_001", root=root)
    try:
        after = connection.execute(
            "SELECT incarnation FROM state WHERE singleton = 1"
        ).fetchone()[0]
    finally:
        connection.close()
    assert after != before
    assert [json.loads(line)["body"] for line in destination_path.read_text().splitlines()] == ["before"]


@pytest.mark.parametrize(
    "crash_stage",
    ["after_copy", "after_source_remove", "after_owner_switch", "after_index_reset"],
)
def test_room_move_restarts_at_each_durable_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, crash_stage: str
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_transcript_message("epic_001", author="human", body="before", root=root)
    destination = root / ".cascade/worktrees/epic_epic_001"
    destination.mkdir(parents=True)
    owner = {"destination": False}
    crashed = False

    def fault(stage: str) -> None:
        nonlocal crashed
        if stage == crash_stage and not crashed:
            crashed = True
            raise RuntimeError(f"crash at {stage}")

    monkeypatch.setattr(chat_store, "_move_fault", fault)
    with pytest.raises(RuntimeError, match="crash at"):
        move_transcript_room(
            "epic_001", source_root=root, destination_root=destination, root=root,
            switch_owner=lambda: owner.update(destination=True),
        )
    if crash_stage != "after_index_reset":
        with pytest.raises(TranscriptPendingError, match="movement is pending"):
            append_transcript_message(
                "epic_001", author="human", body="must wait", root=root
            )
    move_transcript_room(
        "epic_001", source_root=root, destination_root=destination, root=root,
        switch_owner=lambda: owner.update(destination=True),
    )

    destination_path = destination / "docs/_war_room/chat/epic_001.jsonl"
    assert owner["destination"]
    assert not (root / "docs/_war_room/chat/epic_001.jsonl").exists()
    assert [json.loads(line)["body"] for line in destination_path.read_text().splitlines()] == [
        "before"
    ]
    assert destination_path.read_text().count("\n") == 1
    connection = chat_store._connect_index("epic_001", root=root)
    try:
        assert connection.execute("SELECT count(*) FROM move_intent").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    finally:
        connection.close()


def test_split_root_room_move_keeps_recovery_state_with_tracking(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.board.context import set_project_context
    from cascade.workspace.types import ProjectContext

    product = make_repo(tmp_path / "product", git=False)
    tracking = make_repo(tmp_path / "tracking", git=False)
    destination = product / ".cascade/worktrees/epic_epic_001"
    destination.mkdir(parents=True)
    set_project_context(ProjectContext.split(product, tracking))
    crashed = False

    def fault(stage: str) -> None:
        nonlocal crashed
        if stage == "after_copy" and not crashed:
            crashed = True
            raise RuntimeError("crash after split-root copy")

    try:
        append_transcript_message("epic_001", author="human", body="split", root=product)
        monkeypatch.setattr(chat_store, "_move_fault", fault)
        with pytest.raises(RuntimeError, match="split-root copy"):
            move_transcript_room(
                "epic_001", source_root=product, destination_root=destination,
                root=product,
            )
        key = hashlib.sha256(b"epic_001").hexdigest()
        index = tracking / f".cascade/transcript_index/{key}.sqlite"
        with sqlite3.connect(index) as connection:
            assert connection.execute("SELECT count(*) FROM move_intent").fetchone()[0] == 1
        move_transcript_room(
            "epic_001", source_root=product, destination_root=destination,
            root=product,
        )
        destination_path = destination / "docs/_war_room/chat/epic_001.jsonl"
        assert [
            json.loads(line)["body"]
            for line in destination_path.read_text().splitlines()
        ] == ["split"]
    finally:
        set_project_context(None)


def test_integration_dispatch_and_completion_move_room_under_owner_switch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.integration_worktree import (
        TerminalRetirementProof,
        create_integration_worktree,
        retire_integration_worktree,
    )

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    append_transcript_message("epic_001", author="human", body="before", root=root)

    record = create_integration_worktree(
        "epic",
        "epic_001",
        branch="epic/epic_001",
        base_ref="HEAD",
        trunk=root,
    )

    destination = record.path / "docs/_war_room/chat/epic_001.jsonl"
    assert [json.loads(line)["body"] for line in destination.read_text().splitlines()] == ["before"]
    assert not (root / "docs/_war_room/chat/epic_001.jsonl").exists()
    assert [row["body"] for row in read_messages("epic_001", root=root)] == ["before"]

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.prove_terminal_retirement",
        lambda *_args, **_kwargs: TerminalRetirementProof(True),
    )
    assert retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert not record.path.exists()
    assert [row["body"] for row in read_messages("epic_001", root=root)] == ["before"]


def test_terminal_retirement_resumes_after_owner_switch_deleted_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.integration_worktree import (
        TerminalRetirementProof,
        create_integration_worktree,
        retire_integration_worktree,
    )

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    append_transcript_message("epic_001", author="human", body="before", root=root)
    record = create_integration_worktree(
        "epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=root
    )
    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.prove_terminal_retirement",
        lambda *_args, **_kwargs: TerminalRetirementProof(True),
    )
    crashed = False

    def fault(stage: str) -> None:
        nonlocal crashed
        if stage == "after_owner_switch" and not crashed:
            crashed = True
            raise RuntimeError("crash after terminal owner switch")

    monkeypatch.setattr(chat_store, "_move_fault", fault)
    assert not retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert not record.path.exists()
    assert retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert [row["body"] for row in read_messages("epic_001", root=root)] == ["before"]
    connection = chat_store._connect_index("epic_001", root=root)
    try:
        assert connection.execute("SELECT count(*) FROM move_intent").fetchone()[0] == 0
        assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    finally:
        connection.close()

