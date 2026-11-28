"""Verified, disposable closeout workspaces."""

from __future__ import annotations

import subprocess
import shutil
from pathlib import Path

import pytest

from cascade.board.errors import GitError
from cascade.board.context import set_project_context
from cascade.board.store import move_doc
from cascade.workspace.branch_synchronization import synchronize_operator_trunk
from cascade.workspace.closeout import create_verified_trunk_workspace
from cascade.workspace.types import ProjectContext
from tests.support import add_doc, commit_board, make_repo


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("trunk\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "initial")


def _remote_operator(tmp_path: Path) -> Path:
    root = make_repo(tmp_path / "operator")
    _initial_commit(root)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "origin", "main")
    return root


def _advance_remote(root: Path, tmp_path: Path, name: str = "remote-change") -> str:
    writer = tmp_path / name
    _git(
        tmp_path,
        "clone",
        "--branch",
        "main",
        _git(root, "remote", "get-url", "origin"),
        str(writer),
    )
    _git(writer, "config", "user.name", "Test")
    _git(writer, "config", "user.email", "test@example.com")
    (writer / f"{name}.txt").write_text(f"{name}\n", encoding="utf-8")
    _git(writer, "add", f"{name}.txt")
    _git(writer, "commit", "-m", name)
    _git(writer, "push", "origin", "main")
    return _git(writer, "rev-parse", "HEAD")


def test_verified_closeout_workspace_is_detached_and_cleanup_preserves_operator(
    tmp_path: Path,
) -> None:
    root = _remote_operator(tmp_path)
    (root / "README.md").write_text("operator edit\n", encoding="utf-8")
    (root / "staged.txt").write_text("staged\n", encoding="utf-8")
    _git(root, "add", "staged.txt")
    (root / "untracked.txt").write_text("untracked\n", encoding="utf-8")
    before = {
        "head": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "branch", "--show-current"),
        "index": _git(root, "ls-files", "-s"),
        "status": _git(root, "status", "--porcelain"),
        "readme": (root / "README.md").read_bytes(),
    }

    workspace = create_verified_trunk_workspace(root)
    assert workspace.revision == _git(root, "rev-parse", "origin/main")
    assert _git(workspace.path, "rev-parse", "HEAD") == workspace.revision
    assert _git(workspace.path, "branch", "--show-current") == ""
    assert (workspace.path / "README.md").read_text(encoding="utf-8") == "trunk\n"

    # A failed closeout may leave generated files behind; forced cleanup is
    # confined to the disposable worktree and remains safe to repeat.
    (workspace.path / "failed-closeout.txt").write_text("discard\n", encoding="utf-8")
    workspace.cleanup()
    workspace.cleanup()

    assert not workspace.path.exists()
    assert str(workspace.path) not in _git(root, "worktree", "list", "--porcelain")
    assert _git(root, "rev-parse", "HEAD") == before["head"]
    assert _git(root, "branch", "--show-current") == before["branch"]
    assert _git(root, "ls-files", "-s") == before["index"]
    assert _git(root, "status", "--porcelain") == before["status"]
    assert (root / "README.md").read_bytes() == before["readme"]


def test_closeout_refuses_duplicate_remote_board_without_leaking_worktree(
    tmp_path: Path,
) -> None:
    root = _remote_operator(tmp_path)
    original = add_doc(
        root, id="epic_001", title="Epic", tier="epic", status="completed"
    )
    duplicate = root / "docs/epics/1_backlog/epic_001_duplicate.md"
    duplicate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(original.meta.path, duplicate)
    commit_board(root, message="duplicate remote board")
    _git(root, "push", "origin", "main")
    before = _git(root, "worktree", "list", "--porcelain")

    with pytest.raises(GitError, match="closeout history admission refused"):
        create_verified_trunk_workspace(root)

    assert _git(root, "worktree", "list", "--porcelain") == before


def test_closeout_history_proof_rejects_reopened_terminal_target(
    tmp_path: Path,
) -> None:
    root = _remote_operator(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="completed")
    commit_board(root, message="accepted terminal board")
    _git(root, "push", "origin", "main")
    accepted = _git(root, "rev-parse", "HEAD")
    move_doc("epic_001", "active", root=root)
    commit_board(root, message="reopen terminal board")
    _git(root, "push", "origin", "main")

    with create_verified_trunk_workspace(root) as workspace:
        with pytest.raises(GitError, match="terminal status reopened"):
            workspace.verify_history(accepted_revision=accepted)


