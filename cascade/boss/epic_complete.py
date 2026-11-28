"""Epic completion gates, human confirm, and war_room close prompt (task_042).

War Room prompt (``docs/_queue/war_room.jsonl``, event type ``Toast``):

- ``payload["kind"]``: ``"epic_ready_to_close"``
- ``payload["epic_id"]`` and ``payload["id"]``: the epic work id (stable for task_044)
- ``payload["message"]`` / ``payload["body"]``: short human-readable text

Idempotency (``surface_epic_close_prompt``): while an epic is ready to close, at most
one Toast is appended per ``(resolved repo root, epic_id)`` per process. A module-local
set records surfaces; repeat calls are no-ops. Use ``reset_epic_close_prompt_surfaces()``
in tests to clear that set.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import GitError, NotFound
from cascade.board.store import move_doc, read_doc
from cascade.board.types import WorkId, WorkMeta
from cascade.comments.store import read_comments
from cascade.review import (
    EpicCloseBlocker,
    EpicCloseStage,
    EpicReviewSnapshot,
    ForgeReviewState,
    epic_review_snapshot,
    persist_epic_review_snapshot,
    refresh_epic_review_snapshot,
    validate_review_url,
)
from cascade.tracking import MergeRequest
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event, Principal

_TOAST_KIND = "epic_ready_to_close"
_LOG = logging.getLogger(__name__)
_surfaced_prompts: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class EpicCompleteResult:
    ok: bool
    reason: str | None = None
    blocker_ids: tuple[WorkId, ...] = ()
    conflict_paths: tuple[str, ...] = ()
    review_url: str | None = None
    close_stage: EpicCloseStage | None = None
    source_branch: str | None = None
    target_branch: str | None = None
    forge_state: ForgeReviewState = "unknown"
    blocker: EpicCloseBlocker | None = None

    def __post_init__(self) -> None:
        if self.review_url is not None:
            validate_review_url(self.review_url)
        if self.close_stage == "blocked" and self.blocker is None:
            raise ValueError(
                "blocked epic close result requires actionable blocker details"
            )


def reset_epic_close_prompt_surfaces() -> None:
    """Clear in-process ``surface_epic_close_prompt`` deduplication (tests only)."""

    _surfaced_prompts.clear()


def epic_ready_to_close(epic_id: WorkId, *, root: Path | None = None) -> bool:
    """True when every child feature is delivered or explicitly removed from scope."""

    repo = resolve_root(root)
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    return _epic_ready_to_close(epic_id, repo=repo, board=board)


def _epic_ready_to_close(epic_id: WorkId, *, repo: Path, board) -> bool:
    return _epic_close_blocker(epic_id, repo=repo, board=board) is None


def _epic_close_blocker(
    epic_id: WorkId, *, repo: Path, board
) -> EpicCompleteResult | None:
    """Return the first actionable closeout blocker, if any.

    Keep the public boolean readiness check for existing callers, but retain the
    specific gate for the human close endpoint.  A generic ``not_ready`` left
    operators unable to distinguish unfinished work from a comment thread that
    merely needed resolving.
    """

    if epic_id not in board.by_id:
        return EpicCompleteResult(ok=False, reason="not_ready")
    epic_meta = board.by_id[epic_id]
    if epic_meta.tier != "epic":
        return EpicCompleteResult(ok=False, reason="wrong_tier")
    incomplete = _incomplete_child_feature_ids(epic_id, board)
    if incomplete is None:
        return EpicCompleteResult(ok=False, reason="no_child_features")
    if not incomplete:
        from cascade.board.store import list_board
        from cascade.workspace.integration_worktree import get_integration_worktree

        epic_entry = get_integration_worktree(repo, "epic", epic_id)
        if epic_entry is not None and epic_entry.path.is_dir():
            # A completed source worktree can hide an open copy on the epic
            # branch. Check any child docs the epic review would publish.
            epic_board = list_board(epic_entry.path)
            for feature_id in _child_feature_ids(epic_id, board):
                meta = epic_board.by_id.get(feature_id)
                if (
                    meta is not None
                    and meta.tier == "feature"
                    and not _child_feature_satisfies_closeout(meta, epic_meta)
                ):
                    incomplete.add(feature_id)
    if incomplete:
        return EpicCompleteResult(
            ok=False,
            reason="child_features_incomplete",
            blocker_ids=tuple(sorted(incomplete)),
        )
    from cascade.review import epic_has_pending_feature_review

    if epic_has_pending_feature_review(epic_id, root=repo):
        return EpicCompleteResult(ok=False, reason="pending_feature_review")
    open_comments = _open_human_comment_ids(epic_id, repo)
    if open_comments:
        return EpicCompleteResult(
            ok=False,
            reason="open_human_comments",
            blocker_ids=tuple(open_comments),
        )
    return None


def surface_epic_close_prompt(epic_id: WorkId, *, root: Path | None = None) -> None:
    """Append a war_room Toast when the epic is ready; idempotent per process (see module doc)."""

    repo = resolve_root(root)
    if not epic_ready_to_close(epic_id, root=repo):
        return
    key = (str(repo.resolve()), epic_id)
    message = f"Epic {epic_id} is ready to close"
    with process_lock:
        if key in _surfaced_prompts:
            return
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload={
                    "kind": _TOAST_KIND,
                    "id": epic_id,
                    "epic_id": epic_id,
                    "message": message,
                    "body": message,
                },
                dest="war_room",
            ),
            root=repo,
        )
        _surfaced_prompts.add(key)


def epic_completed_recorded(epic_id: WorkId, *, root: Path) -> bool:
    """True when ``EpicCompleted`` for ``epic_id`` is already on ``war_room``."""

    events, _ = read_events("war_room", 0, root=root)
    return any(
        event.type == "EpicCompleted" and event.payload.get("epic_id") == epic_id
        for event in events
    )


def try_complete_epic(epic_id: WorkId, *, root: Path | None = None) -> bool:
    """Complete the epic when every persisted child feature is terminal; idempotent."""

    return try_complete_epic_result(epic_id, root=root).ok


def try_complete_epic_result(
    epic_id: WorkId, *, root: Path | None = None
) -> EpicCompleteResult:
    """Reconcile one Epic while retaining its durable publication result."""

    # Automatic recovery and a concurrent human Close share the same
    # check/create boundary. The durable review/event stores provide
    # idempotency after this in-process serialization point.
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=resolve_root(root)):
        return _finish_epic_completion_result(epic_id, root=root)


def confirm_epic_complete(
    epic_id: WorkId, by: Principal, *, root: Path | None = None
) -> bool:
    """Human-only: move the epic to completed and emit ``EpicCompleted`` on ``war_room``."""

    return confirm_epic_complete_result(epic_id, by, root=root).ok


def confirm_epic_complete_result(
    epic_id: WorkId, by: Principal, *, root: Path | None = None
) -> EpicCompleteResult:
    """Complete an epic and retain the refusal reason for API callers."""

    if by != "human":
        return EpicCompleteResult(ok=False, reason="unauthorized")
    # Serialize the check/create boundary so concurrent Close requests in this
    # process cannot both observe an absent snapshot and publish reviews.
    from cascade.task.lifecycle_lock import task_lifecycle_lock

    with task_lifecycle_lock(root=resolve_root(root)):
        return _finish_epic_completion_result(epic_id, root=root)


def _finish_epic_completion(epic_id: WorkId, *, root: Path | None = None) -> bool:
    """Boolean compatibility wrapper for automatic lifecycle reconciliation."""

    return _finish_epic_completion_result(epic_id, root=root).ok


def _finish_epic_completion_result(
    epic_id: WorkId, *, root: Path | None = None
) -> EpicCompleteResult:
    repo = resolve_root(root)
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    if epic_id not in board.by_id:
        return EpicCompleteResult(ok=False, reason="not_ready")
    epic_meta = board.by_id[epic_id]
    if epic_meta.tier != "epic":
        return EpicCompleteResult(ok=False, reason="wrong_tier")
    if epic_meta.status == "completed" and epic_meta.path.parent.name == "3_completed":
        if _completed_on_operator_trunk(epic_id, repo):
            review_state = epic_review_snapshot(epic_id, root=repo)
            if review_state is not None and not (
                review_state.stage == "completed" and review_state.verified_closure
            ):
                review_state = refresh_epic_review_snapshot(epic_id, root=repo)
                if (
                    review_state is None
                    or review_state.stage == "blocked"
                    or review_state.forge_state != "merged"
                ):
                    return (
                        _epic_review_result(review_state)
                        if review_state is not None
                        else EpicCompleteResult(ok=False, reason="review_failed")
                    )
                from cascade.review import detect_forge

                forge = detect_forge(repo)
                review = MergeRequest(
                    url=review_state.review_url or "",
                    number=None,
                    forge=forge or "github",
                    source_branch=review_state.source_branch or "",
                    target_branch=review_state.target_branch or "",
                    draft=False,
                )
                if (
                    forge is None
                    or _merged_epic_review_landed(epic_id, review, repo) is None
                ):
                    latest = epic_review_snapshot(epic_id, root=repo)
                    return (
                        _epic_review_result(latest)
                        if latest is not None and latest.stage == "blocked"
                        else EpicCompleteResult(ok=False, reason="verification_pending")
                    )
                review_state = epic_review_snapshot(epic_id, root=repo)
                if review_state is None or not review_state.verified_closure:
                    return EpicCompleteResult(ok=False, reason="verification_pending")
                if not persist_epic_review_snapshot(
                    epic_id,
                    _completed_epic_snapshot(review_state),
                    root=repo,
                    expected=review_state,
                ):
                    return EpicCompleteResult(
                        ok=False, reason="verification_pending"
                    )
            _emit_epic_completed(epic_id, repo)
            _retire_epic_worktree(epic_id, repo)
            return EpicCompleteResult(ok=True, close_stage="completed")
        review_state = epic_review_snapshot(epic_id, root=repo)
        if (
            review_state is not None
            and review_state.stage == "completed"
            and review_state.verified_closure
        ):
            _emit_epic_completed(epic_id, repo)
            return EpicCompleteResult(
                ok=True, close_stage="completed", forge_state="merged"
            )
    from cascade.lifecycle_review_gate import require_lifecycle_review_gate
    from cascade.workspace.architecture_review import ArchitectureProposalError

    try:
        require_lifecycle_review_gate(epic_id, "closeout", root=repo)
    except ArchitectureProposalError as exc:
        return EpicCompleteResult(ok=False, reason=str(exc))
    blocker = _epic_close_blocker(epic_id, repo=repo, board=board)
    if blocker is not None:
        return blocker
    try:
        epic_doc = read_doc(epic_id, root=repo)
    except NotFound:
        return EpicCompleteResult(ok=False, reason="not_found")
    from cascade.boss.merge import promote_epic_to_trunk
    from cascade.review import ensure_epic_review

    persisted = refresh_epic_review_snapshot(epic_id, root=repo)
    review = None
    if persisted is not None:
        if persisted.stage == "blocked" or persisted.forge_state != "merged":
            return _epic_review_result(persisted)
        from cascade.review import detect_forge

        forge = detect_forge(repo)
        if forge is None:
            # refresh would already have persisted a blocker in this case.
            return _epic_review_result(persisted)
        review = MergeRequest(
            url=persisted.review_url or "",
            number=None,
            forge=forge,
            source_branch=persisted.source_branch or "",
            target_branch=persisted.target_branch or "",
            draft=False,
        )
    else:
        try:
            review = ensure_epic_review(epic_id, root=repo)
        except GitError:
            _LOG.exception("could not open epic review for %s", epic_id)
            return EpicCompleteResult(
                ok=False,
                reason="review_failed",
                close_stage="blocked",
                blocker=EpicCloseBlocker(
                    code="review_publication_failed",
                    message="Retry after restoring forge access or resolving the publication error.",
                    retryable=True,
                ),
            )

    # A merged review already put the epic on the product trunk upstream.  The
    # operator checkout can be dirty or behind that merge; updating it here
    # would overwrite unrelated work.  Persist the terminal document in its
    # owning integration worktree and keep that worktree until the operator
    # checkout itself contains the completed document.
    if review is not None:
        remote_doc = _merged_epic_review_landed(epic_id, review, repo)
        if remote_doc is None:
            latest = epic_review_snapshot(epic_id, root=repo)
            if latest is not None and latest.stage == "blocked":
                return _epic_review_result(latest)
            return EpicCompleteResult(
                ok=False,
                reason="pending_epic_review",
                review_url=review.url,
                close_stage="implementation_review_pending",
                source_branch=review.source_branch,
                target_branch=review.target_branch,
                forge_state="open",
            )
        trunk = locate_trunk(repo)
        if remote_doc.meta.status == "completed":
            from cascade.workspace.integration_worktree import get_integration_worktree

            entry = get_integration_worktree(trunk, "epic", epic_id)
            if entry is None:
                return EpicCompleteResult(ok=False, reason="checkout_missing")
            move_doc(epic_id, "completed", root=entry.path)
            verified = epic_review_snapshot(epic_id, root=repo)
            if verified is None or not verified.verified_closure:
                return EpicCompleteResult(ok=False, reason="verification_pending")
            persist_epic_review_snapshot(
                epic_id, _completed_epic_snapshot(verified), root=repo
            )
            _emit_epic_completed(epic_id, repo)
            return EpicCompleteResult(
                ok=True, close_stage="completed", forge_state="merged"
            )
        return EpicCompleteResult(
            ok=False,
            reason="pending_epic_review",
            review_url=review.url,
            close_stage="implementation_review_pending",
            source_branch=review.source_branch,
            target_branch=review.target_branch,
            forge_state="open",
        )

    promote_result = promote_epic_to_trunk(epic_id, root=repo)
    if not promote_result.ok:
        if promote_result.reason == "branch_missing" and _skip_epic_promote(
            epic_doc, repo=repo
        ):
            pass
        else:
            return EpicCompleteResult(
                ok=False,
                reason=promote_result.reason or "promote_failed",
                conflict_paths=promote_result.conflict_paths,
            )
    trunk = locate_trunk(repo)
    move_doc(epic_id, "completed", root=repo)
    _complete_epic_trunk_pointer(epic_id, trunk=trunk)
    _emit_epic_completed(epic_id, repo)
    _retire_epic_worktree(epic_id, repo)
    return EpicCompleteResult(ok=True, close_stage="completed")


def _epic_review_result(snapshot: EpicReviewSnapshot) -> EpicCompleteResult:
    """Return the canonical persisted review state from a repeated Close."""

    return EpicCompleteResult(
        ok=False,
        reason="pending_epic_review"
        if snapshot.stage != "blocked"
        else "review_failed",
        review_url=snapshot.review_url,
        close_stage=snapshot.stage,
        source_branch=snapshot.source_branch,
        target_branch=snapshot.target_branch,
        forge_state=snapshot.forge_state,
        blocker=snapshot.blocker,
    )


def _merged_epic_review_landed(epic_id: WorkId, review, repo: Path):
    """Return the reviewed remote doc only after CI, board and sync verification."""

    import subprocess

    from cascade.board.store import read_doc_in_worktree
    from cascade.review import merge_request_snapshot
    from cascade.workspace.branch_synchronization import synchronize_operator_trunk
    from cascade.workspace.closeout import create_verified_trunk_workspace
    from cascade.workspace.integration_worktree import (
        get_integration_worktree,
        locate_trunk,
    )
    from cascade.workspace.trunk import resolve_product_trunk

    trunk = locate_trunk(repo)
    target = resolve_product_trunk(trunk)
    if review.source_branch != f"epic/{epic_id}" or review.target_branch != target:
        return None
    observed_review = epic_review_snapshot(epic_id, root=repo)
    if (
        observed_review is None
        or observed_review.review_url != review.url
        or observed_review.source_branch != review.source_branch
        or observed_review.target_branch != review.target_branch
    ):
        return None
    try:
        workspace = create_verified_trunk_workspace(trunk, target=target)
    except GitError:
        return None
    with workspace:
        checkout = workspace.path
        try:
            snapshot = merge_request_snapshot(checkout, review)
            if snapshot.get("state") != "merged":
                return None
        except GitError:
            _persist_epic_verification_blocker(
                epic_id,
                repo,
                "forge_evidence_unavailable",
                "Retry the exact forge observation.",
                expected=observed_review,
            )
            return None
        merge_sha = snapshot.get("merge_sha")
        accepted = snapshot.get("accepted_merge_identity")
        post_merge = snapshot.get("post_merge_ci")
        if (
            not isinstance(merge_sha, str)
            or len(merge_sha) != 40
            or not isinstance(accepted, dict)
            or accepted.get("available") is not True
            or accepted.get("merge_sha") != merge_sha
            or not isinstance(post_merge, dict)
            or post_merge.get("state") != "green"
            or post_merge.get("merge_sha") != merge_sha
            or post_merge.get("observed_target_sha") != workspace.revision
            or accepted.get("observed_target_head") != workspace.revision
            or observed_review.observation_identity is None
            or observed_review.accepted_merge_sha != merge_sha
            or observed_review.observed_target_sha != workspace.revision
            or observed_review.post_merge_ci != post_merge
            or snapshot.get("url") != observed_review.review_url
            or snapshot.get("source_branch") != observed_review.source_branch
            or snapshot.get("target_branch") != observed_review.target_branch
        ):
            post_state = (
                str(post_merge.get("state") or "unknown")
                if isinstance(post_merge, dict)
                else "unknown"
            )
            reason = (
                str(post_merge.get("reason") or post_merge.get("state") or "unknown")
                if isinstance(post_merge, dict)
                else "unavailable"
            )
            _persist_epic_verification_blocker(
                epic_id,
                repo,
                "post_merge_ci_red"
                if post_state == "red"
                else "post_merge_ci_not_green",
                (
                    "Authorize a supported corrective scope on the current target."
                    if post_state == "red"
                    else f"Wait for fresh green checks on the accepted merge SHA ({reason})."
                ),
                snapshot=snapshot,
                owner=f"epic:{epic_id}",
                prerequisite=(
                    "authorize_supported_corrective_scope_on_current_target"
                    if post_state == "red"
                    else "retry_exact_merge_ci_observation"
                ),
                expected=observed_review,
            )
            return None
        landed = subprocess.run(
            ["git", "merge-base", "--is-ancestor", merge_sha, workspace.revision],
            cwd=checkout,
            capture_output=True,
            text=True,
        )
        if landed.returncode != 0:
            return None
        accepted_parent = subprocess.run(
            ["git", "rev-parse", "--verify", f"{merge_sha}^1"],
            cwd=checkout,
            capture_output=True,
            text=True,
        )
        if accepted_parent.returncode != 0:
            return None
        source_revision = snapshot.get("source_revision")
        if not isinstance(source_revision, str) or len(source_revision) != 40:
            return None
        try:
            board_fingerprint = workspace.verify_history(
                source_revision=source_revision,
                accepted_revision=accepted_parent.stdout.strip(),
            )
        except GitError:
            _persist_epic_verification_blocker(
                epic_id,
                repo,
                "physical_board_unavailable",
                "Repair and re-prove the current remote physical board.",
                snapshot=snapshot,
                owner="operator",
                prerequisite="repair_and_reprove_current_physical_board",
                expected=observed_review,
            )
            return None
        sync = synchronize_operator_trunk(root=trunk, target=target)
        if (
            not sync.ok
            or sync.remote_sha != workspace.revision
            or not sync.board_fingerprint
        ):
            _persist_epic_verification_blocker(
                epic_id,
                repo,
                f"trunk_sync_{sync.reason or 'unavailable'}",
                sync.prerequisite or "Reconcile the operator trunk and retry.",
                snapshot=snapshot,
                board_fingerprint=board_fingerprint,
                sync=sync,
                owner=sync.owner,
                prerequisite=sync.prerequisite,
                expected=observed_review,
            )
            return None
        try:
            workspace.refresh_target()
        except GitError:
            _persist_epic_verification_blocker(
                epic_id,
                repo,
                "target_moved",
                "Observe and verify the new target generation.",
                snapshot=snapshot,
                owner="operator",
                prerequisite="observe_and_verify_new_target_generation",
                expected=observed_review,
            )
            return None
        entry = get_integration_worktree(trunk, "epic", epic_id)
        if entry is None or not entry.path.is_dir():
            return None
        try:
            source_doc = read_doc_in_worktree(epic_id, entry.path)
            source_path = source_doc.meta.path.relative_to(entry.path).as_posix()
            remote_doc = read_doc_in_worktree(epic_id, checkout)
        except (NotFound, ValueError):
            return None
        if remote_doc.meta.status == "completed":
            accepted = (
                remote_doc.meta.path.parent.name == "3_completed"
                and remote_doc.meta.title == source_doc.meta.title
                and remote_doc.meta.children == source_doc.meta.children
                and remote_doc.body == source_doc.body
            )
            if not accepted:
                return None
            if not _persist_verified_epic_closure(
                epic_id,
                repo,
                snapshot,
                board_fingerprint,
                sync,
                expected=observed_review,
            ):
                return None
            return remote_doc
        if (
            remote_doc.meta.status != "active"
            or remote_doc.meta.path.parent.name != "2_active"
        ):
            return None
        # An ancestry relation alone is insufficient: a merge can resolve the
        # activation pointer by keeping the trunk stub instead of the live spec.
        source_blob = subprocess.run(
            ["git", "rev-parse", f"{review.source_branch}:{source_path}"],
            cwd=checkout,
            capture_output=True,
            text=True,
        )
        target_blob = subprocess.run(
            ["git", "rev-parse", f"{workspace.revision}:{source_path}"],
            cwd=checkout,
            capture_output=True,
            text=True,
        )
        accepted = (
            source_blob.returncode == 0
            and target_blob.returncode == 0
            and source_blob.stdout.strip() == target_blob.stdout.strip()
        )
        if not accepted:
            return None
        if not _persist_verified_epic_closure(
            epic_id,
            repo,
            snapshot,
            board_fingerprint,
            sync,
            expected=observed_review,
        ):
            return None
        return remote_doc


def _sync_receipt(sync) -> dict[str, object]:
    return {
        "ok": sync.ok,
        "target": sync.target,
        "local_sha": sync.local_sha,
        "remote_sha": sync.remote_sha,
        "sync_result": sync.sync_result,
        "board_fingerprint": sync.board_fingerprint,
        "reason": sync.reason,
        "owner": sync.owner,
        "prerequisite": sync.prerequisite,
    }


def _persist_epic_verification_blocker(
    epic_id: WorkId,
    repo: Path,
    code: str,
    message: str,
    *,
    snapshot: dict[str, object] | None = None,
    board_fingerprint: str | None = None,
    sync=None,
    owner: str | None = None,
    prerequisite: str | None = None,
    expected: EpicReviewSnapshot | None = None,
) -> bool:
    """Persist independent failed dimensions without inventing closure."""

    current = epic_review_snapshot(epic_id, root=repo)
    if current is None:
        return False
    accepted = snapshot.get("accepted_merge_identity") if snapshot else None
    accepted = accepted if isinstance(accepted, dict) else {}
    post_merge = snapshot.get("post_merge_ci") if snapshot else None
    post_merge = (
        dict(post_merge)
        if isinstance(post_merge, dict)
        else dict(current.post_merge_ci)
    )
    return persist_epic_review_snapshot(
        epic_id,
        EpicReviewSnapshot(
            stage="blocked",
            review_url=current.review_url,
            source_branch=current.source_branch,
            target_branch=current.target_branch,
            forge_state="merged"
            if snapshot and snapshot.get("state") == "merged"
            else current.forge_state,
            blocker=EpicCloseBlocker(
                code=code,
                message=message,
                retryable=True,
                owner=owner,
                prerequisite=prerequisite,
            ),
            generation=current.generation,
            observation_identity=current.observation_identity,
            accepted_merge_sha=(
                str(accepted.get("merge_sha"))
                if accepted.get("merge_sha")
                else current.accepted_merge_sha
            ),
            observed_target_sha=(
                str(accepted.get("observed_target_head"))
                if accepted.get("observed_target_head")
                else current.observed_target_sha
            ),
            post_merge_ci=post_merge,
            board_fingerprint=board_fingerprint or current.board_fingerprint,
            sync_receipt=_sync_receipt(sync)
            if sync is not None
            else dict(current.sync_receipt),
        ),
        root=repo,
        expected=expected,
    )


def _persist_verified_epic_closure(
    epic_id: WorkId,
    repo: Path,
    snapshot: dict[str, object],
    board_fingerprint: str,
    sync,
    *,
    expected: EpicReviewSnapshot,
) -> bool:
    current = epic_review_snapshot(epic_id, root=repo)
    accepted = snapshot.get("accepted_merge_identity")
    post_merge = snapshot.get("post_merge_ci")
    if (
        current is None
        or not isinstance(accepted, dict)
        or not isinstance(post_merge, dict)
    ):
        return False
    return persist_epic_review_snapshot(
        epic_id,
        EpicReviewSnapshot(
            stage="implementation_review_pending",
            review_url=current.review_url,
            source_branch=current.source_branch,
            target_branch=current.target_branch,
            forge_state="merged",
            generation=current.generation,
            observation_identity=current.observation_identity,
            accepted_merge_sha=str(accepted["merge_sha"]),
            observed_target_sha=str(accepted["observed_target_head"]),
            post_merge_ci=dict(post_merge),
            board_fingerprint=board_fingerprint,
            sync_receipt=_sync_receipt(sync),
            verified_closure=True,
        ),
        root=repo,
        expected=expected,
    )


def _completed_epic_snapshot(current: EpicReviewSnapshot) -> EpicReviewSnapshot:
    """Advance only the already verified generation to terminal closeout."""

    return EpicReviewSnapshot(
        stage="completed",
        review_url=current.review_url,
        source_branch=current.source_branch,
        target_branch=current.target_branch,
        forge_state="merged",
        generation=current.generation,
        observation_identity=current.observation_identity,
        accepted_merge_sha=current.accepted_merge_sha,
        observed_target_sha=current.observed_target_sha,
        post_merge_ci=dict(current.post_merge_ci),
        board_fingerprint=current.board_fingerprint,
        sync_receipt=dict(current.sync_receipt),
        verified_closure=True,
    )


def _completed_on_operator_trunk(epic_id: WorkId, repo: Path) -> bool:
    """Retire the integration worktree only after local trunk owns completion."""

    from cascade.board.store import list_board
    from cascade.workspace.integration_worktree import is_trunk_pointer, locate_trunk

    meta = list_board(locate_trunk(repo)).by_id.get(epic_id)
    return bool(
        meta is not None
        and meta.status == "completed"
        and meta.path.parent.name == "3_completed"
        and not is_trunk_pointer(meta)
    )


def _emit_epic_completed(epic_id: WorkId, repo: Path) -> None:
    if epic_completed_recorded(epic_id, root=repo):
        return
    append_event(
        "war_room",
        Event(
            type="EpicCompleted",
            ts=datetime.now(timezone.utc),
            payload={"epic_id": epic_id},
            dest="war_room",
        ),
        root=repo,
    )


def _retire_epic_worktree(epic_id: WorkId, repo: Path) -> None:
    """Best-effort cleanup after promotion and terminal metadata are durable."""

    from cascade.workspace.integration_worktree import (
        locate_trunk,
        prove_terminal_retirement,
        retire_integration_worktree,
    )

    trunk = locate_trunk(repo)
    proof = prove_terminal_retirement("epic", epic_id, trunk=trunk)
    if not proof.ok:
        _LOG.warning(
            "could not retire completed epic worktree %s: %s; %s",
            epic_id,
            proof.reason,
            proof.next_action,
        )
        return
    try:
        retire_integration_worktree("epic", epic_id, merged_into="HEAD", trunk=trunk)
    except Exception:
        _LOG.exception("could not retire completed epic worktree %s", epic_id)


def on_feature_completed(feature_id: WorkId, *, root: Path | None = None) -> None:
    """After a feature lands in completed, prompt to close the parent epic when all features are done."""

    repo = resolve_root(root)
    try:
        feature = read_doc(feature_id, root=repo)
    except NotFound:
        return
    if feature.meta.tier != "feature":
        return
    epic_id = feature.meta.parent
    if not epic_id:
        return
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    parent = board.by_id.get(epic_id)
    if parent is None or parent.tier != "epic":
        return
    surface_epic_close_prompt(epic_id, root=repo)


def _skip_epic_promote(epic_doc, *, repo: Path) -> bool:
    """True when there is no ``epic/{id}`` integration branch to merge (trunk-only epic)."""

    if epic_doc.meta.integration_branch is not None:
        return False
    from cascade.workspace.integration_worktree import load_registry, locate_trunk

    trunk = locate_trunk(repo)
    for entry in load_registry(trunk):
        if entry.kind == "epic" and entry.work_id == epic_doc.meta.id:
            return False
    return True


def _child_feature_ids(epic_id: WorkId, board) -> set[WorkId]:
    epic = board.by_id[epic_id]
    ids = set(epic.children)
    for meta in board.by_id.values():
        if meta.tier == "feature" and meta.parent == epic_id:
            ids.add(meta.id)
    return ids


def _all_child_features_completed(epic_id: WorkId, board) -> bool:
    incomplete = _incomplete_child_feature_ids(epic_id, board)
    return incomplete == set()


def _child_feature_satisfies_closeout(child: WorkMeta, parent: WorkMeta) -> bool:
    """Accept delivery or an exact, fully reconciled reduced-scope cancellation."""
    if child.path.parent.name != "3_completed":
        return False
    if child.status == "completed":
        return True
    if (
        child.status != "cancelled"
        or child.parent != parent.id
        or child.cancellation_step != "complete"
        or child.cancellation_error is not None
        or child.cancelled_at is None
        or not child.cancellation_reason
    ):
        return False
    feedback = [
        item for item in parent.cancellation_feedback if item.child_id == child.id
    ]
    if len(feedback) != 1:
        return False
    disposition = feedback[0]
    return (
        disposition.child_tier == "feature"
        and disposition.parent_id == parent.id
        and disposition.cancelled_at == child.cancelled_at
        and disposition.reason == child.cancellation_reason
        and disposition.disposition == "continue_reduced_scope"
        and disposition.resolved_at is not None
    )


def _incomplete_child_feature_ids(epic_id: WorkId, board) -> set[WorkId] | None:
    """Return incomplete/missing children, or ``None`` when no features exist."""

    parent = board.by_id[epic_id]
    feature_ids = _child_feature_ids(epic_id, board)
    # An activated brief with no minted features is not delivered work.  In
    # particular, do not let the universal "all children completed" check pass
    # vacuously: startup recovery must only close epics that have actual child
    # completion state to reconcile.
    if not feature_ids:
        return None
    incomplete: set[WorkId] = set()
    for feature_id in feature_ids:
        meta = board.by_id.get(feature_id)
        if meta is None or meta.tier != "feature":
            incomplete.add(feature_id)
            continue
        if not _child_feature_satisfies_closeout(meta, parent):
            incomplete.add(feature_id)
    return incomplete


def _complete_epic_trunk_pointer(epic_id: WorkId, *, trunk: Path) -> None:
    """Move the product-trunk stub for an activated epic into ``3_completed``."""

    from datetime import date

    from cascade.board.gitutil import commit_paths, has_git
    from cascade.board.parse import parse_doc, render_doc
    from cascade.board.paths import column_dir, status_for_column
    from cascade.board.store import list_board
    from cascade.workspace.integration_worktree import is_trunk_pointer

    board = list_board(trunk)
    meta = board.by_id.get(epic_id)
    if meta is None or not is_trunk_pointer(meta):
        return
    if meta.path.parent.name == "3_completed":
        return
    doc = parse_doc(meta.path)
    old_path = meta.path.resolve()
    new_path = (trunk / column_dir("epic", "completed") / old_path.name).resolve()
    doc.meta.status = status_for_column("completed")
    doc.meta.path = new_path
    doc.meta.updated = date.today()
    doc.meta.integration_branch = None
    doc.meta.integration_worktree = None
    new_path.parent.mkdir(parents=True, exist_ok=True)
    new_path.write_text(render_doc(doc), encoding="utf-8")
    if new_path != old_path and old_path.exists():
        old_path.unlink()
    if has_git(trunk):
        paths = [new_path] if new_path == old_path else [old_path, new_path]
        commit_paths(trunk, paths, f"docs: {epic_id} trunk pointer completed")


def _open_human_comment_ids(epic_id: WorkId, repo: Path) -> list[WorkId]:
    ids: list[WorkId] = []
    for row in read_comments(epic_id, root=repo):
        if row.state == "open" and row.author == "human":
            ids.append(row.id)
    return ids
