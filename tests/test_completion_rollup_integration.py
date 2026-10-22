"""Lifecycle integration coverage for completion rollup and recovery (task_006)."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.automation import advance_work, poll_reviews, reset_automation_memory
from cascade.board.store import move_doc, read_doc, write_doc
from cascade.boss.rollup import on_task_merged
from cascade.watchdog.events import read_events
from tests.support import add_doc, make_repo


def _enable_automation(root: Path) -> None:
    root.joinpath("cascade.toml").write_text(
        "[automation]\nenabled = true\npoll_seconds = 1\n",
        encoding="utf-8",
    )


def _single_task_feature(root: Path) -> None:
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


def _write_open_review(root: Path, *, closed: bool = False) -> None:
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
                    "closed": closed,
                }
            }
        ),
        encoding="utf-8",
    )


def _feature_completed_events(epic_id: str, *, root: Path) -> list[object]:
    events, _ = read_events(epic_id, 0, root=root)
    return [event for event in events if event.type == "FeatureCompleted"]


def _epic_completed_events(*, root: Path) -> list[object]:
    events, _ = read_events("war_room", 0, root=root)
    return [event for event in events if event.type == "EpicCompleted"]


def test_task_merge_leaves_open_review_without_feature_completed_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _single_task_feature(root)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr("cascade.review.ensure_feature_review", lambda *_args, **_kwargs: None)

    on_task_merged("task_001", root=root)

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"
    assert feature.meta.path.parent.name == "2_active"
    assert _feature_completed_events("epic_001", root=root) == []


def test_tasks_first_then_merged_review_via_poll_reviews(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    _single_task_feature(root)
    _write_open_review(root, closed=False)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    move_doc("feat_001", "completed", root=root)
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_args, **_kwargs: {"state": "merged", "comments": []},
    )
    monkeypatch.setattr(
        "cascade.review.get_integration_worktree",
        lambda *_args, **_kwargs: SimpleNamespace(path=root),
    )
    monkeypatch.setattr("cascade.review.fast_forward_branch", lambda *_args, **_kwargs: "sha")

    poll_reviews(root)

    assert len(_feature_completed_events("epic_001", root=root)) == 1
    state = json.loads((root / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    assert state["feat_001"]["closed"] is True


def test_merge_recorded_before_task_merge_converges_on_task_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
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
        children=["task_001"],
    )
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    _write_open_review(root, closed=True)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr("cascade.review.ensure_feature_review", lambda *_args, **_kwargs: None)

    on_task_merged("task_001", root=root)

    assert _feature_completed_events("epic_001", root=root) == []

    move_doc("task_001", "completed", root=root)
    on_task_merged("task_001", root=root)

    assert len(_feature_completed_events("epic_001", root=root)) == 1


def test_advance_work_completes_epic_when_all_children_terminal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    monkeypatch.setattr(
        "cascade.automation.reconcile_approval_dispatch",
        lambda _root: {"features": [], "tasks": []},
    )
    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", lambda _root: [])
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

    advance_work(root)

    assert read_doc("epic_001", root=root).meta.status == "completed"
    assert len(_epic_completed_events(root=root)) == 1


def test_incomplete_persisted_follow_up_blocks_epic_via_advance_work(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    monkeypatch.setattr(
        "cascade.automation.reconcile_approval_dispatch",
        lambda _root: {"features": [], "tasks": []},
    )
    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", lambda _root: [])
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

    advance_work(root)

    assert read_doc("epic_001", root=root).meta.status == "active"
    assert _epic_completed_events(root=root) == []


def test_unminted_follow_up_suggestion_allows_epic_via_on_task_merged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Only child",
        tier="feature",
        status="completed",
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
    epic = read_doc("epic_001", root=root)
    epic.body = (
        epic.body.rstrip()
        + "\n\n## Follow-up\n\nSuggested `feat_002` (not accepted or minted).\n"
    )
    write_doc(epic, root=root)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: False)

    on_task_merged("task_001", root=root)

    assert read_doc("epic_001", root=root).meta.status == "completed"
    assert len(_epic_completed_events(root=root)) == 1


def test_repeated_advance_work_does_not_duplicate_completion_events(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    monkeypatch.setattr(
        "cascade.automation.reconcile_approval_dispatch",
        lambda _root: {"features": [], "tasks": []},
    )
    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", lambda _root: [])
    _single_task_feature(root)
    from cascade.boss.rollup import write_closeout

    write_closeout("feat_001", "Done.", root=root)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: False)

    advance_work(root)
    advance_work(root)

    assert len(_feature_completed_events("epic_001", root=root)) == 1


def test_watchdog_startup_recovery_completes_stalled_rollups(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    monkeypatch.setattr("cascade.task.wiring.restore_active_task_runs", lambda _root: [])
    monkeypatch.setattr(
        "cascade.automation.advance_work", lambda _root: {"features": [], "tasks": []}
    )
    monkeypatch.setattr("cascade.watchdog.loop.watchdog_tick", lambda *_args, **_kwargs: None)

    from cascade.watchdog.loop import run_watchdog

    run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)

    assert read_doc("epic_001", root=root).meta.status == "completed"
    assert len(_epic_completed_events(root=root)) == 1

    run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)

    assert len(_epic_completed_events(root=root)) == 1
