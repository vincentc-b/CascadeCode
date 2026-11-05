"""Synchronize merged review targets without discarding local lifecycle history."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.errors import GitError
from cascade.tracking import fast_forward_branch


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _diverged_review_target(tmp_path: Path) -> tuple[Path, str]:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-b", "epic/epic_001")

    local = tmp_path / "local"
    local.mkdir()
    _git(local, "init", "-b", "epic/epic_001")
    _git(local, "config", "user.name", "Test")
    _git(local, "config", "user.email", "test@example.com")
    (local / "state.txt").write_text("active\n", encoding="utf-8")
    _git(local, "add", "state.txt")
    _git(local, "commit", "-m", "base")
    _git(local, "remote", "add", "origin", str(remote))
    _git(local, "push", "-u", "origin", "epic/epic_001")

    writer = tmp_path / "writer"
    _git(tmp_path, "clone", str(remote), str(writer))
    _git(writer, "config", "user.name", "Test")
    _git(writer, "config", "user.email", "test@example.com")
    (writer / "feature.txt").write_text("merged feature\n", encoding="utf-8")
    _git(writer, "add", "feature.txt")
    _git(writer, "commit", "-m", "merge feature review")
    _git(writer, "push", "origin", "epic/epic_001")
    return local, _git(writer, "rev-parse", "HEAD")


def test_redundant_lifecycle_commits_reconcile_with_merged_review(
    tmp_path: Path,
) -> None:
    local, accepted_sha = _diverged_review_target(tmp_path)
    (local / "state.txt").write_text("blocked\n", encoding="utf-8")
    _git(local, "commit", "-am", "mark blocked")
    (local / "state.txt").write_text("active\n", encoding="utf-8")
    _git(local, "commit", "-am", "clear blocker")
    local_sha = _git(local, "rev-parse", "HEAD")

    reconciled_sha = fast_forward_branch(local, "epic/epic_001")

    assert reconciled_sha == _git(local, "rev-parse", "HEAD")
    assert _git(local, "diff", "--name-only", accepted_sha, "HEAD") == ""
    _git(local, "merge-base", "--is-ancestor", local_sha, reconciled_sha)
    _git(local, "merge-base", "--is-ancestor", accepted_sha, reconciled_sha)
    assert fast_forward_branch(local, "epic/epic_001") == reconciled_sha


def test_substantive_local_change_stays_blocked(tmp_path: Path) -> None:
    local, _accepted_sha = _diverged_review_target(tmp_path)
    (local / "state.txt").write_text("new plan\n", encoding="utf-8")
    _git(local, "commit", "-am", "unpublished plan")
    local_sha = _git(local, "rev-parse", "HEAD")

    with pytest.raises(GitError, match="fast-forward"):
        fast_forward_branch(local, "epic/epic_001")

    assert _git(local, "rev-parse", "HEAD") == local_sha
    assert _git(local, "status", "--porcelain") == ""
