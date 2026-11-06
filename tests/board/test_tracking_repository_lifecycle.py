"""Planning artifacts persist through the resolved tracking repository."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import cascade.workspace.repository_resolver as repository_resolver
from cascade.board import list_board, move_doc, pin_parent, read_doc, write_doc
from cascade.board.errors import GitSynchronizationError
from cascade.epic.decisions import record_decision
from cascade.epic.planning_signoffs import sidecar_path
from cascade.task.worktree import create_task_worktree
from cascade.workspace import WorkspaceError, prepare_up
from tests.support import add_doc, make_repo


def _commit_initial(root: Path) -> None:
    (root / "README.md").write_text("repository\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initialize"], cwd=root, check=True)


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )


def test_split_repository_routes_complete_artifact_lifecycle(tmp_path: Path) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    (target / "cascade.toml").write_text(
        f'tracking_repository = "{tracking}"\n', encoding="utf-8"
    )
    _commit_initial(target)
    _commit_initial(tracking)
    target_head = _git(target, "rev-parse", "HEAD").stdout.strip()

    workspace = prepare_up(target)
    assert workspace.board == tracking / "docs"

    epic = add_doc(
        target,
        id="epic_001",
        title="Split epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    feature = add_doc(
        target,
        id="feat_001",
        title="Split feature",
        tier="feature",
        status="active",
        parent=epic.meta.id,
        children=["task_001"],
    )
    add_doc(
        target,
        id="task_001",
        title="Split task",
        tier="task",
        parent=feature.meta.id,
    )

    parent_revision = pin_parent("task_001", "feat_001", root=target)
    task = read_doc("task_001", root=target)
    assert task.meta.parent_rev == read_doc("feat_001", root=target).sha
    assert parent_revision == task.sha

    task.meta.title = "Updated split task"
    write_doc(task, root=target)
    move_doc("task_001", "completed", root=target)
    decision_id = record_decision(
        "Storage",
        "Use tracking",
        "Planning history belongs with planning artifacts.",
        "The configured repository roles.",
        epic_id="epic_001",
        root=target,
    )

    board = list_board(target)
    assert set(board.by_id) == {"epic_001", "feat_001", "task_001"}
    assert board.by_id["task_001"].status == "completed"
    assert read_doc("task_001", root=target).meta.title == "Updated split task"
    assert decision_id in read_doc("epic_001", root=target).body
    assert sidecar_path("epic_001", root=target).is_relative_to(tracking)
    assert all(meta.path.is_relative_to(tracking) for meta in board.by_id.values())
    assert not list((target / "docs").rglob("*.md"))
    assert len(list((tracking / "docs").rglob("*.md"))) == 3
    assert _git(target, "rev-parse", "HEAD").stdout.strip() == target_head
    assert _git(target, "status", "--porcelain", "--", "docs").stdout == ""


def test_colocated_repository_keeps_existing_storage_behavior(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _commit_initial(root)

    workspace = prepare_up(root)
    doc = add_doc(root, id="epic_001", title="Colocated", tier="epic")
    doc.meta.title = "Updated colocated epic"
    write_doc(doc, root=root)
    move_doc(doc.meta.id, "active", root=root)
    decision_id = record_decision(
        "Storage",
        "Stay colocated",
        "Compatibility mode keeps planning with source.",
        "No tracking repository is configured.",
        epic_id=doc.meta.id,
        root=root,
    )

    assert workspace.target_repository is workspace.tracking_repository
    assert workspace.board == root / "docs"
    persisted = read_doc(doc.meta.id, root=root)
    assert persisted.meta.path.is_relative_to(root)
    assert persisted.meta.title == "Updated colocated epic"
    assert persisted.meta.status == "active"
    assert decision_id in persisted.body
    assert set(list_board(root).by_id) == {doc.meta.id}


def test_split_repository_keeps_implementation_worktrees_in_target(
    tmp_path: Path,
) -> None:
    target = make_repo(tmp_path / "target")
    tracking = make_repo(tmp_path / "tracking")
    (target / "cascade.toml").write_text(
        f'tracking_repository = "{tracking}"\n', encoding="utf-8"
    )
    _commit_initial(target)
    _commit_initial(tracking)
    prepare_up(target)

    run = create_task_worktree(
        "task_001", root=target, parent_rev=None, skills=[]
    )

    assert run.worktree.is_relative_to(target / ".cascade" / "worktrees")
    assert not (tracking / ".cascade" / "worktrees").exists()


def test_unavailable_tracking_storage_reports_failure_without_artifact_changes(
    tmp_path: Path,
) -> None:
    target = make_repo(tmp_path / "target")
    unavailable = tmp_path / "missing-tracking"
    (target / "cascade.toml").write_text(
        f'tracking_repository = "{unavailable}"\n', encoding="utf-8"
    )
    _commit_initial(target)
    target_head = _git(target, "rev-parse", "HEAD").stdout.strip()

    with pytest.raises(WorkspaceError, match="tracking repository path does not exist"):
        prepare_up(target)

    assert not unavailable.exists()
    assert not list((target / "docs").rglob("*.md"))
    assert _git(target, "rev-parse", "HEAD").stdout.strip() == target_head
    assert _git(target, "status", "--porcelain").stdout == ""


def test_failed_tracking_synchronization_reports_failure_and_preserves_recovery_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = make_repo(tmp_path / "target")
    source = make_repo(tmp_path / "tracking-source")
    _commit_initial(source)
    remote = tmp_path / "tracking.git"
    _git(tmp_path, "clone", "--bare", str(source), str(remote))
    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(
        f'[url "{remote.as_uri()}"]\n\tinsteadOf = https://example.test/planning.git\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    (target / "cascade.toml").write_text(
        'tracking_repository = "https://example.test/planning.git"\n',
        encoding="utf-8",
    )
    _commit_initial(target)

    workspace = prepare_up(target)
    tracking = workspace.tracking_repository.root
    _git(tracking, "config", "user.email", "test@example.com")
    _git(tracking, "config", "user.name", "Test User")
    original_git = repository_resolver._git

    def fail_push(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(args, 1, "", "private upstream detail")
        return original_git(root, *args)

    monkeypatch.setattr(repository_resolver, "_git", fail_push)

    with pytest.raises(GitSynchronizationError) as raised:
        add_doc(target, id="epic_001", title="Unsynchronized", tier="epic")

    message = str(raised.value)
    assert "failed to push tracking repository" in message
    assert "local commits are preserved" in message
    assert "private upstream detail" not in message
    assert not list((target / "docs").rglob("*.md"))
    assert read_doc("epic_001", root=target).meta.path.is_relative_to(tracking)
    local_paths = _git(
        tracking, "show", "--name-only", "--format=", "HEAD"
    ).stdout.splitlines()
    remote_paths = _git(
        remote, "ls-tree", "-r", "--name-only", "HEAD"
    ).stdout.splitlines()
    assert any("epic_001" in path for path in local_paths)
    assert not any(path.startswith("docs/") for path in remote_paths)
