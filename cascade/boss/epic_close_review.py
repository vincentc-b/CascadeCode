"""Publish terminal epic metadata without changing the operator checkout."""

from __future__ import annotations

import subprocess
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.store import move_doc
from cascade.tracking import MergeRequest, create_merge_request, find_merge_request, push_branch
from cascade.workspace.closeout import create_verified_trunk_workspace


def ensure_epic_close_review(epic_id: str, *, trunk: Path, target: str) -> MergeRequest:
    """Open one PR that moves an already merged epic to completed on trunk."""

    branch = f"cascade/epic-close/{epic_id}"
    existing = find_merge_request(trunk, source_branch=branch, target_branch=target)
    if existing is not None:
        return existing
    workspace = create_verified_trunk_workspace(trunk, target=target)
    checkout = workspace.path
    created_branch = False
    try:
        created = _git(checkout, "switch", "-c", branch)
        if created.returncode != 0:
            raise GitError(created.stderr.strip() or "cannot create epic closeout branch")
        created_branch = True
        move_doc(epic_id, "completed", root=checkout)
        push_branch(checkout, branch)
        return create_merge_request(
            checkout,
            title=f"{epic_id}: complete epic",
            body=(
                f"Records the human close of `{epic_id}` after its implementation "
                f"review merged. This changes only the epic lifecycle document."
            ),
            source_branch=branch,
            target_branch=target,
        )
    finally:
        workspace.cleanup()
        if created_branch:
            _git(trunk, "branch", "-D", branch)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
    )
