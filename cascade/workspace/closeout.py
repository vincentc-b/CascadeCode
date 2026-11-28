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
    remote: str
    revision: str
    path: Path
    _temporary_root: Path
    _added: bool = True
    _cleaned: bool = False

    @property
    def remote_ref(self) -> str:
        return f"refs/remotes/{self.remote}/{self.target}"

    def refresh_target(self) -> None:
        """Fetch and require the configured target to remain at ``revision``."""

        fetched = _fetch_target(self.trunk, self.remote, self.target)
        if fetched != self.revision:
            raise GitError(
                "closeout target changed during history admission; "
                "fetch and prove it again"
            )

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

    def verify_history(
        self,
        *,
        source_revision: str | None = None,
        accepted_revision: str | None = None,
    ) -> str:
        """Prove physical terminal history for the exact fetched target.

        The returned fingerprint is valid only for this workspace revision.
        Split projects use their canonical tracking checkout for board evidence
        while retaining the fetched product revision as the closeout fence.
        """

        from cascade.board.context import get_project_context
        from cascade.review_validation import (
            AcceptedTerminalHistoryProof,
            ExactMergeCandidate,
            prove_accepted_terminal_history,
        )

        # A remote-tracking ref is a cache, not evidence. Refresh before and
        # after the physical scan so movement on either side of the proof is a
        # refusal rather than authorization for a stale checkout.
        self.refresh_target()

        board_root = self.path
        # The fetched commit may not be reachable from a local branch yet.
        # The detached checkout pins it as HEAD and is therefore the exact
        # accepted-history repository for colocated projects.
        accepted_repository = self.path
        board_revision = accepted_revision or self.revision
        target_repository = self.trunk
        target_ref = self.remote_ref
        target_sha = self.revision
        project = get_project_context()
        if (
            project is not None
            and project.target.root.resolve() != project.tracking.root.resolve()
        ):
            accepted_repository = project.tracking.root.resolve()
            board_root = accepted_repository
            board_revision = _resolve_commit(accepted_repository, "HEAD")
            target_repository = accepted_repository
            target_ref = "HEAD"
            target_sha = board_revision

        candidate = ExactMergeCandidate(
            source_sha=source_revision or self.revision,
            target_sha=target_sha,
            result_commit=self.revision,
            result_tree=_resolve_object(self.path, "HEAD^{tree}"),
            checkout=self.path,
        )
        proof = prove_accepted_terminal_history(
            target_repository,
            candidate,
            board_revision,
            accepted_repository=accepted_repository,
            candidate_board_root=board_root,
            owner_root=self.trunk,
            target_ref=target_ref,
        )
        if not isinstance(proof, AcceptedTerminalHistoryProof):
            raise GitError(
                "closeout history admission refused: "
                f"{proof.kind}: {proof.reason}; {proof.owner_action}"
            )
        self.refresh_target()
        return proof.fingerprint


def create_verified_trunk_workspace(
    trunk: Path, *, target: str | None = None, remote: str = "origin"
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
    revision = _fetch_target(repo, remote, branch)

    temporary_root = Path(tempfile.mkdtemp(prefix="cascade-closeout-"))
    path = temporary_root / "checkout"
    added = _git(repo, "worktree", "add", "--detach", str(path), revision)
    if added.returncode != 0:
        shutil.rmtree(temporary_root, ignore_errors=True)
        raise GitError(added.stderr.strip() or "cannot prepare closeout checkout")
    workspace = VerifiedTrunkWorkspace(
        trunk=repo,
        target=branch,
        remote=remote,
        revision=revision,
        path=path,
        _temporary_root=temporary_root,
    )
    try:
        workspace.verify_history()
    except Exception:
        workspace.cleanup()
        raise
    return workspace


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)


def _fetch_target(repo: Path, remote: str, branch: str) -> str:
    remote_ref = f"refs/remotes/{remote}/{branch}"
    fetch = _git(
        repo,
        "fetch",
        "--no-tags",
        remote,
        f"refs/heads/{branch}:{remote_ref}",
    )
    if fetch.returncode != 0:
        raise GitError(
            (fetch.stderr or fetch.stdout).strip()
            or f"could not fetch remote product trunk {remote}/{branch}"
        )
    return _resolve_commit(repo, remote_ref)


def _resolve_commit(repo: Path, ref: str) -> str:
    return _resolve_object(repo, f"{ref}^{{commit}}")


def _resolve_object(repo: Path, ref: str) -> str:
    result = _git(repo, "rev-parse", "--verify", ref)
    if result.returncode != 0:
        raise GitError(
            (result.stderr or result.stdout).strip()
            or f"closeout revision {ref!r} is unavailable"
        )
    return result.stdout.strip()
