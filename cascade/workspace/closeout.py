"""Disposable verified-trunk workspaces for closeout operations."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from cascade.board.errors import GitError
from cascade.workspace.trunk import resolve_product_trunk


@dataclass
class VerifiedTrunkWorkspace:
    """A checkout owned exclusively by one closeout operation.

    ``path`` is detached at ``revision``. The temporary parent is created by
    this object, so cleanup never needs to infer or remove an operator path.
    """

    trunk: Path
    target: str
    revision: str
    path: Path
    _temporary_root: Path
    _added: bool = True
    _cleaned: bool = False

    def cleanup(self) -> None:
        """Remove only this workspace and its private temporary directory."""

        if self._cleaned:
            return
        try:
            if self._added:
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(self.path)],
                    cwd=self.trunk,
                    capture_output=True,
                    text=True,
                )
        finally:
            # The parent came from mkdtemp and is never derived from caller
            # metadata. Removing it is safe even after a partial Git failure.
            shutil.rmtree(self._temporary_root, ignore_errors=True)
            self._cleaned = True

    def __enter__(self) -> "VerifiedTrunkWorkspace":
        return self

    def __exit__(self, *_: object) -> None:
        self.cleanup()


def create_verified_trunk_workspace(
    trunk: Path, *, target: str | None = None
) -> VerifiedTrunkWorkspace:
    """Fetch product trunk and create a detached checkout at its exact SHA.

    The operator checkout supplies only Git administrative metadata; its files,
    index, current branch, and HEAD are never checked out or otherwise changed.
    """

    repo = Path(trunk).resolve()
    expected_target = resolve_product_trunk(repo)
    if target is not None and target != expected_target:
        raise GitError(
            f"closeout target {target!r} is not product trunk {expected_target!r}"
        )
    branch = target or expected_target
    remote_ref = f"refs/remotes/origin/{branch}"
    fetch = _git(
        repo,
        "fetch",
        "--no-tags",
        "origin",
        f"refs/heads/{branch}:{remote_ref}",
    )
    if fetch.returncode != 0:
        raise GitError(
            (fetch.stderr or fetch.stdout).strip()
            or f"could not fetch remote product trunk origin/{branch}"
        )
    resolved = _git(repo, "rev-parse", "--verify", f"{remote_ref}^{{commit}}")
    if resolved.returncode != 0:
        raise GitError(
            (resolved.stderr or resolved.stdout).strip()
            or f"remote product trunk origin/{branch} is unavailable"
        )
    revision = resolved.stdout.strip()

    temporary_root = Path(tempfile.mkdtemp(prefix="cascade-closeout-"))
    path = temporary_root / "checkout"
    added = _git(repo, "worktree", "add", "--detach", str(path), revision)
    if added.returncode != 0:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise GitError(added.stderr.strip() or "cannot prepare closeout checkout")
    return VerifiedTrunkWorkspace(
        trunk=repo,
        target=branch,
        revision=revision,
        path=path,
        _temporary_root=temporary_root,
    )


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
