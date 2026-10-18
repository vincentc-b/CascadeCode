"""Integration worktrees at activate and dispatch (task_065)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    read_events,
    register_boot_hook,
)
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_branch,
    integration_worktree_path,
    load_registry,
    merged_board,
    repair_missing_worktree,
    scan_active_markdown_roots,
)
from cascade.workspace.up import resume_legally_active_graphs
from tests.support import add_doc, make_repo


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def _chain(root: Path) -> None:
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok


def test_activate_epic_creates_branch_and_worktree(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")

    result = activate_epic("epic_001", "human", root=root)
    assert result.ok is True
    branch = integration_branch("epic", "epic_001")
    assert _branch_exists(root, branch)
    wt = integration_worktree_path("epic", "epic_001", trunk=root)
    assert wt.is_dir()
    entry = get_integration_worktree(root, "epic", "epic_001")
    assert entry is not None
    assert entry.branch == branch
    assert entry.path == wt.resolve()

    live = read_doc("epic_001", root=root)
    assert live.meta.status == "active"
    assert live.meta.path.parent.name == "2_active"
    assert live.meta.path.is_relative_to(wt)

    trunk_board = read_doc("epic_001", root=root)
    pointer_path = root / "docs" / "epics" / "2_active"
    assert any(pointer_path.glob("epic_001_*.md"))
    pointer_file = next(pointer_path.glob("epic_001_*.md"))
    text = pointer_file.read_text(encoding="utf-8")
    assert "integration_branch:" in text
    assert branch in text


def test_activate_refuses_without_brief_commit(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    path = root / "docs" / "epics" / "1_backlog" / "epic_001_epic.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\nid: epic_001\ntitle: Epic\ntier: epic\nstatus: backlog\n"
        "parent: null\nchildren: []\ndepends_on: []\nowners: []\n"
        "skills: []\nparent_rev: null\ncreated: 2026-10-09\nupdated: 2026-10-09\n---\n# Epic\n",
        encoding="utf-8",
    )

    refused = activate_epic("epic_001", "human", root=root)
    assert refused.ok is False
    assert refused.reason == "brief_not_on_trunk"


def test_dispatch_stacked_branches_and_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    assert _branch_exists(root, integration_branch("feature", "feat_001"))
    assert _branch_exists(root, integration_branch("task", "task_001"))
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    task_wt = integration_worktree_path("task", "task_001", trunk=root)
    assert feat_wt.is_dir()
    assert task_wt.is_dir()

    task_doc = read_doc("task_001", root=root)
    assert task_doc.meta.path.is_relative_to(feat_wt)


def test_repair_restores_worktree_without_new_dispatch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    events_before, _ = read_events("feat_001", 0, root=root)
    task_events_before, _ = read_events("task_001", 0, root=root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    shutil.rmtree(feat_wt)
    assert not feat_wt.is_dir()

    resume_legally_active_graphs(root)
    assert feat_wt.is_dir()

    events_after, _ = read_events("feat_001", 0, root=root)
    task_events_after, _ = read_events("task_001", 0, root=root)
    assert [event.type for event in events_after] == [event.type for event in events_before]
    assert [event.type for event in task_events_after] == [event.type for event in task_events_before]

    repaired = repair_missing_worktree("feature", "feat_001", trunk=root)
    assert repaired is not None
    assert feat_wt.is_dir()


def test_registry_persists_entries(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    assert activate_epic("epic_001", "human", root=root).ok
    entries = load_registry(root)
    assert len(entries) == 1
    assert entries[0].work_id == "epic_001"
    assert (root / ".cascade" / "worktrees.json").is_file()


def test_merged_board_scans_each_checkout_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    _chain(root)

    import cascade.workspace.integration_worktree as worktrees

    calls: list[Path] = []
    real_list = worktrees.list_board

    def _counting(path: Path):
        calls.append(Path(path).resolve())
        return real_list(path)

    monkeypatch.setattr(worktrees, "list_board", _counting)
    board = merged_board(root)
    roots = [path.resolve() for path in scan_active_markdown_roots(root)]
    assert calls == roots
    assert board.by_id["epic_001"].path.parent.name == "2_active"
    assert board.by_id["feat_001"].path.is_relative_to(
        integration_worktree_path("feature", "feat_001", trunk=root)
    )
