"""Planning turns append to War Room chat sidecars."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.war_room.chat_store import read_messages
from cascade.war_room.planning_transcript import (
    append_planning_turn_to_chat,
    sync_planning_transcript_to_chat,
)
from tests.support import add_doc, make_repo


def test_append_planning_turn_writes_agent_lines(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")

    append_planning_turn_to_chat(
        "epic_001",
        [
            {"role": "human", "content": "hello"},
            {"role": "epic_manager", "content": "Manager reply."},
            {"role": "epic_architect", "content": "Architect reply."},
        ],
        root=root,
    )

    rows = read_messages("epic_001", root=root)
    assert len(rows) == 2
    assert rows[0]["author"] == "epic_manager"
    assert rows[1]["author"] == "epic_architect"


def test_failed_planning_turn_shows_bounded_operator_message(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_planning_turn_to_chat(
        "epic_001",
        [{
            "role": "epic_manager",
            "content": "epic_manager: turn failed — prompt containing private text\n"
            'ERROR: {"message":"Unsupported service_tier: flex"}',
        }],
        root=root,
    )
    rows = read_messages("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0]["author"] == "system"
    assert "rejected Flex service tier" in rows[0]["body"]
    assert "private text" not in rows[0]["body"]


def test_sync_transcript_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    from cascade.epic.graph import ensure_epic_graph
    from cascade.workspace.kickoff import install_kickoff

    install_kickoff(root)
    # Seed graph without running models (stage messages directly)
    graph = ensure_epic_graph("epic_001", root=root)
    from cascade.epic.checkpoint import thread_config

    graph.update_state(
        thread_config("epic_001"),
        {
            "epic_id": "epic_001",
            "messages": [
                {"role": "human", "content": "hi"},
                {"role": "epic_manager", "content": "Acknowledged."},
            ],
            "last_queue_offset": 0,
        },
    )
    sync_planning_transcript_to_chat("epic_001", root=root)
    rows = read_messages("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0]["author"] == "epic_manager"
    sync_planning_transcript_to_chat("epic_001", root=root)
    assert len(read_messages("epic_001", root=root)) == 1


def test_sync_backfills_failed_turn_without_raw_output(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    from cascade.epic.graph import ensure_epic_graph
    from cascade.epic.checkpoint import thread_config

    graph = ensure_epic_graph("epic_001", root=root)
    graph.update_state(thread_config("epic_001"), {
        "epic_id": "epic_001",
        "messages": [{"role": "epic_manager", "content": "epic_manager: turn failed — secret prompt"}],
        "last_queue_offset": 0,
    })
    sync_planning_transcript_to_chat("epic_001", root=root)
    sync_planning_transcript_to_chat("epic_001", root=root)
    rows = read_messages("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0]["author"] == "system"
    assert "secret prompt" not in rows[0]["body"]


def test_backlog_snapshot_transcript_uses_local_chat_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.war_room import chat_store

    root = make_repo(tmp_path)
    snapshot = root / ".cascade" / "backlog_snapshot"
    snapshot.mkdir(parents=True)
    monkeypatch.setattr(chat_store, "resolve_doc_worktree", lambda *_args, **_kwargs: snapshot)

    chat_store.append_transcript_message(
        "epic_001", author="system", body="Planning failed.", root=root
    )

    assert read_messages("epic_001", root=root)[0]["body"] == "Planning failed."
    assert not (snapshot / "docs" / "_war_room" / "chat" / "epic_001.jsonl").exists()
