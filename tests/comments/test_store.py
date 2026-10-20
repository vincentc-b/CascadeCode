"""Comment sidecar store (task_023)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.comments import section_slug
from cascade.boss.rollup import try_complete_feature, write_closeout
from cascade.comments.store import (
    BlockingNotAllowed,
    NotARoot,
    ResolveNotAllowed,
    comment,
    read_comments,
    reply_comment,
    resolve_comment,
)
from cascade.comments.types import Comment
from cascade.watchdog import read_events
from tests.support import add_doc, make_repo


@pytest.fixture
def board(tmp_path: Path):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    return root


def test_comment_schema_and_monotonic_ids(board: Path) -> None:
    first = comment(
        "feat_001",
        "API contracts",
        "Need clearer errors",
        anchor="mint_task",
        author="human",
        root=board,
    )
    second = comment("feat_001", "Scope", "Looks good", author="human", root=board)
    assert first == "cmt_001"
    assert second == "cmt_002"

    rows = read_comments("feat_001", root=board)
    assert len(rows) == 2
    row = rows[0]
    assert row.id == "cmt_001"
    assert row.doc_id == "feat_001"
    assert row.section == "API contracts"
    assert row.anchor == "mint_task"
    assert row.line_start is None
    assert row.line_end is None
    assert row.doc_sha is None
    assert row.blocks == ()
    assert row.author == "human"
    assert row.body == "Need clearer errors"
    assert row.parent is None
    assert row.state == "open"
    assert row.blocking is False
    assert row.created.tzinfo is not None

    sidecar = board / "docs" / "_comments" / "feat_001.jsonl"
    parsed = json.loads(sidecar.read_text(encoding="utf-8").splitlines()[0])
    assert parsed["created"].endswith("Z") or "+" in parsed["created"]
    assert parsed["line_start"] is None
    assert parsed["line_end"] is None
    assert parsed["doc_sha"] is None
    assert parsed["blocks"] == []


def test_legacy_sidecar_without_new_keys(board: Path) -> None:
    sidecar = board / "docs" / "_comments" / "feat_001.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    legacy = {
        "id": "cmt_001",
        "doc_id": "feat_001",
        "section": "Scope",
        "anchor": None,
        "author": "human",
        "body": "legacy row",
        "parent": None,
        "state": "open",
        "blocking": False,
        "created": "2026-01-15T12:00:00+00:00",
    }
    sidecar.write_text(json.dumps(legacy) + "\n", encoding="utf-8")

    rows = read_comments("feat_001", root=board)
    assert len(rows) == 1
    row = rows[0]
    assert row.line_start is None
    assert row.line_end is None
    assert row.doc_sha is None
    assert row.blocks == ()

    resolve_comment("feat_001", "cmt_001", author="human", root=board)
    row = next(r for r in read_comments("feat_001", root=board) if r.id == "cmt_001")
    assert row.state == "resolved"
    assert row.line_start is None
    assert row.line_end is None
    assert row.doc_sha is None
    assert row.blocks == ()


def test_new_fields_round_trip(board: Path) -> None:
    cmt_id = comment(
        "feat_001",
        "Scope",
        "anchored",
        line_start=3,
        line_end=5,
        doc_sha="abc",
        blocks=["task_001"],
        author="human",
        root=board,
    )
    row = next(r for r in read_comments("feat_001", root=board) if r.id == cmt_id)
    assert row.line_start == 3
    assert row.line_end == 5
    assert row.doc_sha == "abc"
    assert row.blocks == ("task_001",)

    sidecar = board / "docs" / "_comments" / "feat_001.jsonl"
    parsed = json.loads(sidecar.read_text(encoding="utf-8").splitlines()[-1])
    assert parsed["line_start"] == 3
    assert parsed["line_end"] == 5
    assert parsed["doc_sha"] == "abc"
    assert parsed["blocks"] == ["task_001"]

    reloaded = Comment.from_dict(parsed)
    assert reloaded.line_start == 3
    assert reloaded.line_end == 5
    assert reloaded.doc_sha == "abc"
    assert reloaded.blocks == ("task_001",)


@pytest.mark.parametrize(
    ("heading", "expected"),
    [
        ("Memory layout", "memory-layout"),
        ("  Open  questions ", "open-questions"),
        ("A_b/C", "a-b-c"),
        ("--x--", "x"),
    ],
)
def test_section_slug(heading: str, expected: str) -> None:
    result = section_slug(heading)
    assert result == expected
    assert "_" not in result


def test_blocking_human_only(board: Path) -> None:
    comment(
        "feat_001",
        "Scope",
        "Block me",
        blocking=True,
        author="human",
        root=board,
    )
    rows = read_comments("feat_001", root=board)
    assert rows[-1].blocking is True

    with pytest.raises(BlockingNotAllowed):
        comment(
            "feat_001",
            "Scope",
            "nope",
            blocking=True,
            author="feature_lead",
            root=board,
        )


@pytest.mark.parametrize("author", ["feature_lead", "feature_architect", "epic_manager"])
def test_comment_posted_to_owning_graph(board: Path, author: str) -> None:
    doc_id = "feat_001" if author.startswith("feature") else "epic_001"
    comment(doc_id, "Section", "body", author=author, root=board)
    events, _ = read_events(doc_id, 0, root=board)
    assert [event.type for event in events] == ["CommentPosted"]
    assert events[0].payload["doc_id"] == doc_id
    assert events[0].dest == doc_id


def test_toast_when_human_detached(board: Path) -> None:
    comment(
        "feat_001",
        "Scope",
        "async",
        author="human",
        root=board,
        is_attached=lambda _gid: False,
    )
    events, _ = read_events("war_room", 0, root=board)
    assert any(
        event.type == "Toast" and event.payload.get("kind") == "comment"
        for event in events
    )


def test_no_toast_when_attached_or_agent(board: Path) -> None:
    comment(
        "feat_001",
        "Scope",
        "sync",
        author="human",
        root=board,
        is_attached=lambda gid: gid == "feat_001",
    )
    comment("feat_001", "Scope", "agent", author="feature_lead", root=board)
    events, _ = read_events("war_room", 0, root=board)
    assert not events


def test_reply_and_resolve(board: Path) -> None:
    root_id = comment("feat_001", "API", "question", author="human", root=board)
    reply_id = reply_comment(
        "feat_001",
        root_id,
        "answer",
        author="feature_lead",
        root=board,
    )
    rows = read_comments("feat_001", root=board)
    reply = next(row for row in rows if row.id == reply_id)
    assert reply.parent == root_id
    assert reply.state == "open"

    resolve_comment("feat_001", root_id, author="human", root=board)
    rows = read_comments("feat_001", root=board)
    root_row = next(row for row in rows if row.id == root_id)
    reply_row = next(row for row in rows if row.id == reply_id)
    assert root_row.state == "resolved"
    assert reply_row.state == "resolved"

    feat_events, _ = read_events("feat_001", 0, root=board)
    types = [event.type for event in feat_events]
    assert "CommentPosted" in types
    assert "CommentReplied" in types
    assert "CommentResolved" in types


def test_human_resolve_cascades_open_human_reply_for_closeout(board: Path) -> None:
    from tests.support import add_doc

    add_doc(
        board,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )
    write_closeout("feat_001", "Ready to ship.", root=board)
    root_id = comment("feat_001", "Scope", "question", author="human", root=board)
    reply_id = reply_comment(
        "feat_001",
        root_id,
        "follow-up",
        author="human",
        root=board,
    )
    assert try_complete_feature("feat_001", root=board) is False

    resolve_comment("feat_001", root_id, author="human", root=board)
    reply_row = next(row for row in read_comments("feat_001", root=board) if row.id == reply_id)
    assert reply_row.state == "resolved"
    assert try_complete_feature("feat_001", root=board) is True


def test_agent_author_cannot_resolve(board: Path) -> None:
    root_id = comment("feat_001", "Scope", "note", author="human", root=board)
    with pytest.raises(ResolveNotAllowed):
        resolve_comment("feat_001", root_id, author="feature_lead", root=board)


def test_resolve_on_reply_raises_not_a_root(board: Path) -> None:
    root_id = comment("feat_001", "Scope", "note", author="human", root=board)
    reply_id = reply_comment(
        "feat_001",
        root_id,
        "reply",
        author="human",
        root=board,
    )
    with pytest.raises(NotARoot):
        resolve_comment("feat_001", reply_id, author="human", root=board)


def test_resolve_idempotent_when_root_already_resolved(board: Path) -> None:
    root_id = comment("feat_001", "Scope", "note", author="human", root=board)
    resolve_comment("feat_001", root_id, author="human", root=board)
    resolve_comment("feat_001", root_id, author="human", root=board)
    feat_events, _ = read_events("feat_001", 0, root=board)
    assert sum(event.type == "CommentResolved" for event in feat_events) == 1
