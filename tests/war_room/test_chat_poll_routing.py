"""Chat polling locates sidecars without scanning the merged planning board."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.war_room.chat_store import read_messages
from cascade.workspace.integration_worktree import (
    IntegrationWorktree,
    integration_worktree_path,
    save_registry,
)
from tests.support import add_doc, make_repo


def _message(path: Path, graph_id: str, body: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"id": body, "graph_id": graph_id, "body": body}) + "\n",
        encoding="utf-8",
    )


def _register(root: Path, kind: str, work_id: str, path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    save_registry(
        root,
        [
            IntegrationWorktree(
                kind=kind,  # type: ignore[arg-type]
                work_id=work_id,
                branch=f"{kind}/{work_id}",
                path=path,
                base_sha="deadbeef",
            )
        ],
    )


def test_repeated_chat_reads_do_not_build_merged_board(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    feature_root = integration_worktree_path("feature", "feat_001", trunk=root)
    _register(root, "feature", "feat_001", feature_root)
    _message(
        feature_root / "docs" / "_war_room" / "chat" / "feat_001.jsonl",
        "feat_001",
        "live feature room",
    )
    _message(
        root / "docs" / "_war_room" / "chat" / "feat_001.jsonl",
        "feat_001",
        "stale trunk room",
    )

    def fail_merged_board(*_args, **_kwargs):
        raise AssertionError("chat GET must not build the merged board")

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.merged_board", fail_merged_board
    )
    monkeypatch.setattr(
        "cascade.war_room.chat_store.resolve_doc_worktree", fail_merged_board
    )

    assert [row["body"] for row in read_messages("feat_001", root=root)] == [
        "live feature room"
    ]
    assert [row["body"] for row in read_messages("feat_001", root=root)] == [
        "live feature room"
    ]


def test_completed_epic_chat_remains_trunk_authoritative(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Done", tier="epic", status="completed")
    epic_root = integration_worktree_path("epic", "epic_001", trunk=root)
    _register(root, "epic", "epic_001", epic_root)
    _message(
        epic_root / "docs" / "_war_room" / "chat" / "epic_001.jsonl",
        "epic_001",
        "stale epic room",
    )
    _message(
        root / "docs" / "_war_room" / "chat" / "epic_001.jsonl",
        "epic_001",
        "closed epic room",
    )

    assert [row["body"] for row in read_messages("epic_001", root=root)] == [
        "closed epic room"
    ]


def test_trunk_only_feature_chat_routes_to_registered_parent_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Draft feature",
        tier="feature",
        parent="epic_001",
    )
    epic_root = integration_worktree_path("epic", "epic_001", trunk=root)
    _register(root, "epic", "epic_001", epic_root)
    _message(
        epic_root / "docs" / "_war_room" / "chat" / "feat_001.jsonl",
        "feat_001",
        "parent epic room",
    )

    assert [row["body"] for row in read_messages("feat_001", root=root)] == [
        "parent epic room"
    ]


def test_task_read_follows_parent_feature_and_unknown_id_stays_on_trunk(
    tmp_path: Path,
) -> None:
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
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    feature_root = integration_worktree_path("feature", "feat_001", trunk=root)
    _register(root, "feature", "feat_001", feature_root)
    _message(
        feature_root / "docs" / "_war_room" / "chat" / "task_001.jsonl",
        "task_001",
        "legacy task room",
    )
    _message(
        root / "docs" / "_war_room" / "chat" / "external_graph.jsonl",
        "external_graph",
        "unknown graph room",
    )

    assert [row["body"] for row in read_messages("task_001", root=root)] == [
        "legacy task room"
    ]
    assert [row["body"] for row in read_messages("external_graph", root=root)] == [
        "unknown graph room"
    ]
