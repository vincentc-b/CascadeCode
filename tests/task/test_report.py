"""Branch diff summary and awaiting-merge Toast (task_036)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.task.report import mark_awaiting_merge, summarize_diff
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.war_room.toasts import events_to_toasts
from cascade.watchdog.events import read_events
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _report_test_isolation() -> None:
    clear_task_runs()
    yield
    clear_task_runs()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


def _task_run_with_change(tmp_path: Path) -> tuple[Path, object]:
    root = make_repo(tmp_path)
    _initial_commit(root)
    run = create_task_worktree(
        "task_036",
        root=root,
        parent_rev=None,
        skills=[],
    )
    _commit_in_worktree(run.worktree, "task_change.txt", "delta\n", "task work")
    return root, run


def test_summarize_diff_shape(tmp_path: Path) -> None:
    root, run = _task_run_with_change(tmp_path)

    summary = summarize_diff(run, root=root)

    assert summary
    assert "task_change.txt" in summary
    assert "diff --git" not in summary
    assert "+++ " not in summary
    assert len(summary.splitlines()) <= 20


def test_mark_awaiting_merge_state_toast_and_mapping(tmp_path: Path) -> None:
    root, run = _task_run_with_change(tmp_path)
    assert run.state == "booting"

    mark_awaiting_merge("task_036", run, root=root)

    assert run.state == "awaiting_merge"

    events, _ = read_events("war_room", 0, root=root)
    assert len(events) == 1
    toast = events[0]
    assert toast.type == "Toast"
    assert toast.payload["kind"] == "task_ready"
    assert toast.payload["id"] == "task_036"
    body = toast.payload.get("message") or toast.payload.get("body")
    assert isinstance(body, str)
    assert "task/task_036" in body
    assert "task_change.txt" in body

    mapped = events_to_toasts(events)
    assert len(mapped) == 1
    assert mapped[0]["kind"] == "task_ready"
    assert mapped[0]["body"] == body
    assert mapped[0]["link"] == "/api/doc/task_036"


def test_mark_awaiting_merge_no_task_merged_event(tmp_path: Path) -> None:
    root, run = _task_run_with_change(tmp_path)

    mark_awaiting_merge("task_036", run, root=root)

    queue_dir = root / "docs" / "_queue"
    if queue_dir.is_dir():
        for path in queue_dir.glob("*.jsonl"):
            events, _ = read_events(path.stem, 0, root=root)
            assert not any(event.type == "TaskMerged" for event in events)
