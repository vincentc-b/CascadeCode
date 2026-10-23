"""Integration worktrees at activate and dispatch (task_065)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    read_events,
)
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    get_integration_worktree,
    invalidate_merged_board,
    integration_branch,
    integration_worktree_path,
    load_registry,
    merged_board,
    repair_missing_worktree,
    retire_integration_worktree,
    retire_terminal_registered_worktrees,
    scan_active_markdown_roots,
    save_registry,
    unregister_missing_integration_worktree,
)
from cascade.workspace.integration_worktree import IntegrationWorktree
from cascade.workspace.up import resume_legally_active_graphs
from tests.support import add_doc, make_repo, approve_board_feature


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def _initial_commit(root: Path) -> None:
    readme = root / "README.md"
    readme.write_text("workspace\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True
    )


def _chain(root: Path) -> None:
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
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


def test_active_task_run_is_restored_after_process_restart(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    from cascade.task.wiring import restore_active_task_runs
    from cascade.task.worktree import clear_task_runs, get_task_run

    clear_task_runs()
    assert get_task_run("task_001") is None

    assert restore_active_task_runs(root) == [("task_001", "feat_001")]
    restored = get_task_run("task_001")
    assert restored is not None
    assert restored.state == "coding"
    assert restore_active_task_runs(root) == []


def test_active_task_with_fresh_live_lease_is_not_resumed_twice(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    from cascade.task.execution import mark_running
    from cascade.task.wiring import restore_active_task_runs
    from cascade.task.worktree import clear_task_runs, get_task_run

    mark_running("task_001", root=root)
    clear_task_runs()
    assert restore_active_task_runs(root) == []
    assert get_task_run("task_001") is None


def test_active_task_with_stale_lease_is_reclaimed_once(tmp_path: Path) -> None:
    from datetime import datetime, timedelta, timezone

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    from cascade.task.execution import mark_running
    from cascade.task.wiring import restore_active_task_runs
    from cascade.task.worktree import clear_task_runs

    mark_running(
        "task_001",
        root=root,
        now=datetime.now(timezone.utc) - timedelta(minutes=3),
    )
    clear_task_runs()
    assert restore_active_task_runs(root) == [("task_001", "feat_001")]
    assert restore_active_task_runs(root) == []


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


def test_concurrent_registry_removals_do_not_restore_stale_rows(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    entries = [
        IntegrationWorktree(
            kind="task",
            work_id=f"task_{index:03d}",
            branch=f"task/task_{index:03d}",
            path=integration_worktree_path(
                "task", f"task_{index:03d}", trunk=root
            ),
            base_sha="deadbeef",
        )
        for index in range(8)
    ]
    save_registry(root, entries)
    barrier = threading.Barrier(len(entries))

    def unregister(entry: IntegrationWorktree) -> None:
        barrier.wait(timeout=5)
        assert unregister_missing_integration_worktree(
            "task", entry.work_id, trunk=root
        )

    threads = [threading.Thread(target=unregister, args=(entry,)) for entry in entries]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert all(not thread.is_alive() for thread in threads)
    assert load_registry(root) == []


def test_registry_save_publishes_with_atomic_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    import cascade.workspace.integration_worktree as worktrees

    calls: list[tuple[Path, Path]] = []
    real_replace = worktrees.os.replace

    def recording_replace(source, destination) -> None:
        calls.append((Path(source), Path(destination)))
        real_replace(source, destination)

    monkeypatch.setattr(worktrees.os, "replace", recording_replace)
    save_registry(root, [])

    assert len(calls) == 1
    assert calls[0][1] == root / ".cascade" / "worktrees.json"
    assert calls[0][0].parent == calls[0][1].parent
    assert not calls[0][0].exists()


def test_registry_save_does_not_deadlock_with_merged_board_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    import cascade.workspace.integration_worktree as worktrees

    save_registry(root, [])
    invalidate_merged_board(root)
    replace_started = threading.Event()
    allow_replace = threading.Event()
    reader_has_cache_lock = threading.Event()
    failures: list[BaseException] = []
    real_replace = worktrees.os.replace
    real_build = worktrees._merged_board_uncached

    def blocking_replace(source, destination) -> None:
        replace_started.set()
        if not allow_replace.wait(timeout=5):
            raise TimeoutError("reader did not start")
        real_replace(source, destination)

    def marked_build(trunk: Path):
        reader_has_cache_lock.set()
        return real_build(trunk)

    monkeypatch.setattr(worktrees.os, "replace", blocking_replace)
    monkeypatch.setattr(worktrees, "_merged_board_uncached", marked_build)

    def run(call) -> None:
        try:
            call()
        except BaseException as exc:  # pragma: no cover - asserted below
            failures.append(exc)

    writer = threading.Thread(target=run, args=(lambda: save_registry(root, []),))
    reader = threading.Thread(target=run, args=(lambda: merged_board(root),))
    writer.start()
    assert replace_started.wait(timeout=5)
    reader.start()
    assert reader_has_cache_lock.wait(timeout=5)
    allow_replace.set()
    writer.join(timeout=5)
    reader.join(timeout=5)

    assert not writer.is_alive()
    assert not reader.is_alive()
    assert failures == []


def test_retire_clean_merged_worktree_preserves_branch(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    branch = integration_branch("epic", "epic_001")
    ensure_integration_worktree(
        "epic", "epic_001", branch=branch, base_ref="HEAD", trunk=root
    )
    wt = integration_worktree_path("epic", "epic_001", trunk=root)

    assert retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert not wt.exists()
    assert get_integration_worktree(root, "epic", "epic_001") is None
    assert _branch_exists(root, branch)


def test_retire_refuses_dirty_or_locked_worktree(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    branch = integration_branch("epic", "epic_001")
    ensure_integration_worktree(
        "epic", "epic_001", branch=branch, base_ref="HEAD", trunk=root
    )
    wt = integration_worktree_path("epic", "epic_001", trunk=root)

    (wt / "untracked.txt").write_text("active work\n", encoding="utf-8")
    assert not retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert wt.is_dir()
    assert get_integration_worktree(root, "epic", "epic_001") is not None

    (wt / "untracked.txt").unlink()
    subprocess.run(
        ["git", "worktree", "lock", str(wt)],
        cwd=root,
        check=True,
        capture_output=True,
    )
    assert not retire_integration_worktree(
        "epic", "epic_001", merged_into="HEAD", trunk=root
    )
    assert wt.is_dir()
    assert get_integration_worktree(root, "epic", "epic_001") is not None


def test_retire_accepts_authoritative_squash_merge_confirmation(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    branch = integration_branch("feature", "feat_001")
    entry = ensure_integration_worktree(
        "feature", "feat_001", branch=branch, base_ref="HEAD", trunk=root
    )
    change = entry.path / "feature.txt"
    change.write_text("source commit\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "feature.txt"], cwd=entry.path, check=True, capture_output=True
    )
    subprocess.run(
        ["git", "commit", "-m", "feature commit"],
        cwd=entry.path,
        check=True,
        capture_output=True,
    )

    assert not retire_integration_worktree(
        "feature", "feat_001", merged_into="HEAD", trunk=root
    )
    assert retire_integration_worktree(
        "feature",
        "feat_001",
        merged_into="HEAD",
        merge_confirmed=True,
        trunk=root,
    )
    assert not entry.path.exists()
    assert _branch_exists(root, branch)


def test_restart_retires_terminal_review_worktree(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    branch = integration_branch("feature", "feat_001")
    entry = ensure_integration_worktree(
        "feature", "feat_001", branch=branch, base_ref="HEAD", trunk=root
    )
    reviews = root / ".cascade" / "reviews.json"
    reviews.write_text(
        '{"feat_001": {"closed": true, "target_branch": "epic/epic_001"}}\n',
        encoding="utf-8",
    )

    retired = retire_terminal_registered_worktrees(root)

    assert [record.work_id for record in retired] == ["feat_001"]
    assert not entry.path.exists()
    assert get_integration_worktree(root, "feature", "feat_001") is None
    assert _branch_exists(root, branch)


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
    invalidate_merged_board(root)
    board = merged_board(root)
    roots = [path.resolve() for path in scan_active_markdown_roots(root)]
    assert calls == roots
    assert board.by_id["epic_001"].path.parent.name == "2_active"
    assert board.by_id["feat_001"].path.is_relative_to(
        integration_worktree_path("feature", "feat_001", trunk=root)
    )

    # A second concurrent-reader-style lookup reuses the completed snapshot.
    assert merged_board(root) is board
    assert calls == roots

    invalidate_merged_board(root)
    assert merged_board(root) is not board
    assert calls == roots + roots


def test_planning_tools_write_into_integration_checkouts(tmp_path: Path) -> None:
    from cascade.board.store import pin_parent
    from cascade.epic.mint import mint_feature
    from cascade.feature.mint import mint_task
    from cascade.feature.scoped_docs import feature_read_doc
    from cascade.workspace.integration_worktree import doc_filesystem_root

    root = make_repo(tmp_path)
    (root / ".gitignore").write_text(".cascade/\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Done", tier="task", status="completed", parent="feat_001")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    _chain(root)
    pin_parent("feat_001", "epic_001", root=doc_filesystem_root("feat_001", trunk=root))

    assert mint_task("Next", feature_id="feat_001", root=root) == "task_001_000_002"
    assert feature_read_doc("epic_001", feature_id="feat_001", root=root).meta.id == "epic_001"
    assert mint_feature("Sibling", epic_id="epic_001", root=root) == "feat_001_002"
    for checkout in (
        integration_worktree_path("feature", "feat_001", trunk=root),
        integration_worktree_path("epic", "epic_001", trunk=root),
    ):
        status = subprocess.run(
            ["git", "status", "--porcelain"], cwd=checkout, capture_output=True, text=True
        )
        assert status.stdout == ""


def test_active_feature_planning_ignores_stale_trunk_backlog_copy(tmp_path: Path) -> None:
    from cascade.boss.rollup import write_closeout
    from cascade.feature.mint import mint_task
    from cascade.feature.scoped_docs import feature_read_doc, feature_write_doc

    root = make_repo(tmp_path)
    (root / ".gitignore").write_text(".cascade/\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    feature = add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    stale_path = feature.meta.path
    stale_bytes = stale_path.read_bytes()
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    _chain(root)

    # Reproduce a stale trunk snapshot while the dispatched Feature is active
    # and authoritative in its integration checkout.
    stale_path.parent.mkdir(parents=True, exist_ok=True)
    stale_path.write_bytes(stale_bytes)

    active = feature_read_doc("feat_001", feature_id="feat_001", root=root)
    assert active.meta.status == "active"
    assert active.meta.path.is_relative_to(
        integration_worktree_path("feature", "feat_001", trunk=root)
    )

    task_id = mint_task("Planned task", feature_id="feat_001", root=root)
    checkout = integration_worktree_path("feature", "feat_001", trunk=root)
    assert read_doc(task_id, root=checkout).meta.parent == "feat_001"
    assert task_id in read_doc("feat_001", root=checkout).meta.children
    assert read_doc("feat_001", root=root).meta.status == "backlog"

    # A graph may submit the stale WorkDoc it ingested before dispatch. Writes
    # must still target the authoritative active copy in the feature checkout.
    stale = read_doc("feat_001", root=root)
    stale.body += "\n\n## Closeout\n\nCompleted from stale input.\n"
    feature_write_doc(stale, feature_id="feat_001", root=root)

    assert "Completed from stale input." in read_doc("feat_001", root=checkout).body
    assert read_doc("feat_001", root=root).body == feature.body

    write_closeout("feat_001", "Deterministic rollup closeout.", root=root)
    assert "Deterministic rollup closeout." in read_doc("feat_001", root=checkout).body
    assert read_doc("feat_001", root=root).body == feature.body
