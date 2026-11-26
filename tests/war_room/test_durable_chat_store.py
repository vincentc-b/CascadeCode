"""Cross-process and crash-boundary coverage for the transcript writer."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from cascade.war_room import chat_store
from cascade.war_room.chat_store import (
    TranscriptPendingError,
    append_transcript_message,
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

