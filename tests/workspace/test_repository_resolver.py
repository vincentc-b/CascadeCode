"""Integration coverage for tracking-repository preparation."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

import cascade.workspace.repository_resolver as repository_resolver
from cascade.board.context import set_project_context
from cascade.board.errors import GitSynchronizationError
from cascade.board.gitutil import commit_paths
from cascade.workspace import (
    WorkspaceError,
    parse_tracking_repository_reference,
    prepare_tracking_repository,
    synchronize_tracking_repository,
)
from cascade.workspace.project_config import TrackingRepositoryReference
from cascade.workspace.types import ProjectContext, RepositoryContext
from tests.support import make_git_repo


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    )


def _remote_with_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> TrackingRepositoryReference:
    source_parent = tmp_path / "source-parent"
    source_parent.mkdir()
    source = make_git_repo(source_parent)
    (source / "plan.md").write_text("tracked\n", encoding="utf-8")
    _git(source, "add", "plan.md")
    _git(source, "commit", "-m", "seed")
    bare = tmp_path / "remote.git"
    _git(tmp_path, "clone", "--bare", str(source), str(bare))

    home = tmp_path / "home"
    home.mkdir()
    (home / ".gitconfig").write_text(
        '[url "'
        + bare.as_uri()
        + '"]\n\tinsteadOf = https://user:token@example.test/planning.git\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("HOME", str(home))
    return TrackingRepositoryReference(
        kind="remote",
        value="https://user:token@example.test/planning.git",
    )


def test_local_checkout_is_validated_and_returned(tmp_path: Path) -> None:
    checkout = make_git_repo(tmp_path)
    config = tmp_path / "config" / "cascade.toml"
    config.parent.mkdir()
    reference = parse_tracking_repository_reference(str(checkout), config)

    prepared = prepare_tracking_repository(reference, tmp_path / "managed")

    assert prepared.root == checkout.resolve()
    assert prepared.display_identity == str(checkout.resolve())


@pytest.mark.parametrize("kind", ["missing", "plain-directory"])
def test_invalid_local_checkout_has_actionable_error(tmp_path: Path, kind: str) -> None:
    checkout = tmp_path / "tracking"
    if kind == "plain-directory":
        checkout.mkdir()
    reference = TrackingRepositoryReference(kind="local", value=checkout)

    with pytest.raises(WorkspaceError) as raised:
        prepare_tracking_repository(reference, tmp_path / "managed")

    message = str(raised.value)
    assert str(checkout) in message
    assert "does not exist" in message or "not a usable Git checkout" in message


def test_remote_checkout_is_deterministic_cloned_once_and_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = _remote_with_rewrite(tmp_path, monkeypatch)
    managed = tmp_path / "managed"

    first = prepare_tracking_repository(reference, managed)
    marker = first.root / "reuse-marker"
    marker.write_text("do not replace\n", encoding="utf-8")
    second = prepare_tracking_repository(reference, managed)
    alternate_credentials = TrackingRepositoryReference(
        kind="remote",
        value="https://different:secret@example.test/planning.git",
    )
    third = prepare_tracking_repository(alternate_credentials, managed)

    assert first == second == third
    assert first.root.parent == managed.resolve() / "tracking-repositories"
    assert (first.root / "plan.md").read_text(encoding="utf-8") == "tracked\n"
    assert marker.is_file()
    assert first.display_identity == "https://example.test/planning.git"
    assert "token" not in first.root.as_posix()


def test_existing_incomplete_managed_checkout_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = _remote_with_rewrite(tmp_path, monkeypatch)
    prepared = prepare_tracking_repository(reference, tmp_path / "managed")
    shutil.rmtree(prepared.root / ".git")

    with pytest.raises(WorkspaceError) as raised:
        prepare_tracking_repository(reference, tmp_path / "managed")

    assert "not a usable Git checkout" in str(raised.value)
    assert prepared.root.exists()


def test_existing_mismatched_managed_checkout_is_rejected_without_remote_leak(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = _remote_with_rewrite(tmp_path, monkeypatch)
    prepared = prepare_tracking_repository(reference, tmp_path / "managed")
    _git(
        prepared.root,
        "remote",
        "set-url",
        "origin",
        "https://other-user:other-secret@example.test/other.git",
    )

    with pytest.raises(WorkspaceError) as raised:
        prepare_tracking_repository(reference, tmp_path / "managed")

    message = str(raised.value)
    assert "origin does not match" in message
    assert "other-user" not in message
    assert "other-secret" not in message


@pytest.mark.parametrize(
    ("upstream", "expected"),
    [
        ("fatal: Permission denied (publickey). helper-secret", "authentication failed"),
        ("fatal: transport exploded with bearer-secret", "failed to clone"),
    ],
)
def test_clone_failures_are_actionable_and_redact_all_upstream_output(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    upstream: str,
    expected: str,
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_git = bin_dir / "git"
    fake_git.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$FAKE_GIT_ERROR\" >&2\nexit 1\n",
        encoding="utf-8",
    )
    fake_git.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_GIT_ERROR", upstream)
    reference = TrackingRepositoryReference(
        kind="remote", value="https://user:token@example.test/private.git"
    )

    with pytest.raises(WorkspaceError) as raised:
        prepare_tracking_repository(reference, tmp_path / "managed")

    message = str(raised.value)
    assert expected in message
    assert "user" not in message
    assert "token" not in message
    assert "helper-secret" not in message
    assert "bearer-secret" not in message


def test_failed_tracking_push_preserves_commit_for_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reference = _remote_with_rewrite(tmp_path, monkeypatch)
    tracking = prepare_tracking_repository(reference, tmp_path / "managed")
    _git(tracking.root, "config", "user.email", "test@example.com")
    _git(tracking.root, "config", "user.name", "Test User")
    target_parent = tmp_path / "target"
    target_parent.mkdir()
    target = make_git_repo(target_parent)
    set_project_context(
        ProjectContext(
            target=RepositoryContext(root=target),
            tracking=tracking,
        )
    )
    plan = tracking.root / "plan.md"
    plan.write_text("updated\n", encoding="utf-8")
    original_git = repository_resolver._git

    def fail_push(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "push":
            return subprocess.CompletedProcess(args, 1, "", "secret upstream failure")
        return original_git(cwd, *args)

    monkeypatch.setattr("cascade.workspace.repository_resolver._git", fail_push)
    with pytest.raises(GitSynchronizationError) as raised:
        commit_paths(tracking.root, [plan], "docs: update plan")

    local_head = _git(tracking.root, "rev-parse", "HEAD").stdout.strip()
    assert "local commits are preserved" in str(raised.value)
    assert "secret upstream failure" not in str(raised.value)
    assert _git(tracking.root, "show", "HEAD:plan.md").stdout == "updated\n"

    monkeypatch.setattr("cascade.workspace.repository_resolver._git", original_git)
    assert synchronize_tracking_repository(tracking) == local_head
    assert _git(tracking.root, "status", "--porcelain").stdout == ""
    branch = _git(tracking.root, "branch", "--show-current").stdout.strip()
    assert local_head in _git(tracking.root, "ls-remote", "origin", branch).stdout