def test_operator_trunk_sync_fast_forwards_exact_proven_target_idempotently(
    tmp_path: Path,
) -> None:
    root = _remote_operator(tmp_path)
    local = _git(root, "rev-parse", "HEAD")
    remote = _advance_remote(root, tmp_path)

    result = synchronize_operator_trunk(root=root)

    assert result.ok
    assert result.local_sha == local
    assert result.remote_sha == remote
    assert result.sync_result == "fast_forwarded"
    assert result.board_fingerprint
    assert _git(root, "rev-parse", "HEAD") == remote
    repeated = synchronize_operator_trunk(root=root)
    assert repeated.ok and repeated.sync_result == "current"
    assert repeated.local_sha == repeated.remote_sha == remote


@pytest.mark.parametrize("state", ["dirty", "wrong_branch", "diverged"])
def test_operator_trunk_sync_refusal_preserves_checkout_and_worktrees(
    tmp_path: Path, state: str
) -> None:
    root = _remote_operator(tmp_path)
    _advance_remote(root, tmp_path)
    if state == "dirty":
        (root / "operator.txt").write_text("preserve\n", encoding="utf-8")
        expected_reason = "dirty_checkout"
    elif state == "wrong_branch":
        _git(root, "switch", "-c", "operator-topic")
        expected_reason = "wrong_branch"
    else:
        (root / "local.txt").write_text("local\n", encoding="utf-8")
        _git(root, "add", "local.txt")
        _git(root, "commit", "-m", "local divergence")
        expected_reason = "diverged"
    before = {
        "head": _git(root, "rev-parse", "HEAD"),
        "branch": _git(root, "branch", "--show-current"),
        "index": _git(root, "ls-files", "-s"),
        "status": _git(root, "status", "--porcelain"),
        "worktrees": _git(root, "worktree", "list", "--porcelain"),
        "files": sorted(
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and ".git" not in path.parts
        ),
    }

    result = synchronize_operator_trunk(root=root)

    assert not result.ok and result.reason == expected_reason
    assert result.local_sha == before["head"]
    assert result.remote_sha
    assert result.owner == "operator" and result.prerequisite
    assert _git(root, "rev-parse", "HEAD") == before["head"]
    assert _git(root, "branch", "--show-current") == before["branch"]
    assert _git(root, "ls-files", "-s") == before["index"]
    assert _git(root, "status", "--porcelain") == before["status"]
    assert _git(root, "worktree", "list", "--porcelain") == before["worktrees"]
    assert sorted(
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    ) == before["files"]


def test_operator_trunk_sync_refetches_target_before_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace.closeout import VerifiedTrunkWorkspace

    root = _remote_operator(tmp_path)
    first_remote = _advance_remote(root, tmp_path, "first")
    original = VerifiedTrunkWorkspace.verify_history
    calls = 0

    def move_after_admission(self, **kwargs):
        nonlocal calls
        calls += 1
        proof = original(self, **kwargs)
        if calls == 2:
            _advance_remote(root, tmp_path, "moved")
        return proof

    monkeypatch.setattr(VerifiedTrunkWorkspace, "verify_history", move_after_admission)
    local = _git(root, "rev-parse", "HEAD")

    result = synchronize_operator_trunk(root=root)

    assert not result.ok and result.reason == "target_changed"
    assert result.remote_sha == first_remote
    assert _git(root, "rev-parse", "HEAD") == local


def test_operator_trunk_sync_recovers_when_completion_observation_is_interrupted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace import branch_synchronization

    root = _remote_operator(tmp_path)
    remote = _advance_remote(root, tmp_path, "interrupted")
    original = branch_synchronization._run

    def lose_completion(args, cwd, *, check=True):
        result = original(args, cwd, check=check)
        if args[:2] == ["merge", "--ff-only"]:
            return subprocess.CompletedProcess(args, 1, result.stdout, "interrupted")
        return result

    monkeypatch.setattr(branch_synchronization, "_run", lose_completion)

    result = synchronize_operator_trunk(root=root)

    assert result.ok and result.sync_result == "fast_forwarded"
    assert _git(root, "rev-parse", "HEAD") == remote
    monkeypatch.setattr(branch_synchronization, "_run", original)
    repeated = synchronize_operator_trunk(root=root)
    assert repeated.ok and repeated.sync_result == "current"


def test_operator_trunk_sync_uses_split_tracking_board_owner(tmp_path: Path) -> None:
    target = _remote_operator(tmp_path / "product")
    tracking = make_repo(tmp_path / "tracking")
    add_doc(tracking, id="epic_001", title="Epic", tier="epic", status="completed")
    set_project_context(ProjectContext.split(target, tracking))
    try:
        remote = _advance_remote(target, tmp_path, "split-target")
        result = synchronize_operator_trunk(root=target)
    finally:
        set_project_context(None)

    assert result.ok and result.remote_sha == remote
    assert result.board_fingerprint
