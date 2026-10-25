"""Publish terminal epic metadata without changing the operator checkout."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.store import move_doc
from cascade.tracking import MergeRequest, create_merge_request, find_merge_request, push_branch


def ensure_epic_close_review(epic_id: str, *, trunk: Path, target: str) -> MergeRequest:
    """Open one PR that moves an already merged epic to completed on trunk."""

    branch = f"cascade/epic-close/{epic_id}"
    existing = find_merge_request(trunk, source_branch=branch, target_branch=target)
    if existing is not None:
        return existing
    runtime = trunk / ".cascade"
    runtime.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{epic_id}-close-", dir=runtime) as temporary:
        checkout = Path(temporary) / "checkout"
        added = _git(trunk, "worktree", "add", "--detach", str(checkout), f"origin/{target}")
        if added.returncode != 0:
            raise GitError(added.stderr.strip() or "cannot prepare epic closeout checkout")
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
            _git(trunk, "worktree", "remove", "--force", str(checkout))
            if created_branch:
                _git(trunk, "branch", "-D", branch)


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True,
    )
