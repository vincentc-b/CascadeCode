"""Inspect and update active integration branches (feat_016_001 / epic_016)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import SchemaError
from cascade.board.gitutil import _run, has_git, head_sha
from cascade.board.parse import parse_doc
from cascade.board.paths import column_for_status
from cascade.board.types import WorkMeta, WorkTier
from cascade.stacked_dispatch import review_target_branch
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.integration_worktree import (
    IntegrationKind,
    integration_branch,
    is_trunk_pointer,
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
    refusal_kind: str | None = None
    detail: str = ""
    owner_action: str = ""
    affected_ids: tuple[str, ...] = ()
    evidence_paths: tuple[str, ...] = ()


def inspect_branch_synchronization(
    work_id: str, *, root: Path | None = None, allow_completed_recovery: bool = False
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

    active = column_for_status(meta.status) == "active" and meta.status == "active"
    completed_recovery = (
        allow_completed_recovery
        and column_for_status(meta.status) == "completed"
        and meta.status == "completed"
    )
    if not active and not completed_recovery:
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


def _update_integration_branch(
    work_id: str, *, root: Path | None = None, allow_completed_recovery: bool = False
) -> BranchSyncUpdateResult:
    """Merge the tier-aware base into the integration branch under ``process_lock``."""

    trunk = locate_trunk(resolve_root(root))
    if not has_git(trunk):
        return BranchSyncUpdateResult(ok=False, reason="not_a_git_repo")

    with process_lock:
        inspection = inspect_branch_synchronization(
            work_id, root=trunk, allow_completed_recovery=allow_completed_recovery
        )
        if not inspection.ok or inspection.state is None:
            return BranchSyncUpdateResult(ok=False, reason=inspection.reason)

        state = inspection.state
        already_integrated = state.behind == 0 and inspection.update_blocked_reason == "busy"
        if inspection.update_blocked_reason is not None and not already_integrated:
            return BranchSyncUpdateResult(
                ok=False, reason=inspection.update_blocked_reason
            )

        kind = _integration_kind(state.tier)
        assert kind is not None

        checkout = _resolve_integration_checkout(trunk, kind, work_id)
        if checkout is None:
            return BranchSyncUpdateResult(ok=False, reason="checkout_missing")
        meta = merged_board(trunk).by_id.get(work_id)

        if state.behind == 0:
            # The owning team can finish a repair during its own live turn.
            # Acknowledging an already-integrated base performs no Git mutation
            # and must not self-refuse as busy. All checkout invariants remain.
            if meta is None:
                return BranchSyncUpdateResult(ok=False, reason="not_found")
            blocked = _preflight_blocked(meta, kind, trunk, ignore_inflight=True)
            if blocked is not None:
                return BranchSyncUpdateResult(ok=False, reason=blocked)
            if not _merge_state_clean(checkout):
                return BranchSyncUpdateResult(ok=False, reason="invariant")
            if _run(["merge-base", "--is-ancestor", state.base_branch, "HEAD"], checkout, check=False).returncode != 0:
                return BranchSyncUpdateResult(ok=False, reason="busy" if already_integrated else "invariant")
            return BranchSyncUpdateResult(ok=True, no_op=True, merge_sha=head_sha(checkout))

        pre_sha = head_sha(checkout)
        if pre_sha is None:
            return BranchSyncUpdateResult(ok=False, reason="invariant")

        merge_result = _run(
            ["merge", state.base_branch, "--no-edit"], checkout, check=False
        )
        if merge_result.returncode == 0:
            if not _prune_stale_completed_epic_pointers(checkout, state.base_branch):
                return BranchSyncUpdateResult(ok=False, reason="invariant")
            post_sha = head_sha(checkout)
            no_op = post_sha == pre_sha
            return BranchSyncUpdateResult(
                ok=True, merge_sha=post_sha, no_op=no_op
            )

        conflict_paths = _validated_unmerged_paths(checkout)
        resolved_sha = _resolve_managed_pointer_conflict(
            checkout,
            meta=meta,
            state=state,
            conflict_paths=conflict_paths,
        )
        if resolved_sha is not None:
            if not _prune_stale_completed_epic_pointers(checkout, state.base_branch):
                return BranchSyncUpdateResult(ok=False, reason="invariant")
            return BranchSyncUpdateResult(ok=True, merge_sha=head_sha(checkout))
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


def update_integration_branch(
    work_id: str, *, root: Path | None = None
) -> BranchSyncUpdateResult:
    """Update one integration branch and durably hand off its first failure.

    The underlying operation remains intentionally unaware of recovery.  This
    thin boundary makes direct operator calls and supervisor calls share the
    same stable action identity without changing their returned result.
    """

    result = _update_integration_branch(work_id, root=root)
    if result.ok:
        return result
    try:
        from cascade.task.action_recovery import capture_and_route_action_failure

        target = _recovery_target_ref(work_id, root=root)
        capture_and_route_action_failure(
            f"{work_id}:integration_branch_update",
            "integration_branch_update",
            affected_work_id=work_id,
            intended_target_ref=target,
            root=resolve_root(root),
            failure_code=result.reason or "branch_update_failed",
            safe_summary=f"Integration branch update for {work_id} was unsuccessful.",
            conflicting_paths=list(result.conflict_paths),
        )
    except Exception:
        # Recovery must never replace the operator's original refusal.  Its
        # next invocation will retry the durable capture with the same id.
        pass
    return result


def _recovery_target_ref(work_id: str, *, root: Path | None) -> str | None:
    """Return the intended integration boundary without guessing from refs."""

    try:
        from cascade.board.store import read_doc

        doc = read_doc(work_id, root=resolve_root(root))
    except Exception:
        return None
    if doc.meta.tier == "task" and doc.meta.parent:
        return f"feat/{doc.meta.parent}"
    if doc.meta.tier == "feature" and doc.meta.parent:
        return f"epic/{doc.meta.parent}"
    if doc.meta.tier == "epic":
        return "trunk"
    return None


def _prune_stale_completed_epic_pointers(checkout: Path, base_branch: str) -> bool:
    """Drop old pointers only when the merged base replaced them with completed Epics."""

    epic_dir = checkout / "docs" / "epics"
    completed: dict[str, Path] = {}
    for path in (epic_dir / "3_completed").glob("*.md"):
        if path.is_symlink():
            continue
        try:
            doc = parse_doc(path)
        except (SchemaError, OSError):
            continue
        if doc.meta.tier == "epic" and doc.meta.status == "completed":
            completed[doc.meta.id] = path

    stale: list[str] = []
    for path in (epic_dir / "2_active").glob("*.md"):
        if path.is_symlink():
            continue
        try:
            doc = parse_doc(path)
        except (SchemaError, OSError):
            continue
        if doc.meta.status != "active" or not is_trunk_pointer(doc.meta):
            continue
        replacement = completed.get(doc.meta.id)
        if replacement is None:
            continue
        active_rel = path.relative_to(checkout).as_posix()
        completed_rel = replacement.relative_to(checkout).as_posix()
        if _run(["show", f"{base_branch}:{completed_rel}"], checkout, check=False).returncode != 0:
            continue
        if _run(["show", f"{base_branch}:{active_rel}"], checkout, check=False).returncode == 0:
            continue
        stale.append(active_rel)

    if not stale:
        return True
    if _run(["rm", "--", *stale], checkout, check=False).returncode != 0:
        return False
    commit = _run(
        ["-c", "commit.gpgsign=false", "commit", "-m", "docs: remove stale completed epic pointers"],
        checkout,
        check=False,
    )
    return commit.returncode == 0


def _resolve_managed_pointer_conflict(
    checkout: Path,
    *,
    meta: WorkMeta | None,
    state: BranchSyncState,
    conflict_paths: tuple[str, ...],
) -> str | None:
    """Keep the live integration spec when its managed base pointer conflicts.

    Activation writes the authoritative document to the new integration branch
    and then writes a pointer at the same active path on its base branch. A later
    base update sees those independently-added files as a conflict even though
    their ownership is unambiguous. Resolve only that single, recognizable
    pointer conflict; all content conflicts remain aborted for explicit review.
    """

    if meta is None or len(conflict_paths) != 1:
        return None
    try:
        live_rel = meta.path.resolve().relative_to(checkout.resolve()).as_posix()
    except ValueError:
        return None
    if conflict_paths != (live_rel,):
        return None

    pointer = _run(
        ["show", f"{state.base_branch}:{live_rel}"], checkout, check=False
    )
    live = _run(["show", f":2:{live_rel}"], checkout, check=False)
    if pointer.returncode != 0 or live.returncode != 0:
        return None

    pointer_markers = (
        f"id: {state.work_id}",
        f"integration_branch: {state.work_branch}",
        f"Live {state.tier} spec is on branch `{state.work_branch}`",
    )
    if not all(marker in pointer.stdout for marker in pointer_markers):
        return None
    if f"id: {state.work_id}" not in live.stdout:
        return None
    if "integration_worktree:" in live.stdout:
        return None

    if _run(["checkout", "--ours", "--", live_rel], checkout, check=False).returncode != 0:
        return None
    if _run(["add", "--", live_rel], checkout, check=False).returncode != 0:
        return None
    if _validated_unmerged_paths(checkout):
        return None
    commit = _run(
        ["-c", "commit.gpgsign=false", "commit", "--no-edit"],
        checkout,
        check=False,
    )
    if commit.returncode != 0 or not _merge_state_clean(checkout):
        return None
    return head_sha(checkout)


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
    work_id: str, *, source_work_id: str | None = None, root: Path | None = None
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
    # Derived monitoring blockage must not prevent the child integration
    # which resolves it. Manual blockage and unrelated lifecycle gates remain.
    derived = meta.status == "blocked" and any(b.blocked_supervisor for b in meta.monitoring_blockers)
    # A Feature can enter the completed column when its PR is opened. An
    # explicitly minted repair Task may finish before that PR is merged. Admit
    # only that owned, active child while the Feature has no terminal rollup.
    completed_feature_repair = False
    if (
        meta.tier == "feature"
        and meta.status == "completed"
        and meta.path.parent.name == "3_completed"
        and source_work_id in meta.children
    ):
        source = board.by_id.get(source_work_id)
        if (
            source is not None
            and source.tier == "task"
            and source.parent == work_id
            and source.status == "active"
            and source.path.parent.name == "2_active"
            and meta.parent
        ):
            from cascade.boss.rollup import feature_completed_recorded

            completed_feature_repair = not feature_completed_recorded(
                work_id, meta.parent, root=trunk
            )
    if not completed_feature_repair and (
        column_for_status(meta.status) != "active"
        or (meta.status != "active" and not derived)
    ):
        return BranchSyncUpdateResult(ok=False, reason="not_active")

    work_branch = integration_branch(kind, work_id)
    if not _branch_exists(trunk, work_branch):
        return BranchSyncUpdateResult(ok=False, reason="branch_missing")

    # This gate is intentionally read-only. Missing checkout repair is a
    # separate owner-authorized recovery action; recreating it here would
    # mutate the registry/worktree before the exact candidate is proved.
    blocked = _preflight_blocked(meta, kind, trunk, repair_missing=False)
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
        preflight = preflight_lifecycle_merge_target(
            checkout_work_id, source_work_id=source_work_id, root=trunk
        )
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
                if source_meta.tier == "task":
                    from cascade.task.worktree import task_worktree_has_changes
                    if task_worktree_has_changes(source_work_id, root=trunk):
                        return BranchSyncUpdateResult(ok=False, reason="source_dirty")

        board = merged_board(trunk)
        meta = board.by_id.get(checkout_work_id)
        if meta is None:
            return BranchSyncUpdateResult(ok=False, reason="not_found")
        kind = _integration_kind(meta.tier)
        if kind is None:
            return BranchSyncUpdateResult(ok=False, reason="wrong_tier")

        checkout = _existing_integration_checkout(trunk, kind, checkout_work_id)
        if checkout is None:
            return BranchSyncUpdateResult(ok=False, reason="checkout_missing")

        if not _branch_exists(trunk, source_branch):
            return BranchSyncUpdateResult(ok=False, reason="branch_missing")

        return merge_exact_lifecycle_candidate(
            trunk,
            checkout,
            source_branch,
            integration_branch(kind, checkout_work_id),
            owner_work_id=checkout_work_id,
            owner_tier=meta.tier,
            owner_parent=meta.parent,
        )


def merge_exact_lifecycle_candidate(
    repository: Path,
    checkout: Path,
    source_ref: str,
    target_ref: str,
    *,
    prefer_source_paths: tuple[str, ...] = (),
    owner_work_id: str | None = None,
    owner_tier: str | None = None,
    owner_parent: str | None = None,
    owner_must_match_checkout: bool = True,
) -> BranchSyncUpdateResult:
    """Prove and merge one exact lifecycle pair without mutating on refusal."""

    from cascade.review_validation import (
        ExactMergeCandidate,
        MergeCandidateRefusal,
        TerminalHistoryRefusal,
        materialize_exact_merge_candidate,
        prove_accepted_terminal_history,
    )

    source_sha = _ref_commit(repository, source_ref)
    target_sha = head_sha(checkout)
    if source_sha is None:
        return BranchSyncUpdateResult(ok=False, reason="branch_missing")
    if target_sha is None:
        return BranchSyncUpdateResult(ok=False, reason="invariant")
    if _ref_commit(repository, target_ref) != target_sha:
        return BranchSyncUpdateResult(
            ok=False,
            reason="target_changed",
            refusal_kind="target_changed",
            detail=f"target {target_ref} does not name checkout head {target_sha}",
            owner_action="refresh the target and prove a new exact candidate",
        )

    history_repository = repository
    history_revision = target_sha
    history_candidate_root: Path | None = None
    history_owner_root = repository
    bound_owner: Path | None = None
    if owner_work_id is not None:
        owner_binding = _bind_lifecycle_mutation_owner(
            repository,
            checkout,
            owner_work_id,
            owner_tier,
            owner_parent,
            must_match_checkout=owner_must_match_checkout,
        )
        if isinstance(owner_binding, BranchSyncUpdateResult):
            return owner_binding
        bound_owner, split_owner = owner_binding
        history_owner_root = bound_owner
        if split_owner:
            owner_revision = head_sha(bound_owner)
            if owner_revision is None or _worktree_cleanliness(bound_owner) is not None:
                return _owner_evidence_refusal(
                    owner_work_id,
                    "the canonical tracking owner is not a clean pinned checkout",
                    "restore or commit the canonical tracking owner, then prove a new candidate",
                )
            history_repository = bound_owner
            history_revision = owner_revision
            history_candidate_root = bound_owner

    with materialize_exact_merge_candidate(
        repository,
        source_sha,
        target_sha,
        prefer_source_paths=prefer_source_paths,
    ) as materialized:
        if isinstance(materialized, MergeCandidateRefusal):
            return BranchSyncUpdateResult(
                ok=False,
                reason=(
                    "branch_conflict"
                    if materialized.kind == "conflict"
                    else f"candidate_{materialized.kind}"
                ),
                conflict_paths=materialized.conflicted_paths,
                refusal_kind=materialized.kind,
                detail=materialized.message,
                owner_action=materialized.owner_action,
            )
        assert isinstance(materialized, ExactMergeCandidate)
        if history_candidate_root is not None:
            product_history = prove_accepted_terminal_history(
                repository,
                materialized,
                target_sha,
                candidate_board_root=materialized.checkout,
                owner_root=history_owner_root,
                target_ref=target_ref,
            )
            if isinstance(product_history, TerminalHistoryRefusal):
                return BranchSyncUpdateResult(
                    ok=False,
                    reason=f"board_history_{product_history.kind}",
                    refusal_kind=product_history.kind,
                    detail=product_history.reason,
                    owner_action=product_history.owner_action,
                    affected_ids=product_history.affected_ids,
                    evidence_paths=product_history.paths,
                )
        history = prove_accepted_terminal_history(
            history_repository,
            materialized,
            history_revision,
            accepted_repository=history_repository,
            candidate_board_root=history_candidate_root,
            owner_root=history_owner_root,
            target_ref=target_ref if history_repository == repository else None,
        )
        if isinstance(history, TerminalHistoryRefusal):
            return BranchSyncUpdateResult(
                ok=False,
                reason=f"board_history_{history.kind}",
                refusal_kind=history.kind,
                detail=history.reason,
                owner_action=history.owner_action,
                affected_ids=history.affected_ids,
                evidence_paths=history.paths,
            )

        if owner_work_id is not None:
            refreshed = _bind_lifecycle_mutation_owner(
                repository,
                checkout,
                owner_work_id,
                owner_tier,
                owner_parent,
                must_match_checkout=owner_must_match_checkout,
            )
            if isinstance(refreshed, BranchSyncUpdateResult):
                return refreshed
            refreshed_owner, refreshed_split = refreshed
            if refreshed_owner != bound_owner:
                return _owner_evidence_refusal(
                    owner_work_id,
                    "the canonical mutation owner changed after candidate proof",
                    "refresh the owner and prove a new exact candidate",
                )
            if refreshed_split and (
                head_sha(refreshed_owner) != history_revision
                or _worktree_cleanliness(refreshed_owner) is not None
            ):
                return _owner_evidence_refusal(
                    owner_work_id,
                    "the canonical tracking owner changed after candidate proof",
                    "refresh the tracking owner and prove a new exact candidate",
                )

        # Fence both moving refs after the fresh scan/proof.  Merge the proven
        # source object, not a ref that could move between this check and Git.
        if _ref_commit(repository, source_ref) != materialized.source_sha:
            return BranchSyncUpdateResult(
                ok=False,
                reason="source_changed",
                refusal_kind="source_changed",
                detail=f"source {source_ref} moved after candidate proof",
                owner_action="refresh both heads and prove a new exact candidate",
            )
        if (
            head_sha(checkout) != materialized.target_sha
            or _ref_commit(repository, target_ref) != materialized.target_sha
        ):
            return BranchSyncUpdateResult(
                ok=False,
                reason="target_changed",
                refusal_kind="target_changed",
                detail=f"target {target_ref} moved after candidate proof",
                owner_action="refresh the target and prove a new exact candidate",
            )

        merge = _run(
            ["merge", "--no-commit", "--no-ff", materialized.source_sha],
            checkout,
            check=False,
        )
        if merge.returncode != 0:
            conflict_paths = _validated_unmerged_paths(checkout)
            safe_preference = bool(prefer_source_paths) and all(
                path
                and not Path(path).is_absolute()
                and ".." not in Path(path).parts
                for path in prefer_source_paths
            )
            if safe_preference and set(conflict_paths) == set(prefer_source_paths):
                resolved = _run(
                    ["checkout", materialized.source_sha, "--", *prefer_source_paths],
                    checkout,
                    check=False,
                )
                conflict_paths = _validated_unmerged_paths(checkout)
                if resolved.returncode == 0 and not conflict_paths:
                    merge = resolved
            if merge.returncode != 0:
                _run(["merge", "--abort"], checkout, check=False)
                return BranchSyncUpdateResult(
                    ok=False,
                    reason="branch_conflict" if conflict_paths else "invariant",
                    conflict_paths=conflict_paths,
                )

        merge_head = _run(["rev-parse", "-q", "MERGE_HEAD"], checkout, check=False)
        if merge_head.returncode != 0:
            return BranchSyncUpdateResult(
                ok=True, merge_sha=head_sha(checkout), no_op=True
            )
        observed_tree = _run(["write-tree"], checkout, check=False)
        if (
            observed_tree.returncode != 0
            or observed_tree.stdout.strip() != materialized.result_tree
        ):
            _run(["merge", "--abort"], checkout, check=False)
            return BranchSyncUpdateResult(
                ok=False,
                reason="candidate_result_changed",
                refusal_kind="target_changed",
                detail="the real merge tree did not match the proven candidate tree",
                owner_action="refresh both heads and prove a new exact candidate",
            )
        committed = _run(
            ["-c", "commit.gpgsign=false", "commit", "--no-edit"],
            checkout,
            check=False,
        )
        if committed.returncode != 0:
            _run(["merge", "--abort"], checkout, check=False)
            return BranchSyncUpdateResult(ok=False, reason="invariant")
        return BranchSyncUpdateResult(ok=True, merge_sha=head_sha(checkout))


def _ref_commit(repo: Path, ref: str) -> str | None:
    result = _run(["rev-parse", "--verify", f"{ref}^{{commit}}"], repo, check=False)
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


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


def _existing_integration_checkout(
    trunk: Path, kind: IntegrationKind, work_id: str
) -> Path | None:
    """Return the registered checkout without repairing or publishing state."""

    from cascade.workspace.integration_worktree import get_integration_worktree

    entry = get_integration_worktree(trunk, kind, work_id)
    if entry is None or not entry.path.is_dir():
        return None
    return entry.path


def _owner_evidence_refusal(
    work_id: str, detail: str, owner_action: str
) -> BranchSyncUpdateResult:
    return BranchSyncUpdateResult(
        ok=False,
        reason="board_history_evidence_unavailable",
        refusal_kind="evidence_unavailable",
        detail=f"{work_id}: {detail}",
        owner_action=owner_action,
        affected_ids=(work_id,),
    )


def _bind_lifecycle_mutation_owner(
    repository: Path,
    checkout: Path,
    work_id: str,
    tier: str | None,
    parent: str | None,
    *,
    must_match_checkout: bool,
) -> tuple[Path, bool] | BranchSyncUpdateResult:
    """Bind the exact registered product/tracking owner without repairing it."""

    from cascade.board.context import get_project_context
    from cascade.workspace.errors import MutationOwnerError
    from cascade.workspace.integration_worktree import resolve_mutation_owner

    try:
        owner = resolve_mutation_owner(
            work_id, trunk=repository, tier=tier, parent=parent
        ).resolve()
    except MutationOwnerError as exc:
        return _owner_evidence_refusal(work_id, exc.reason, exc.action)

    project = get_project_context()
    split_owner = bool(
        project is not None
        and project.target.root.resolve() != project.tracking.root.resolve()
    )
    if split_owner:
        target = locate_trunk(project.target.root).resolve()
        tracking = locate_trunk(project.tracking.root).resolve()
        if repository.resolve() != target or not (
            owner == tracking or owner.is_relative_to(tracking / ".cascade")
        ):
            return _owner_evidence_refusal(
                work_id,
                "the registered product/tracking roots do not match this merge boundary",
                "retry from the registered product root after repairing tracking ownership",
            )
    elif must_match_checkout and owner != checkout.resolve():
        return _owner_evidence_refusal(
            work_id,
            f"registered owner {owner} is not merge checkout {checkout.resolve()}",
            "restore the exact registered checkout before proving a new candidate",
        )
    return owner, split_owner


def _preflight_blocked(
    meta: WorkMeta,
    kind: IntegrationKind,
    trunk: Path,
    *,
    ignore_inflight: bool = False,
    repair_missing: bool = True,
) -> SyncBlockReason | None:
    feature_id = meta.parent if meta.tier == "task" else None
    if not ignore_inflight and _graph_has_inflight_turn(
        meta.id, meta.tier, root=trunk, feature_id=feature_id
    ):
        return "busy"

    checkout = (
        _resolve_integration_checkout(trunk, kind, meta.id)
        if repair_missing
        else _existing_integration_checkout(trunk, kind, meta.id)
    )
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
    untracked_source = [
        path
        for path in untracked.stdout.splitlines()
        if path and not _managed_runtime_path(path)
    ]
    if untracked.returncode != 0 or untracked_source:
        return "local_changes"
    return None


def _managed_runtime_path(rel: str) -> bool:
    return rel.startswith(
        (".cascade/", "docs/_queue/", "docs/_comments/", "docs/_war_room/")
    )


def _operator_trunk_ignored(rel: str) -> bool:
    return _managed_runtime_path(rel)


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
