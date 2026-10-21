"""Completion reconciliation rules (task_004)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.board.store import move_doc, read_doc, write_doc
from cascade.boss.epic_complete import try_complete_epic
from cascade.boss.rollup import try_complete_feature, write_closeout
from cascade.completion_reconcile import reconcile_completion
from cascade.watchdog.events import read_events
from tests.support import add_doc, make_repo


def _feature_with_tasks(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="completed",
        parent="feat_001",
    )


def test_open_merge_request_blocks_terminal_feature_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _feature_with_tasks(root)
    write_closeout("feat_001", "Done.", root=root)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr("cascade.review.ensure_feature_review", lambda *_args, **_kwargs: None)

    reconcile_completion(root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert not any(event.type == "FeatureCompleted" for event in epic_events)


def test_merged_review_completes_feature_via_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _feature_with_tasks(root)
    move_doc("feat_001", "completed", root=root)
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/o/r/pull/1",
                    "number": "1",
                    "forge": "github",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_001",
                    "draft": False,
                    "closed": True,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)

    first = reconcile_completion(root)
    assert first["features"] == ["feat_001"]

    epic_events, _ = read_events("epic_001", 0, root=root)
    completed = [event for event in epic_events if event.type == "FeatureCompleted"]
    assert len(completed) == 1

    second = reconcile_completion(root)
    assert second["features"] == []
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert len([e for e in epic_events if e.type == "FeatureCompleted"]) == 1


def test_reconcile_completes_epic_when_all_persisted_children_done(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="One",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Two",
        tier="feature",
        status="completed",
        parent="epic_001",
    )

    result = reconcile_completion(root)

    assert result["epics"] == ["epic_001"]
    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "completed"
    war_events, _ = read_events("war_room", 0, root=root)
    assert len([e for e in war_events if e.type == "EpicCompleted"]) == 1


def test_incomplete_persisted_follow_up_blocks_epic_completion(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Done",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Follow-up",
        tier="feature",
        status="active",
        parent="epic_001",
    )

    result = reconcile_completion(root)

    assert result["epics"] == []
    assert read_doc("epic_001", root=root).meta.status == "active"
    assert try_complete_epic("epic_001", root=root) is False


def test_unminted_follow_up_suggestion_does_not_block_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Only child",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    epic = read_doc("epic_001", root=root)
    epic.body = (
        epic.body.rstrip()
        + "\n\n## Follow-up\n\nSuggested `feat_002` (not accepted or minted).\n"
    )
    write_doc(epic, root=root)

    assert reconcile_completion(root)["epics"] == ["epic_001"]


def test_non_review_feature_completes_on_reconcile(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _feature_with_tasks(root)
    write_closeout("feat_001", "Shipped.", root=root)

    result = reconcile_completion(root)

    assert result["features"] == ["feat_001"]
    assert read_doc("feat_001", root=root).meta.status == "completed"
    epic_events, _ = read_events("epic_001", 0, root=root)
    assert any(event.type == "FeatureCompleted" for event in epic_events)


def test_try_complete_feature_review_merged_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _feature_with_tasks(root)
    move_doc("feat_001", "completed", root=root)

    assert try_complete_feature("feat_001", root=root, review_merged=True) is True
    assert try_complete_feature("feat_001", root=root, review_merged=True) is True

    epic_events, _ = read_events("epic_001", 0, root=root)
    assert len([e for e in epic_events if e.type == "FeatureCompleted"]) == 1
