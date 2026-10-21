"""Completion reconciliation wired into lifecycle hooks (task_005)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from cascade.automation import advance_work, poll_reviews, reset_automation_memory
from cascade.boss.rollup import on_task_merged, write_closeout
from cascade.board.store import read_doc
from tests.support import add_doc, make_repo


def _enable_automation(root: Path) -> None:
    root.joinpath("cascade.toml").write_text(
        "[automation]\nenabled = true\npoll_seconds = 1\n",
        encoding="utf-8",
    )


def _feature_ready_to_complete(root: Path) -> None:
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
    write_closeout("feat_001", "Done.", root=root)


def test_on_task_merged_runs_shared_reconciler(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _feature_ready_to_complete(root)
    calls: list[Path] = []
    real = __import__(
        "cascade.completion_reconcile", fromlist=["reconcile_completion_with_prompts"]
    ).reconcile_completion_with_prompts

    def _track(*, root: Path | None = None):
        repo = root if root is not None else Path(".")
        calls.append(repo.resolve())
        return real(root=root)

    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        _track,
    )

    on_task_merged("task_001", root=root)

    assert calls == [root.resolve()]
    assert read_doc("feat_001", root=root).meta.status == "completed"


def test_advance_work_reconciles_before_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    _feature_ready_to_complete(root)
    reconciled: list[Path] = []
    from cascade.completion_reconcile import reconcile_completion_with_prompts as real_reconcile

    def _reconcile(*, root: Path | None = None):
        repo = (root if root is not None else Path(".")).resolve()
        reconciled.append(repo)
        return real_reconcile(root=root)

    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        _reconcile,
    )
    monkeypatch.setattr(
        "cascade.automation.reconcile_approval_dispatch",
        lambda _root: {"features": [], "tasks": []},
    )
    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", lambda _root: [])

    advance_work(root)

    assert reconciled == [root.resolve()]


def test_poll_reviews_reconciles_after_review_poll(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    reset_automation_memory()
    order: list[str] = []

    monkeypatch.setattr(
        "cascade.review.poll_feature_reviews",
        lambda _root: order.append("poll"),
    )
    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        lambda *, root=None: order.append("reconcile") or {"features": [], "epics": []},
    )

    poll_reviews(root)

    assert order == ["poll", "reconcile"]


def test_watchdog_startup_reconciles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    reconciled = MagicMock(return_value={"features": [], "epics": []})
    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        reconciled,
    )
    monkeypatch.setattr("cascade.task.wiring.restore_active_task_runs", lambda _root: [])
    monkeypatch.setattr("cascade.automation.advance_work", lambda _root: {"features": [], "tasks": []})
    monkeypatch.setattr("cascade.watchdog.loop.watchdog_tick", lambda *_args, **_kwargs: None)

    from cascade.watchdog.loop import run_watchdog

    run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)

    reconciled.assert_called_once_with(root=root.resolve())
