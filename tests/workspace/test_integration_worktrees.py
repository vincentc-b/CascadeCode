"""Integration worktrees at activate and dispatch (task_065)."""

from __future__ import annotations

import shutil
import subprocess
import threading
from pathlib import Path

import pytest

from cascade.board.context import set_project_context
from cascade.board.store import (
    list_board,
    move_doc,
    read_doc,
    read_doc_in_worktree,
    save_doc,
    write_doc,
)
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
    read_events,
)
from cascade.workspace.integration_worktree import (
    cancel_integration_worktree,
    ensure_integration_worktree,
    get_integration_worktree,
    invalidate_merged_board,
    integration_branch,
    integration_worktree_path,
    load_registry,
    merged_board,
    repair_missing_worktree,
    prove_terminal_retirement,
    resolve_mutation_owner,
    retire_integration_worktree,
    retire_terminal_registered_worktrees,
    scan_active_markdown_roots,
    save_registry,
    unregister_missing_integration_worktree,
)
from cascade.workspace.integration_worktree import IntegrationWorktree
from cascade.workspace.types import ProjectContext
from cascade.workspace.errors import MutationOwnerError
from cascade.workspace.up import resume_legally_active_graphs
from tests.support import (
    add_doc,
    approve_board_feature,
    commit_board,
    declare_no_dependencies,
    make_repo,
)


