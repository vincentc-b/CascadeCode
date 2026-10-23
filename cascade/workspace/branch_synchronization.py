"""Inspect and update active integration branches (feat_016_001 / epic_016)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import _run, has_git, head_sha
from cascade.board.paths import column_for_status
from cascade.board.types import WorkMeta, WorkTier
from cascade.stacked_dispatch import review_target_branch
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.integration_worktree import (
    IntegrationKind,
    integration_branch,
    locate_trunk,
    merged_board,
    repair_missing_worktree,
)
from cascade.workspace.kickoff import _graph_has_inflight_turn
from cascade.workspace.trunk import is_integration_branch, resolve_product_trunk
from cascade.watchdog.lock import process_lock

SyncBlockReason = str


@dataclass(frozen=True)
class BranchSyncState:
    work_id: str
    tier: WorkTier
    work_branch: str
    base_branch: str
    ahead: int
    behind: int


@dataclass(frozen=True)
class BranchSyncInspection:
    ok: bool
    reason: str | None = None
    state: BranchSyncState | None = None
    update_blocked_reason: SyncBlockReason | None = None


@dataclass(frozen=True)
class BranchSyncUpdateResult:
    ok: bool
    reason: SyncBlockReason | None = None
    conflict_paths: tuple[str, ...] = ()
    merge_sha: str | None = None
    no_op: bool = False


def inspect_branch_synchronization(
    work_id: str, *, root: Path | None = None
) -> BranchSyncInspection:
    """Resolve base/ahead/behind for an active work item without mutating git state."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncInspection(ok=False, reason="not_a_git_repo")

    board = merged_board(trunk)
    meta_entry = board.by_id.get(work_id)
    if meta_entry is None:
        return BranchSyncInspection(ok=False, reason="not_found")
    meta = meta_entry

    kind = _integration_kind(meta.tier)
    if kind is None:
        return BranchSyncInspection(ok=False, reason="wrong_tier")

    if column_for_status(meta.status) != "active" or meta.status != "active":
        return BranchSyncInspection(ok=False, reason="not_active")

    base_branch = _resolve_base_branch(meta, trunk)
    if base_branch is None:
        return BranchSyncInspection(ok=False, reason="base_unresolved")

    work_branch = integration_branch(kind, work_id)
    if not _branch_exists(trunk, work_branch):
        return BranchSyncInspection(ok=False, reason="branch_missing")
    if not _branch_exists(trunk, base_branch):
        return BranchSyncInspection(ok=False, reason="base_missing")

    ahead, behind = _ahead_behind(trunk, work_branch, base_branch)
    if ahead is None or behind is None:
        return BranchSyncInspection(ok=False, reason="invariant")

    state = BranchSyncState(
        work_id=work_id,
        tier=meta.tier,
        work_branch=work_branch,
        base_branch=base_branch,
        ahead=ahead,
        behind=behind,
    )
    blocked = _preflight_blocked(meta, kind, trunk)
    return BranchSyncInspection(ok=True, state=state, update_blocked_reason=blocked)


