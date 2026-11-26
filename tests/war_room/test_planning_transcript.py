"""Planning turns append to War Room chat sidecars."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.war_room.chat_store import read_messages
from cascade.war_room.planning_transcript import (
    append_planning_turn_to_chat,
    sync_planning_transcript_to_chat,
)
from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import merged_board
from tests.support import SyntheticDependencyLifecycle, add_doc, make_repo


def _epic_row(payload: dict, epic_id: str) -> dict:
    for column in ("1_backlog", "2_active", "3_completed"):
        for row in payload["epics"][column]:
            if row["id"] == epic_id:
                return row
    raise KeyError(epic_id)


def test_historical_blocker_does_not_override_synthetic_live_completion(
    synthetic_dependency_lifecycle: SyntheticDependencyLifecycle,
) -> None:
    scenario = synthetic_dependency_lifecycle
    append_planning_turn_to_chat(
        scenario.owner_id,
        [
            {
                "role": "epic_manager",
                "content": f"Blocked by {scenario.dependency_id}.",
            }
        ],
        root=scenario.root,
    )

    board = merged_board(scenario.root)
    payload = board_view_from_index(board, root=scenario.root)
    row = _epic_row(payload, scenario.owner_id)

    assert read_messages(scenario.owner_id, root=scenario.root)[0]["body"] == (
        f"Blocked by {scenario.dependency_id}."
    )
    assert row["dependency_status"]["outcome"] == "satisfied"
    assert row["plan_readiness"]["dependency_status"] == row["dependency_status"]
    assert all(
        blocker["category"] != "dependency"
        for blocker in row["plan_readiness"]["blockers"]
    )


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


def test_direct_append_and_later_checkpoint_backfill_share_durable_message_id(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    from cascade.epic.checkpoint import thread_config
    from cascade.epic.graph import ensure_epic_graph

    graph = ensure_epic_graph("epic_001", root=root)
    config = thread_config("epic_001")
    reply = {"role": "epic_manager", "content": "Final summary.", "id": "reply-1"}
    graph.update_state(
        config,
        {"epic_id": "epic_001", "messages": [reply], "last_queue_offset": 0},
    )
    committed = graph.get_state(config)
    append_planning_turn_to_chat(
        "epic_001",
        [reply],
        root=root,
        checkpoint_config=committed.config,
        message_offset=0,
    )

    # A later checkpoint changes the lineage head, as model-override cleanup does.
    graph.update_state(config, {"last_queue_offset": 1})
    sync_planning_transcript_to_chat("epic_001", root=root)

    rows = read_messages("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0]["body"] == "Final summary."
    assert rows[0]["checkpoint_message_id"] == "reply-1"
    assert rows[0]["source_key"] == "role_reply:epic_001:message:reply-1"


def test_distinct_same_text_replies_keep_separate_checkpoint_identity(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    append_planning_turn_to_chat(
        "epic_001",
        [
            {"role": "epic_manager", "content": "Same.", "id": "reply-1"},
            {"role": "epic_manager", "content": "Same.", "id": "reply-2"},
        ],
        root=root,
        checkpoint_config={"configurable": {"checkpoint_id": "checkpoint-1"}},
    )

    rows = read_messages("epic_001", root=root)
    assert [row["body"] for row in rows] == ["Same.", "Same."]
    assert [row["checkpoint_message_id"] for row in rows] == ["reply-1", "reply-2"]


def test_legacy_author_body_match_is_labeled_unknown_without_claiming_identity(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    from cascade.epic.checkpoint import thread_config
    from cascade.epic.graph import ensure_epic_graph
    from cascade.war_room.chat_store import append_transcript_message

    append_transcript_message(
        "epic_001", author="epic_manager", body="Older reply.", root=root
    )
    graph = ensure_epic_graph("epic_001", root=root)
    graph.update_state(
        thread_config("epic_001"),
        {
            "epic_id": "epic_001",
            "messages": [
                {"role": "epic_manager", "content": "Older reply.", "id": "reply-1"}
            ],
            "last_queue_offset": 0,
        },
    )

    sync_planning_transcript_to_chat("epic_001", root=root)
    sync_planning_transcript_to_chat("epic_001", root=root)

    rows = read_messages("epic_001", root=root)
    assert len(rows) == 1
    assert rows[0]["provenance"] == "legacy_unknown"
    assert rows[0]["occurred_at"] is None
    assert rows[0]["source_key"] is None


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