@pytest.fixture(autouse=True)
def _isolate_provider_admission(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep worktree lifecycle tests independent of provider discovery."""

    monkeypatch.setattr(
        "cascade.watchdog.dispatch._provider_preflight_refusal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        "cascade.approvals._require_approval_selections",
        lambda *_args, **_kwargs: (),
    )


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


def test_mutation_owner_ignores_completed_copy_in_sibling_worktree(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Owner", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    owner = ensure_integration_worktree(
        "feature",
        "feat_001",
        branch=integration_branch("feature", "feat_001"),
        base_ref="HEAD",
        trunk=root,
    )
    sibling = ensure_integration_worktree(
        "feature",
        "feat_002",
        branch=integration_branch("feature", "feat_002"),
        base_ref="HEAD",
        trunk=root,
    )
    stale = read_doc_in_worktree("task_001", sibling.path)
    previous = stale.meta.path
    stale.meta.status = "completed"
    stale.meta.path = sibling.path / "docs/tasks/3_completed/task_001_task.md"
    save_doc(stale, previous_path=previous, root=sibling.path)
    invalidate_merged_board(root)

    assert merged_board(root).by_id["task_001"].path.is_relative_to(sibling.path)
    assert resolve_mutation_owner("task_001", trunk=root) == owner.path
    move_doc("task_001", "active", root=root)
    assert read_doc_in_worktree("task_001", owner.path).meta.status == "active"
    assert read_doc_in_worktree("task_001", sibling.path).meta.status == "completed"


def test_mutation_owner_rejects_changed_registry_identity(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    entry = ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=integration_branch("epic", "epic_001"),
        base_ref="HEAD",
        trunk=root,
    )
    save_registry(
        root,
        [
            IntegrationWorktree(
                entry.kind,
                entry.work_id,
                "epic/changed",
                entry.path,
                entry.base_sha,
            )
        ],
    )

    with pytest.raises(
        MutationOwnerError, match="registered branch or checkout path"
    ) as exc:
        resolve_mutation_owner("epic_001", trunk=root)
    assert exc.value.reason.startswith("registered branch")

    save_registry(root, [entry])
    subprocess.run(
        ["git", "checkout", "-b", "epic/wrong-checkout"],
        cwd=entry.path,
        check=True,
        capture_output=True,
    )
    with pytest.raises(MutationOwnerError, match="different or detached branch"):
        resolve_mutation_owner("epic_001", trunk=root)


def test_mutation_owner_uses_tracking_root_in_split_project(tmp_path: Path) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    _initial_commit(target)
    add_doc(tracking, id="epic_001", title="Epic", tier="epic")
    set_project_context(ProjectContext.split(target, tracking))

    assert resolve_mutation_owner("epic_001", trunk=target) == tracking
    entry = ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=integration_branch("epic", "epic_001"),
        base_ref="HEAD",
        trunk=target,
    )
    assert resolve_mutation_owner("epic_001", trunk=target) == tracking
    move_doc("epic_001", "active", root=target)
    assert read_doc("epic_001", root=target).meta.status == "active"
    assert not list((entry.path / "docs").rglob("*.md"))


def test_mutation_owner_split_root_rejects_changed_owner_despite_completed_sibling(
    tmp_path: Path,
) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    _initial_commit(target)
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        tracking,
        id="feat_001",
        title="Owner backlog",
        tier="feature",
        parent="epic_001",
    )
    set_project_context(ProjectContext.split(target, tracking))
    owner = ensure_integration_worktree(
        "feature",
        "feat_001",
        branch=integration_branch("feature", "feat_001"),
        base_ref="HEAD",
        trunk=target,
    )
    sibling = ensure_integration_worktree(
        "feature",
        "feat_002",
        branch=integration_branch("feature", "feat_002"),
        base_ref="HEAD",
        trunk=target,
    )
    set_project_context(ProjectContext.colocated(sibling.path))
    add_doc(
        sibling.path,
        id="epic_001",
        title="Historical epic",
        tier="epic",
        status="active",
    )
    add_doc(
        sibling.path,
        id="feat_001",
        title="Historical sibling",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    set_project_context(ProjectContext.split(target, tracking))

    save_registry(
        target,
        [
            IntegrationWorktree(
                owner.kind,
                owner.work_id,
                "feat/changed",
                owner.path,
                owner.base_sha,
            ),
            sibling,
        ],
    )
    invalidate_merged_board(target)
    historical = next(
        (sibling.path / "docs/features/3_completed").glob("feat_001_*.md")
    )
    assert historical.is_file()
    with pytest.raises(MutationOwnerError, match="registered branch or checkout path"):
        resolve_mutation_owner("feat_001", trunk=target)

    save_registry(target, [owner, sibling])
    move_doc("feat_001", "active", root=target)
    assert read_doc_in_worktree("feat_001", tracking).meta.status == "active"
    assert historical.is_file()


def test_mutation_owner_refuses_snapshot_and_missing_registered_owner(tmp_path: Path) -> None:
    from cascade.workspace.backlog_snapshot import snapshot_root

    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(snapshot_root(root), id="epic_001", title="Remote", tier="epic")
    with pytest.raises(MutationOwnerError, match="read-only backlog snapshot"):
        resolve_mutation_owner("epic_001", trunk=root)

    active_owner = ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=integration_branch("epic", "epic_001"),
        base_ref="HEAD",
        trunk=root,
    )
    assert resolve_mutation_owner("epic_001", trunk=root) == active_owner.path

    shutil.rmtree(snapshot_root(root))
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    missing = IntegrationWorktree(
        "feature",
        "feat_001",
        integration_branch("feature", "feat_001"),
        integration_worktree_path("feature", "feat_001", trunk=root),
        "0" * 40,
    )
    save_registry(root, [missing])
    with pytest.raises(MutationOwnerError, match="registered owner checkout is missing"):
        resolve_mutation_owner("feat_001", trunk=root)


def test_mutation_owner_accepts_returned_lifecycle_root(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    returned = root / ".cascade/epic-returns/epic_001"
    add_doc(returned, id="epic_001", title="Returned", tier="epic")
    (returned / "manifest.json").write_text(
        '{"state":"returned","members":[{"id":"epic_001"}]}\n',
        encoding="utf-8",
    )

    assert resolve_mutation_owner("epic_001", trunk=root) == returned.resolve()


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


def test_activation_archives_a_previous_checkpoint_and_resolves_reviewed_role_pins(
    tmp_path: Path,
) -> None:
    """A backlog reactivation starts a graph run, rather than reviving its old one."""

    root = make_repo(tmp_path, models=True)
    (root / "cascade.toml").write_text(
        '[providers]\ndefault = "codex"\n[providers.codex]\nepic = "reviewed-default"\n',
        encoding="utf-8",
    )
    doc = add_doc(
        root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan"
    )
    doc.meta.provider = "codex"
    doc.meta.models = {
        "epic_manager": "reviewed-manager",
        "epic_architect": "reviewed-architect",
    }
    write_doc(doc, root=root)
    commit_board(root)

    from cascade.epic.checkpoint import checkpoint_path
    from cascade.epic.graph import ensure_epic_graph, seed_epic_role_models
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.watchdog.model_resolve import ResolvedBackend, ResolvedModel

    archived = ResolvedBackend(
        provider="cursor",
        provider_source="project-default",
        model=ResolvedModel("epic_manager", "archived-manager", "document-role"),
    )
    seed_epic_role_models("epic_001", manager=archived, architect=archived, root=root)
    assert checkpoint_path("epic_001", root=root).exists()

    install_epic_boot_hook(root)
    result = activate_epic("epic_001", "human", root=root)

    assert result.ok
    assert result.event is not None and result.event.payload["run_id"]
    archive = root / ".cascade" / "checkpoints" / "archive" / "epic_001"
    assert len(list(archive.glob("*.sqlite"))) == 1
    state = (
        ensure_epic_graph("epic_001", root=root)
        .get_state({"configurable": {"thread_id": "epic_001"}})
        .values
    )
    assert state is not None
    assert state["model_ids"] == {
        "epic_manager": "reviewed-manager",
        "epic_architect": "reviewed-architect",
    }
    assert state["provider_ids"] == {
        "epic_manager": "codex",
        "epic_architect": "codex",
    }


def test_activation_refuses_reactivation_when_child_work_is_present(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        parent="epic_001",
        status="active",
    )

    assert activate_epic("epic_001", "human", root=root).reason == "existing_child_work"


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


def test_merge_ready_task_is_not_restarted_as_swe_work(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    from cascade.task.execution import mark_awaiting_merge, mark_merge_blocked
    from cascade.task_rollup import queue_task_merge
    from cascade.task.wiring import restore_active_task_runs
    from cascade.task.worktree import clear_task_runs, get_task_run

    mark_awaiting_merge("task_001", root=root)
    clear_task_runs()
    assert restore_active_task_runs(root) == []
    assert get_task_run("task_001") is None

    # Older execution records may still say running even though the merge
    # queue proves the SWE turn already finished.
    from cascade.task.execution import mark_running

    mark_running("task_001", root=root)
    queue_task_merge("task_001", root=root)
    assert restore_active_task_runs(root) == []
    assert get_task_run("task_001") is None

    mark_merge_blocked(
        "task_001", root=root, reason="branch_conflict", conflict_paths=("worker.py",),
        source_sha="source1", target_sha="target1",
    )
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

    # Repair has restored the persisted branch/checkout identity; repeating the
    # supervisor evaluation has no lifecycle side effect.
    resume_legally_active_graphs(root)
    assert feat_wt.is_dir()
    repeated_events, _ = read_events("task_001", 0, root=root)
    assert [event.type for event in repeated_events] == [
        event.type for event in task_events_before
    ]


def test_startup_resumes_interrupted_task_once_without_new_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _chain(root)
    assert dispatch_task("task_001", "human", root=root).ok

    from cascade.task.worktree import clear_task_runs, get_task_run

    clear_task_runs()
    resumed: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_graph_queue_event",
        lambda task_id, **_kwargs: resumed.append(task_id) or True,
    )

    resume_legally_active_graphs(root)
    assert get_task_run("task_001") is not None
    resume_legally_active_graphs(root)
    assert resumed == ["task_001"]

    events, _ = read_events("task_001", 0, root=root)
    assert [event.type for event in events] == ["TaskDispatched", "TaskResumeRequested"]


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


def test_retire_clean_merged_worktree_preserves_branch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.integration_worktree import TerminalRetirementProof

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.prove_terminal_retirement",
        lambda *_args, **_kwargs: TerminalRetirementProof(True),
    )
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


def test_retire_refuses_dirty_or_locked_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.integration_worktree import TerminalRetirementProof

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.prove_terminal_retirement",
        lambda *_args, **_kwargs: TerminalRetirementProof(True),
    )
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


def test_retire_accepts_authoritative_squash_merge_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.integration_worktree import TerminalRetirementProof

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.prove_terminal_retirement",
        lambda *_args, **_kwargs: TerminalRetirementProof(True),
    )
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


def test_retirement_persists_and_rereads_missing_terminal_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    epic = ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=integration_branch("epic", "epic_001"),
        base_ref="HEAD",
        trunk=root,
    )
    feature = ensure_integration_worktree(
        "feature",
        "feat_001",
        branch=integration_branch("feature", "feat_001"),
        base_ref=epic.branch,
        trunk=root,
    )
    move_doc("task_001", "completed", root=feature.path)
    move_doc("feat_001", "completed", root=feature.path)
    subprocess.run(
        ["git", "branch", integration_branch("task", "task_001"), "HEAD"],
        cwd=feature.path,
        check=True,
        capture_output=True,
    )

    target_feature = read_doc_in_worktree("feat_001", epic.path)
    previous_feature = target_feature.meta.path
    target_feature.meta.status = "completed"
    target_feature.meta.path = (
        epic.path / "docs/features/3_completed" / previous_feature.name
    )
    save_doc(target_feature, previous_path=previous_feature, root=epic.path)
    target_task = read_doc_in_worktree("task_001", epic.path).meta.path
    subprocess.run(
        ["git", "rm", str(target_task.relative_to(epic.path))],
        cwd=epic.path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "remove stale task copy"],
        cwd=epic.path,
        check=True,
        capture_output=True,
    )
    reviews = root / ".cascade" / "reviews.json"
    reviews.write_text(
        '{"feat_001": {"closed": true, "target_branch": "epic/epic_001", '
        '"terminal_disposition": "closed"}}\n',
        encoding="utf-8",
    )

    import cascade.board.store as board_store

    real_write = board_store.write_doc
    interrupted = True

    def interrupt_once(*args, **kwargs):
        nonlocal interrupted
        if interrupted:
            interrupted = False
            raise OSError("simulated persistence interruption")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(board_store, "write_doc", interrupt_once)
    first = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not first.ok
    assert first.next_action is not None and "retry retirement" in first.next_action
    assert feature.path.is_dir()
    assert get_integration_worktree(root, "feature", "feat_001") is not None

    proof = prove_terminal_retirement("feature", "feat_001", trunk=root)

    assert proof.ok
    assert proof.required_descendants == ("task_001",)
    assert proof.persisted_descendants == ("task_001",)
    copied = read_doc_in_worktree("task_001", epic.path)
    assert copied.meta.status == "completed"
    assert copied.meta.path.parent.name == "3_completed"
    assert prove_terminal_retirement("feature", "feat_001", trunk=root).ok


def test_delivery_rollup_retirement_and_restart_converge_on_terminal_task(
    tmp_path: Path,
) -> None:
    from cascade.boss.rollup import try_complete_feature
    from cascade.comments.store import comment, resolve_comment
    from cascade.task.action_recovery import recovery_actions
    from cascade.task.execution import (
        execution_view,
        mark_awaiting_merge,
        mark_queued,
        mark_running,
    )
    from cascade.task.failure import defer_task_teardown, flush_deferred_task_teardown
    from cascade.task.worktree import create_task_worktree
    from cascade.task_rollup import queue_task_merge, retry_pending_task_merges

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
    commit_board(root)
    epic = ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=integration_branch("epic", "epic_001"),
        base_ref="HEAD",
        trunk=root,
    )
    feature = ensure_integration_worktree(
        "feature",
        "feat_001",
        branch=integration_branch("feature", "feat_001"),
        base_ref=epic.branch,
        trunk=root,
    )
    move_doc("feat_001", "active", root=root)

    # The child is minted after the parent checkout was cut.  This is the
    # production shape that left a terminal parent copy without its last Task.
    add_doc(
        feature.path,
        id="task_001",
        title="Last task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    feature_doc = read_doc_in_worktree("feat_001", feature.path)
    feature_doc.meta.children = ["task_001"]
    save_doc(feature_doc, previous_path=feature_doc.meta.path, root=feature.path)
    task_run = create_task_worktree(
        "task_001",
        root=root,
        parent_rev=None,
        skills=[],
        base_ref=feature.branch,
    )
    (task_run.worktree / "delivered.txt").write_text(
        "delivered\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "add", "delivered.txt"],
        cwd=task_run.worktree,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "deliver task"],
        cwd=task_run.worktree,
        check=True,
        capture_output=True,
    )
    deliverable_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=task_run.worktree,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    feature_base_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feature.path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    mark_queued("task_001", root=root)
    mark_running("task_001", root=root)
    mark_awaiting_merge("task_001", root=root)
    queue_task_merge(
        "task_001",
        root=root,
        delivery_evidence={
            "task_id": "task_001",
            "deliverable_sha": deliverable_sha,
            "feature_base_sha": feature_base_sha,
        },
    )
    comment_id = comment(
        "feat_001",
        "Scope",
        "Hold parent rollup until Task delivery evidence is inspected.",
        author="human",
        root=root,
    )
    teardown = defer_task_teardown()
    assert retry_pending_task_merges(root) == ["task_001"]

    execution = execution_view("task_001", root=root)
    assert execution is not None
    assert (execution["phase"], execution["outcome"]) == ("terminal", "succeeded")
    action = next(
        row
        for row in recovery_actions(root=root)
        if row["action_id"] == "task_001:queued_merge"
    )
    assert action["recovery_state"] == "completed"
    task_events, _ = read_events("feat_001", 0, root=root)
    merged = [event for event in task_events if event.type == "TaskMerged"]
    assert len(merged) == 1
    assert merged[0].payload["task_id"] == "task_001"
    assert merged[0].payload["branch"] == "task/task_001"
    assert merged[0].payload["merge_sha"]

    resolve_comment("feat_001", comment_id, author="human", root=root)
    subprocess.run(
        ["git", "add", "docs/_comments/feat_001.jsonl"],
        cwd=feature.path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "resolve closeout hold"],
        cwd=feature.path,
        check=True,
        capture_output=True,
    )
    move_doc("feat_001", "completed", root=feature.path)
    assert "task_001" not in list_board(epic.path).by_id
    invalidate_merged_board(root)

    assert try_complete_feature("feat_001", root=root, review_merged=True)
    # A forge callback records completion but cannot retire the retained owner
    # before the intended local Epic target contains the delivered head.
    assert feature.path.exists()
    assert get_integration_worktree(root, "feature", "feat_001") is not None
    subprocess.run(
        ["git", "merge", "--no-ff", feature.branch, "-m", "synchronize feature"],
        cwd=epic.path,
        check=True,
        capture_output=True,
    )
    assert retire_integration_worktree(
        "feature", "feat_001", merged_into=epic.branch, trunk=root
    )
    assert not feature.path.exists()
    persisted = read_doc_in_worktree("task_001", epic.path)
    assert persisted.meta.status == "completed"
    assert persisted.meta.path.parent.name == "3_completed"
    feature_events, _ = read_events("epic_001", 0, root=root)
    assert any(
        event.type == "FeatureCompleted"
        and event.payload.get("feature_id") == "feat_001"
        for event in feature_events
    )

    # The Task checkout still contains its pre-merge active copy until graph
    # teardown.  The merged board must keep the canonical persisted terminal row.
    assert task_run.worktree.is_dir()
    assert list_board(task_run.worktree).by_id["task_001"].status == "active"
    invalidate_merged_board(root)
    projected = merged_board(root).by_id["task_001"]
    assert projected.status == "completed"
    assert projected.path.is_relative_to(epic.path)

    flush_deferred_task_teardown(teardown)
    retire_terminal_registered_worktrees(root)
    retire_terminal_registered_worktrees(root)
    resume_legally_active_graphs(root)
    invalidate_merged_board(root)

    restarted = merged_board(root).by_id["task_001"]
    assert restarted.status == "completed"
    assert restarted.path.is_relative_to(epic.path)
    assert read_doc_in_worktree("task_001", epic.path).meta.status == "completed"
    assert execution_view("task_001", root=root)["outcome"] == "succeeded"
    assert next(
        row
        for row in recovery_actions(root=root)
        if row["action_id"] == "task_001:queued_merge"
    )["recovery_state"] == "completed"


def test_retirement_refuses_missing_descendant_provenance(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    epic = ensure_integration_worktree(
        "epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=root
    )
    feature = ensure_integration_worktree(
        "feature", "feat_001", branch="feat/feat_001", base_ref=epic.branch, trunk=root
    )
    move_doc("task_001", "completed", root=feature.path)
    move_doc("feat_001", "completed", root=feature.path)
    target_feature = read_doc_in_worktree("feat_001", epic.path)
    previous = target_feature.meta.path
    target_feature.meta.status = "completed"
    target_feature.meta.path = epic.path / "docs/features/3_completed" / previous.name
    save_doc(target_feature, previous_path=previous, root=epic.path)
    reviews = root / ".cascade" / "reviews.json"
    reviews.write_text(
        '{"feat_001": {"closed": true, "target_branch": "epic/epic_001", '
        '"terminal_disposition": "closed"}}\n',
        encoding="utf-8",
    )

    proof = prove_terminal_retirement("feature", "feat_001", trunk=root)

    assert not proof.ok
    assert (
        proof.reason is not None
        and "lacks delivery/completion provenance" in proof.reason
    )
    assert feature.path.is_dir()
    assert get_integration_worktree(root, "feature", "feat_001") is not None


def test_feature_retirement_requires_exact_review_and_target_integration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cascade.review as review
    from cascade.watchdog import Event, append_event
    from datetime import datetime, timezone

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
    epic = ensure_integration_worktree(
        "epic", "epic_001", branch="epic/epic_001", base_ref="HEAD", trunk=root
    )
    feature = ensure_integration_worktree(
        "feature", "feat_001", branch="feat/feat_001", base_ref=epic.branch, trunk=root
    )
    (feature.path / "delivered.txt").write_text("delivery\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", "delivered.txt"],
        cwd=feature.path,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "feature delivery"],
        cwd=feature.path,
        check=True,
        capture_output=True,
    )
    source_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=feature.path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    target_head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=epic.path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    projection = {
        "url": "https://example.test/pulls/1",
        "number": "1",
        "forge": "github",
        "source_branch": feature.branch,
        "target_branch": epic.branch,
        "source_head": source_head,
        "target_head": target_head,
        "draft": False,
        "closed": False,
        "seen_comments": [],
        "toast_notified": True,
    }
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)

    missing = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not missing.ok and "review_not_published" in str(missing.reason)

    review._store_review_generation(
        root, "feat_001", projection, generation=1, action_id="repair:one"
    )
    opened = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not opened.ok and "review_acceptance_pending" in str(opened.reason)

    review._update_record(root, "feat_001", {"closed": True})
    closed_unmerged = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not closed_unmerged.ok
    assert "accepted_current_generation_missing" in str(closed_unmerged.reason)

    review._update_record(
        root,
        "feat_001",
        {
            "accepted_merge_sha": source_head,
            "accepted_source_head": "stale-source",
            "accepted_target_head": target_head,
            "reconciliation_status": "accepted",
        },
    )
    stale = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not stale.ok

    review._update_record(
        root,
        "feat_001",
        {
            "accepted_source_head": source_head,
            "accepted_target_head": target_head,
        },
    )
    unsynchronized = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert not unsynchronized.ok
    assert "intended_target_not_verified" in str(unsynchronized.reason)
    assert feature.path.is_dir()
    assert get_integration_worktree(root, "feature", "feat_001") is not None

    subprocess.run(
        ["git", "merge", "--no-ff", feature.branch, "-m", "integrate feature"],
        cwd=epic.path,
        check=True,
        capture_output=True,
    )
    append_event(
        "epic_001",
        Event(
            type="FeatureCompleted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": "feat_001"},
            dest="epic_001",
        ),
        root=root,
    )

    verified = prove_terminal_retirement("feature", "feat_001", trunk=root)
    assert verified.ok
    assert feature.path.is_dir()
    assert get_integration_worktree(root, "feature", "feat_001") is not None


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
        '{"feat_001": {"closed": true, "target_branch": "epic/epic_001", '
        '"terminal_disposition": "closed"}}\n',
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
    declare_no_dependencies("epic_001", root=root)
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


def test_cancel_owned_worktree_removes_only_clean_registered_artifacts(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    branch = integration_branch("task", "task_001")
    entry = ensure_integration_worktree(
        "task", "task_001", branch=branch, base_ref="HEAD", trunk=root
    )
    unrelated = "task/task_999"
    subprocess.run(
        ["git", "branch", unrelated], cwd=root, check=True, capture_output=True
    )

    result = cancel_integration_worktree("task", "task_001", trunk=root)

    assert result.complete
    assert not entry.path.exists()
    assert get_integration_worktree(root, "task", "task_001") is None
    assert not _branch_exists(root, branch)
    assert _branch_exists(root, unrelated)
    # A matching-looking unregistered branch is not sufficient ownership proof.
    assert cancel_integration_worktree("task", "task_999", trunk=root).complete
    assert _branch_exists(root, unrelated)


def test_cancel_owned_worktree_reports_dirty_refusal_without_mutation(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    branch = integration_branch("feature", "feat_001")
    entry = ensure_integration_worktree(
        "feature", "feat_001", branch=branch, base_ref="HEAD", trunk=root
    )
    (entry.path / "uncommitted.txt").write_text("preserve me\n", encoding="utf-8")

    result = cancel_integration_worktree("feature", "feat_001", trunk=root)

    assert not result.complete
    assert result.step == "remove_worktree"
    assert result.detail is not None and "uncommitted changes" in result.detail
    assert entry.path.is_dir()
    assert (entry.path / "uncommitted.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert get_integration_worktree(root, "feature", "feat_001") == entry
    assert _branch_exists(root, branch)