def update_integration_branch(
    work_id: str, *, root: Path | None = None
) -> BranchSyncUpdateResult:
    """Merge the tier-aware base into the integration branch under ``process_lock``."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncUpdateResult(ok=False, reason="not_a_git_repo")

    with process_lock:
        inspection = inspect_branch_synchronization(work_id, root=trunk)
        if not inspection.ok or inspection.state is None:
            return BranchSyncUpdateResult(ok=False, reason=inspection.reason)

        if inspection.update_blocked_reason is not None:
            return BranchSyncUpdateResult(
                ok=False, reason=inspection.update_blocked_reason
            )

        state = inspection.state
        kind = _integration_kind(state.tier)
        assert kind is not None

        checkout = _resolve_integration_checkout(trunk, kind, work_id)
        if checkout is None:
            return BranchSyncUpdateResult(ok=False, reason="checkout_missing")

        if state.behind == 0:
            return BranchSyncUpdateResult(ok=True, no_op=True, merge_sha=head_sha(checkout))

        pre_sha = head_sha(checkout)
        if pre_sha is None:
            return BranchSyncUpdateResult(ok=False, reason="invariant")

        merge_result = _run(
            ["merge", state.base_branch, "--no-edit"], checkout, check=False
        )
        if merge_result.returncode == 0:
            post_sha = head_sha(checkout)
            no_op = post_sha == pre_sha
            return BranchSyncUpdateResult(
                ok=True, merge_sha=post_sha, no_op=no_op
            )

        conflict_paths = _validated_unmerged_paths(checkout)
        _run(["merge", "--abort"], checkout, check=False)
        if not _merge_state_clean(checkout):
            return BranchSyncUpdateResult(ok=False, reason="invariant")
        if head_sha(checkout) != pre_sha:
            _run(["reset", "--hard", pre_sha], checkout, check=False)
        if head_sha(checkout) != pre_sha:
            return BranchSyncUpdateResult(ok=False, reason="invariant")
        return BranchSyncUpdateResult(
            ok=False,
            reason="branch_conflict",
            conflict_paths=conflict_paths,
        )


def preflight_integration_sync(
    work_id: str, *, root: Path | None = None
) -> BranchSyncUpdateResult:
    """Read-only merge/update preflight for lifecycle callers (no merge attempted)."""

    inspection = inspect_branch_synchronization(work_id, root=root)
    if not inspection.ok:
        return BranchSyncUpdateResult(ok=False, reason=inspection.reason)
    if inspection.update_blocked_reason is not None:
        return BranchSyncUpdateResult(ok=False, reason=inspection.update_blocked_reason)
    return BranchSyncUpdateResult(ok=True)


def preflight_lifecycle_merge_target(
    work_id: str, *, root: Path | None = None
) -> BranchSyncUpdateResult:
    """Preflight the integration checkout that will receive a lifecycle merge."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncUpdateResult(ok=False, reason="not_a_git_repo")

    board = merged_board(trunk)
    meta = board.by_id.get(work_id)
    if meta is None:
        return BranchSyncUpdateResult(ok=False, reason="not_found")
    kind = _integration_kind(meta.tier)
    if kind is None:
        return BranchSyncUpdateResult(ok=False, reason="wrong_tier")
    if column_for_status(meta.status) != "active" or meta.status != "active":
        return BranchSyncUpdateResult(ok=False, reason="not_active")

    work_branch = integration_branch(kind, work_id)
    if not _branch_exists(trunk, work_branch):
        return BranchSyncUpdateResult(ok=False, reason="branch_missing")

    blocked = _preflight_blocked(meta, kind, trunk)
    if blocked is not None:
        return BranchSyncUpdateResult(ok=False, reason=blocked)
    return BranchSyncUpdateResult(ok=True)


