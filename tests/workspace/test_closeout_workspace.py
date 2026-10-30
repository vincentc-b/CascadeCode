"""Verified, disposable closeout workspaces."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.workspace.closeout import create_verified_trunk_workspace
from tests.support import make_repo


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
