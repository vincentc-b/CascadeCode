"""Human-path local merges on stacked integration branches (no push, no Boss tools).

Merge targets: task → feat/{parent}, feature → epic/{parent}, epic → product trunk.
Git merge/checkout runs in integration worktrees; operator ``--root`` stays on the trunk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import _run, has_git, head_sha
from cascade.board.paths import column_for_status
from cascade.board.store import move_doc, read_doc
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event


@dataclass(frozen=True)
class MergeResult:
    ok: bool
    reason: str | None = None
    merge_sha: str | None = None
    branch: str | None = None
    target_branch: str | None = None


def merge_task_branch(task_id: str, *, root: Path | None = None) -> MergeResult:
    """Merge ``task/{task_id}`` into ``feat/{feature_id}`` and complete the task."""

    trunk = resolve_root(root)
    branch = f"task/{task_id}"

    try:
        task = read_doc(task_id, root=trunk)
    except NotFound:
        return MergeResult(ok=False, reason="task_not_found", branch=branch)

    if task.meta.tier != "task":
        return MergeResult(ok=False, reason="wrong_tier", branch=branch)

    if column_for_status(task.meta.status) != "active":
        return MergeResult(ok=False, reason="wrong_column", branch=branch)
    if task.meta.status != "active":
        return MergeResult(ok=False, reason="not_mergeable", branch=branch)

    feature_id = task.meta.parent
    if not feature_id:
        return MergeResult(ok=False, reason="missing_parent", branch=branch)

    if not has_git(trunk):
        return MergeResult(ok=False, reason="not_a_git_repo", branch=branch)

    aligned, align_reason = _operator_on_product_trunk(trunk)
    if not aligned:
        return MergeResult(ok=False, reason=align_reason or "wrong_branch", branch=branch)

    target_branch = f"feat/{feature_id}"
    merge_root = _feature_merge_checkout(trunk, feature_id)
    if merge_root is None:
        return MergeResult(
            ok=False,
            reason="merge_target_missing",
            branch=branch,
            target_branch=target_branch,
        )

    if not _branch_exists(trunk, branch):
        return MergeResult(
            ok=False,
            reason="branch_missing",
            branch=branch,
            target_branch=target_branch,
        )

    if _current_branch(merge_root) != target_branch:
        if _run(["checkout", target_branch], merge_root, check=False).returncode != 0:
            return MergeResult(
                ok=False,
                reason="merge_target_missing",
                branch=branch,
                target_branch=target_branch,
            )

    pre_merge_sha = head_sha(merge_root)
    worktree_clean = _worktree_clean(merge_root)

    merge_sha = _merge_branch(merge_root, branch)
    if merge_sha is None:
        return MergeResult(
            ok=False,
            reason="merge_conflict",
            branch=branch,
            target_branch=target_branch,
        )

    created_merge_commit = (
        pre_merge_sha is not None
        and merge_sha is not None
        and merge_sha != pre_merge_sha
    )

    try:
        move_doc(task_id, "completed", root=merge_root)
        _sync_task_completed_on_trunk(trunk, task_id, merge_root)
    except Exception:
        if worktree_clean and created_merge_commit:
            _run(["reset", "--hard", "ORIG_HEAD"], merge_root, check=False)
        return MergeResult(
            ok=False,
            reason="post_merge_failed",
            branch=branch,
            target_branch=target_branch,
        )

    try:
        append_event(
            feature_id,
            Event(
                type="TaskMerged",
                ts=datetime.now(timezone.utc),
                payload={
                    "task_id": task_id,
                    "branch": branch,
                    "merge_sha": merge_sha,
                    "target_branch": target_branch,
                },
                dest=feature_id,
            ),
            root=trunk,
        )

        message = f"Task {task_id} merged into {target_branch}."
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload={
                    "kind": "task_merged",
                    "id": task_id,
                    "message": message,
                    "body": message,
                },
                dest="war_room",
            ),
            root=trunk,
        )
    except Exception:
        pass

    from cascade.task.worktree import get_task_run

    run = get_task_run(task_id)
    if run is not None:
        run.state = "merged"
    from cascade.task.failure import schedule_task_teardown

    schedule_task_teardown(task_id)

    return MergeResult(
        ok=True,
        merge_sha=merge_sha,
        branch=branch,
        target_branch=target_branch,
    )


def merge_feature_branch(feature_id: str, *, root: Path | None = None) -> MergeResult:
    """Merge ``feat/{feature_id}`` into ``epic/{epic_id}`` when branches exist."""

    trunk = resolve_root(root)
    source_branch = f"feat/{feature_id}"

    if not has_git(trunk):
        return MergeResult(ok=True, branch=source_branch)

    try:
        feature = read_doc(feature_id, root=trunk)
    except NotFound:
        return MergeResult(ok=False, reason="feature_not_found", branch=source_branch)

    if feature.meta.tier != "feature":
        return MergeResult(ok=False, reason="wrong_tier", branch=source_branch)

    epic_id = feature.meta.parent
    if not epic_id:
        return MergeResult(ok=False, reason="missing_parent", branch=source_branch)

    target_branch = f"epic/{epic_id}"
    if not _branch_exists(trunk, source_branch):
        return MergeResult(
            ok=False,
            reason="branch_missing",
            branch=source_branch,
            target_branch=target_branch,
        )

    aligned, align_reason = _operator_on_product_trunk(trunk)
    if not aligned:
        return MergeResult(
            ok=False,
            reason=align_reason or "wrong_branch",
            branch=source_branch,
            target_branch=target_branch,
        )

    merge_root = _epic_merge_checkout(trunk, epic_id)
    if merge_root is None:
        return MergeResult(
            ok=False,
            reason="merge_target_missing",
            branch=source_branch,
            target_branch=target_branch,
        )

    if not _branch_exists(trunk, target_branch):
        return MergeResult(
            ok=False,
            reason="merge_target_missing",
            branch=source_branch,
            target_branch=target_branch,
        )

    if _current_branch(merge_root) != target_branch:
        if _run(["checkout", target_branch], merge_root, check=False).returncode != 0:
            return MergeResult(
                ok=False,
                reason="merge_target_missing",
                branch=source_branch,
                target_branch=target_branch,
            )

    merge_sha = _merge_branch(merge_root, source_branch)
    if merge_sha is None:
        return MergeResult(
            ok=False,
            reason="merge_conflict",
            branch=source_branch,
            target_branch=target_branch,
        )

    return MergeResult(
        ok=True,
        merge_sha=merge_sha,
        branch=source_branch,
        target_branch=target_branch,
    )


def promote_epic_to_trunk(epic_id: str, *, root: Path | None = None) -> MergeResult:
    """Merge ``epic/{epic_id}`` into the product trunk checkout (human promote)."""

    trunk = resolve_root(root)
    source_branch = f"epic/{epic_id}"

    if not has_git(trunk):
        return MergeResult(ok=True, branch=source_branch)

    if not _branch_exists(trunk, source_branch):
        return MergeResult(ok=False, reason="branch_missing", branch=source_branch)

    aligned, align_reason = _operator_on_product_trunk(trunk)
    if not aligned:
        return MergeResult(ok=False, reason=align_reason or "wrong_branch", branch=source_branch)

    try:
        product_trunk = _mainline_branch(trunk)
    except Exception:
        product_trunk = None
    if product_trunk is None:
        return MergeResult(ok=False, reason="ambiguous_trunk", branch=source_branch)

    target_branch = product_trunk
    if _current_branch(trunk) != target_branch:
        return MergeResult(
            ok=False,
            reason="wrong_branch",
            branch=source_branch,
            target_branch=target_branch,
        )

    merge_sha = _merge_branch(trunk, source_branch)
    if merge_sha is None:
        return MergeResult(
            ok=False,
            reason="merge_conflict",
            branch=source_branch,
            target_branch=target_branch,
        )

    return MergeResult(
        ok=True,
        merge_sha=merge_sha,
        branch=source_branch,
        target_branch=target_branch,
    )


def _mainline_branch(repo: Path) -> str | None:
    """Product trunk for merges (``resolve_product_trunk``; None when ambiguous)."""

    from cascade.workspace.errors import WorkspaceError
    from cascade.workspace.trunk import resolve_product_trunk

    try:
        return resolve_product_trunk(repo)
    except WorkspaceError:
        return None


def _operator_on_product_trunk(trunk: Path) -> tuple[bool, str | None]:
    from cascade.workspace.errors import WorkspaceError
    from cascade.workspace.trunk import is_integration_branch, resolve_product_trunk

    current = _current_branch(trunk)
    if current is None:
        return False, "wrong_branch"
    if is_integration_branch(current):
        return False, "wrong_branch"
    try:
        product = resolve_product_trunk(trunk)
    except WorkspaceError:
        return False, "ambiguous_trunk"
    if current != product:
        return False, "wrong_branch"
    return True, None


def _feature_merge_checkout(trunk: Path, feature_id: str) -> Path | None:
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        integration_branch,
        repair_missing_worktree,
    )

    feat_branch = integration_branch("feature", feature_id)
    if not _branch_exists(trunk, feat_branch):
        return None
    repaired = repair_missing_worktree("feature", feature_id, trunk=trunk)
    if repaired is not None:
        return repaired.path
    entry = get_integration_worktree(trunk, "feature", feature_id)
    return entry.path if entry is not None else None


def _epic_merge_checkout(trunk: Path, epic_id: str) -> Path | None:
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        integration_branch,
        repair_missing_worktree,
    )

    epic_branch = integration_branch("epic", epic_id)
    if not _branch_exists(trunk, epic_branch):
        return None
    repaired = repair_missing_worktree("epic", epic_id, trunk=trunk)
    if repaired is not None:
        return repaired.path
    entry = get_integration_worktree(trunk, "epic", epic_id)
    return entry.path if entry is not None else None


def _current_branch(repo: Path) -> str | None:
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"], repo, check=False)
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    if not name or name == "HEAD":
        return None
    return name


def _worktree_clean(repo: Path) -> bool:
    """True when no staged or unstaged tracked changes (untracked files ignored)."""

    result = _run(["diff-index", "--quiet", "HEAD"], repo, check=False)
    return result.returncode == 0


def _merge_branch(repo: Path, branch: str) -> str | None:
    if _run(["merge", branch, "--no-edit"], repo, check=False).returncode != 0:
        _run(["merge", "--abort"], repo, check=False)
        return None
    sha = head_sha(repo)
    if sha is None:
        result = _run(["rev-parse", "HEAD"], repo, check=False)
        if result.returncode != 0:
            _run(["merge", "--abort"], repo, check=False)
            return None
        sha = result.stdout.strip() or None
    return sha


def _branch_exists(repo: Path, branch: str) -> bool:
    result = _run(["show-ref", "--verify", f"refs/heads/{branch}"], repo, check=False)
    return result.returncode == 0


def _sync_task_completed_on_trunk(trunk: Path, task_id: str, merge_root: Path) -> None:
    """When a task spec exists on both trunk and the feature worktree, complete both."""

    if merge_root.resolve() == trunk.resolve():
        return
    from cascade.board.store import list_board

    trunk_board = list_board(trunk)
    meta = trunk_board.by_id.get(task_id)
    if meta is None or meta.tier != "task":
        return
    if column_for_status(meta.status) == "completed":
        return
    move_doc(task_id, "completed", root=trunk)