def preflight_epic_trunk_promotion(
    epic_id: str, *, root: Path | None = None
) -> BranchSyncUpdateResult:
    """Preflight merging ``epic/{id}`` into the operator product-trunk checkout."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncUpdateResult(ok=False, reason="not_a_git_repo")

    blocked = _operator_trunk_cleanliness(trunk)
    if blocked is not None:
        return BranchSyncUpdateResult(ok=False, reason=blocked)

    board = merged_board(trunk)
    meta = board.by_id.get(epic_id)
    if meta is not None:
        if meta.tier != "epic":
            return BranchSyncUpdateResult(ok=False, reason="wrong_tier")
        if column_for_status(meta.status) != "active" or meta.status != "active":
            return BranchSyncUpdateResult(ok=False, reason="not_active")
        if _graph_has_inflight_turn(
            epic_id, "epic", root=trunk, feature_id=None
        ):
            return BranchSyncUpdateResult(ok=False, reason="busy")

    current = _current_branch(trunk)
    if current is None:
        return BranchSyncUpdateResult(ok=False, reason="wrong_branch")
    if is_integration_branch(current):
        return BranchSyncUpdateResult(ok=False, reason="wrong_branch")
    try:
        product = resolve_product_trunk(trunk)
    except WorkspaceError:
        return BranchSyncUpdateResult(ok=False, reason="ambiguous_trunk")
    if current != product:
        return BranchSyncUpdateResult(ok=False, reason="wrong_branch")

    return BranchSyncUpdateResult(ok=True)


def merge_lifecycle_source(
    checkout_work_id: str,
    source_branch: str,
    *,
    source_work_id: str | None = None,
    root: Path | None = None,
) -> BranchSyncUpdateResult:
    """Merge ``source_branch`` into the integration checkout for ``checkout_work_id``."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncUpdateResult(ok=False, reason="not_a_git_repo")

    with process_lock:
        preflight = preflight_lifecycle_merge_target(checkout_work_id, root=trunk)
        if not preflight.ok:
            return preflight

        if source_work_id is not None:
            board = merged_board(trunk)
            source_meta = board.by_id.get(source_work_id)
            if source_meta is not None:
                feature_id = (
                    source_meta.parent if source_meta.tier == "task" else None
                )
                if _graph_has_inflight_turn(
                    source_work_id,
                    source_meta.tier,
                    root=trunk,
                    feature_id=feature_id,
                ):
                    return BranchSyncUpdateResult(ok=False, reason="busy")

        board = merged_board(trunk)
        meta = board.by_id.get(checkout_work_id)
        if meta is None:
            return BranchSyncUpdateResult(ok=False, reason="not_found")
        kind = _integration_kind(meta.tier)
        if kind is None:
            return BranchSyncUpdateResult(ok=False, reason="wrong_tier")

        checkout = _resolve_integration_checkout(trunk, kind, checkout_work_id)
        if checkout is None:
            return BranchSyncUpdateResult(ok=False, reason="checkout_missing")

        if not _branch_exists(trunk, source_branch):
            return BranchSyncUpdateResult(ok=False, reason="branch_missing")

        pre_sha = head_sha(checkout)
        if pre_sha is None:
            return BranchSyncUpdateResult(ok=False, reason="invariant")

        if _run(["merge", source_branch, "--no-edit"], checkout, check=False).returncode == 0:
            return BranchSyncUpdateResult(ok=True, merge_sha=head_sha(checkout))

        conflict_paths = _validated_unmerged_paths(checkout)
        _run(["merge", "--abort"], checkout, check=False)
        if not _merge_state_clean(checkout):
            return BranchSyncUpdateResult(ok=False, reason="invariant")
        if head_sha(checkout) != pre_sha:
            _run(["reset", "--hard", pre_sha], checkout, check=False)
        if head_sha(checkout) != pre_sha:
            return BranchSyncUpdateResult(ok=False, reason="invariant")
        return BranchSyncUpdateResult(
            ok=False,
            reason="branch_conflict",
            conflict_paths=conflict_paths,
        )


def _integration_kind(tier: WorkTier) -> IntegrationKind | None:
    if tier == "epic":
        return "epic"
    if tier == "feature":
        return "feature"
    if tier == "task":
        return "task"
    return None


def _resolve_base_branch(meta: WorkMeta, trunk: Path) -> str | None:
    if meta.tier == "epic":
        try:
            return resolve_product_trunk(trunk)
        except WorkspaceError:
            return None
    if meta.tier == "feature":
        epic_id = meta.parent or ""
        if not epic_id:
            return None
        return review_target_branch(meta.id, epic_id, root=trunk)
    if meta.tier == "task":
        parent = meta.parent
        if not parent:
            return None
        return integration_branch("feature", parent)
    return None


def _resolve_integration_checkout(
    trunk: Path, kind: IntegrationKind, work_id: str
) -> Path | None:
    entry = repair_missing_worktree(kind, work_id, trunk=trunk)
    if entry is None or not entry.path.is_dir():
        return None
    return entry.path


def _preflight_blocked(
    meta: WorkMeta, kind: IntegrationKind, trunk: Path
) -> SyncBlockReason | None:
    feature_id = meta.parent if meta.tier == "task" else None
    if _graph_has_inflight_turn(
        meta.id, meta.tier, root=trunk, feature_id=feature_id
    ):
        return "busy"

    checkout = _resolve_integration_checkout(trunk, kind, meta.id)
    if checkout is None:
        return "checkout_missing"

    expected = integration_branch(kind, meta.id)
    current = _current_branch(checkout)
    if current != expected:
        return "wrong_branch"

    return _worktree_cleanliness(checkout)


def _worktree_cleanliness(repo: Path) -> SyncBlockReason | None:
    if _run(["diff", "--cached", "--quiet", "HEAD"], repo, check=False).returncode != 0:
        return "dirty_index"
    if _run(["diff", "--quiet", "HEAD"], repo, check=False).returncode != 0:
        return "local_changes"
    untracked = _run(
        ["ls-files", "--others", "--exclude-standard"], repo, check=False
    )
    if untracked.returncode == 0 and untracked.stdout.strip():
        return "local_changes"
    return None


def _operator_trunk_ignored(rel: str) -> bool:
    return rel.startswith((".cascade/", "docs/_queue/"))


def _operator_trunk_cleanliness(repo: Path) -> SyncBlockReason | None:
    """Product-trunk cleanliness for epic promotion (ignore linked worktree mounts)."""

    if _run(["diff", "--cached", "--quiet", "HEAD"], repo, check=False).returncode != 0:
        return "dirty_index"
    diff = _run(["diff", "--name-only", "HEAD"], repo, check=False)
    if diff.returncode != 0:
        return "local_changes"
    operator_changes = [
        path
        for path in diff.stdout.splitlines()
        if path and not _operator_trunk_ignored(path)
    ]
    if operator_changes:
        return "local_changes"
    untracked = _run(
        ["ls-files", "--others", "--exclude-standard"], repo, check=False
    )
    if untracked.returncode != 0:
        return "local_changes"
    operator_untracked = [
        path
        for path in untracked.stdout.splitlines()
        if path and not _operator_trunk_ignored(path)
    ]
    if operator_untracked:
        return "local_changes"
    return None


def _ahead_behind(
    repo: Path, work_branch: str, base_branch: str
) -> tuple[int | None, int | None]:
    result = _run(
        [
            "rev-list",
            "--left-right",
            "--count",
            f"{work_branch}...{base_branch}",
        ],
        repo,
        check=False,
    )
    if result.returncode != 0:
        return None, None
    parts = result.stdout.strip().split()
    if len(parts) != 2:
        return None, None
    try:
        ahead = int(parts[0])
        behind = int(parts[1])
    except ValueError:
        return None, None
    return ahead, behind


def _current_branch(repo: Path) -> str | None:
    result = _run(["rev-parse", "--abbrev-ref", "HEAD"], repo, check=False)
    if result.returncode != 0:
        return None
    name = result.stdout.strip()
    if not name or name == "HEAD":
        return None
    return name


def _branch_exists(repo: Path, branch: str) -> bool:
    result = _run(["show-ref", "--verify", f"refs/heads/{branch}"], repo, check=False)
    return result.returncode == 0


def validated_unmerged_paths(repo: Path) -> tuple[str, ...]:
    """Repository-relative unmerged paths during an in-progress merge (validated)."""

    return _validated_unmerged_paths(repo)


def _validated_unmerged_paths(repo: Path) -> tuple[str, ...]:
    conflicts = _run(
        ["diff", "--name-only", "--diff-filter=U", "-z"], repo, check=False
    )
    if conflicts.returncode != 0:
        return ()
    raw = [path for path in conflicts.stdout.split("\0") if path]
    repo_root = repo.resolve()
    validated: list[str] = []
    for rel in raw:
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            continue
        resolved = (repo_root / rel).resolve()
        try:
            resolved.relative_to(repo_root)
        except ValueError:
            continue
        validated.append(Path(rel).as_posix())
    return tuple(validated)


def _merge_state_clean(repo: Path) -> bool:
    merge_head = _run(["rev-parse", "-q", "MERGE_HEAD"], repo, check=False)
    return merge_head.returncode != 0
