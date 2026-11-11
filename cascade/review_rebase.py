"""Bounded, repository-backed preflight for an admitted review rebase.

This boundary deliberately stops before rebasing, editing, testing, or pushing.
It converts a durable ``mutation_ready`` action into a small execution contract
only after the live remote and durable review record still agree.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cascade.resolution_actions import resolution_action
from cascade.task.action_recovery import (
    ActionFailure,
    ActionReconciliation,
    create_or_load_action,
    load_action,
    reconcile_action,
    record_action_checkpoint,
    record_owner_decision,
    resume_action,
)
from cascade.workspace.integration_worktree import locate_trunk


_ALLOWED_OPERATIONS = (
    "rebase_owned_source",
    "edit_conflicted_owned_paths",
    "run_repository_checks",
    "push_source_with_force_with_lease",
)

from cascade.review_validation import review_validation_command as validation_command
from cascade.review_validation import review_validation_timeout, run_review_validation, validate_publication_board


@dataclass(frozen=True)
class WorktreeSnapshot:
    """Read-only evidence captured before the preflight fetch."""

    head: str
    branch: str
    dirty_paths: tuple[str, ...]
    remote_shas: tuple[str | None, str | None]


@dataclass(frozen=True)
class ReviewRebaseTurn:
    """The only capabilities supplied to the subsequent rebase turn."""

    action_id: str
    review_id: str
    worktree: Path
    remote: str
    source_ref: str
    target_ref: str
    observed_source_sha: str
    observed_target_sha: str
    initial_state: WorktreeSnapshot
    fetched_remote_shas: tuple[str, str]
    allowed_operations: tuple[str, ...] = _ALLOWED_OPERATIONS
    push_credentials_available: bool = True


@dataclass(frozen=True)
class ReviewRebaseBlocker:
    """Fail-closed evidence; no cleanup or reset is performed for a blocker."""

    checkpoint: str
    code: str
    message: str
    affected_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReviewRebasePreflight:
    """Exactly one bounded turn or blocker."""

    turn: ReviewRebaseTurn | None = None
    blocker: ReviewRebaseBlocker | None = None

    def __post_init__(self) -> None:
        if (self.turn is None) == (self.blocker is None):
            raise ValueError("preflight must contain exactly one turn or blocker")


@dataclass(frozen=True)
class ReviewRebaseExecution:
    """Evidence from the bounded rebase stage, before checks or publication.

    A blocked execution intentionally leaves a Git rebase in progress.  The
    caller can hand that state to the existing recovery lifecycle; this module
    must never guess a product-level merge resolution or discard user work.
    """

    rebased: bool
    source_head: str | None = None
    modified_paths: tuple[str, ...] = ()
    conflicted_paths: tuple[str, ...] = ()
    blocker: ReviewRebaseBlocker | None = None

    def __post_init__(self) -> None:
        if self.rebased == (self.blocker is not None):
            raise ValueError("execution must contain exactly one success or blocker")


@dataclass(frozen=True)
class ReviewRebaseCheck:
    """Captured result of one repository-defined verification command."""

    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


@dataclass(frozen=True)
class ReviewRebasePublication:
    """Evidence for the checks-and-publication stage of an owned rebase."""

    published: bool
    source_head: str | None = None
    observed_remote_source_sha: str | None = None
    checks: tuple[ReviewRebaseCheck, ...] = ()
    blocker: ReviewRebaseBlocker | None = None

    def __post_init__(self) -> None:
        if self.published == (self.blocker is not None):
            raise ValueError("publication must contain exactly one success or blocker")


@dataclass(frozen=True)
class ReviewRebaseRecovery:
    """The normalized result of executing or recovering one admitted rebase."""

    action_id: str
    outcome: str
    reconciliation: ActionReconciliation | None = None
    execution: ReviewRebaseExecution | None = None
    publication: ReviewRebasePublication | None = None
    blocker: ReviewRebaseBlocker | None = None


def execute_review_rebase(
    turn: ReviewRebaseTurn, *, authorized_paths: tuple[str, ...] | list[str]
) -> ReviewRebaseExecution:
    """Rebase only the admitted source and stop safely at any conflict.

    ``authorized_paths`` is deliberately required at this mutation boundary:
    the preceding generic review admission does not infer file ownership.  A
    conflict is never auto-resolved, even when its path is authorized, because
    choosing either side is a semantic/product decision.  The rebase remains
    in progress so no potentially useful work is discarded.
    """

    worktree = turn.worktree
    authorized = _normalized_authorized_paths(authorized_paths)
    if authorized is None:
        return _execution_blocked(
            "path_authorization", "authorized_paths_invalid",
            "The owned path authorization is missing or invalid.", worktree,
        )
    if not worktree.is_dir():
        return _execution_blocked("worktree", "worktree_unavailable", "The authorized worktree is unavailable.", worktree)
    if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") != turn.source_ref:
        return _execution_blocked("source_checkout", "source_not_checked_out", "The admitted source branch is not checked out; no rebase was attempted.", worktree)
    if _git(worktree, "rev-parse", "--verify", "HEAD^{commit}") != turn.observed_source_sha:
        return _execution_blocked("source_head", "source_head_changed", "The checked-out source head no longer matches the admitted source head.", worktree)
    if _git(worktree, "rev-parse", "--verify", f"refs/remotes/{turn.remote}/{turn.target_ref}^{{commit}}") != turn.observed_target_sha:
        return _execution_blocked("target_head", "target_head_changed", "The fetched target head no longer matches the admitted target head.", worktree)
    if _dirty_paths(worktree):
        return _execution_blocked("worktree_clean", "dirty_unrelated_paths", "The authorized worktree changed after preflight; it was left untouched.", worktree)

    result = subprocess.run(
        ["git", "rebase", f"refs/remotes/{turn.remote}/{turn.target_ref}"],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        conflicts = _conflicted_paths(worktree)
        if conflicts:
            unauthorized = tuple(path for path in conflicts if path not in authorized)
            if unauthorized:
                return _execution_blocked("conflict_paths", "conflict_path_not_authorized", "A rebase conflict touches paths outside the admitted ownership bounds; the conflict state was preserved.", *(worktree / path for path in unauthorized), conflicts=conflicts)
            return _execution_blocked("conflict_resolution", "semantic_conflict_requires_decision", "An authorized rebase conflict requires a product or semantic decision; the conflict state was preserved.", *(worktree / path for path in conflicts), conflicts=conflicts)
        detail = (result.stderr or result.stdout).strip()
        message = "Git could not complete the rebase; the worktree was preserved."
        if detail:
            message = f"{message} Git reported: {detail}"
        return _execution_blocked("rebase", "rebase_failed", message, worktree)

    # Compare against the admitted target, not the former source: the latter
    # would also report every target-side change newly present in ``HEAD``.
    modified = _git_paths(worktree, "diff", "--name-only", f"{turn.observed_target_sha}..HEAD")
    unexpected = tuple(path for path in modified if path not in authorized)
    if unexpected:
        return _execution_blocked("mutation_bounds", "modified_path_not_authorized", "The completed rebase modified paths outside the admitted ownership bounds; local work was preserved.", *(worktree / path for path in unexpected), modified=modified)
    return ReviewRebaseExecution(True, _git(worktree, "rev-parse", "--verify", "HEAD^{commit}"), modified)


def check_and_publish_review_rebase(
    turn: ReviewRebaseTurn, execution: ReviewRebaseExecution
) -> ReviewRebasePublication:
    """Run the bounded regression check and lease-protect source publication.

    This function deliberately accepts only the successful result of the prior
    rebase stage.  It revalidates the durable admission and both remote heads
    after checks, immediately before pushing.  A failed invariant leaves the
    rebased checkout intact for the existing recovery lifecycle.
    """

    if not execution.rebased or not execution.source_head:
        return _publication_blocked(
            "rebase", "rebase_not_complete",
            "The source was not successfully rebased; checks and publication were not attempted.",
        )
    worktree = turn.worktree
    if not worktree.is_dir():
        return _publication_blocked("worktree", "worktree_unavailable", "The authorized worktree is unavailable.", worktree)
    if _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") != turn.source_ref:
        return _publication_blocked("source_checkout", "source_not_checked_out", "The admitted source branch is no longer checked out; publication was not attempted.", worktree)
    if _git(worktree, "rev-parse", "--verify", "HEAD^{commit}") != execution.source_head:
        return _publication_blocked("source_head", "source_head_changed", "The rebased source head changed before checks; publication was not attempted.", worktree)
    if _dirty_paths(worktree):
        return _publication_blocked("worktree_clean", "dirty_unrelated_paths", "The authorized worktree has uncommitted paths; they were left untouched.", worktree)

    # A conflict-free Git tree can still contain duplicate lifecycle documents.
    # Reject it before spawning checks or publishing any remote mutation.
    from cascade.board.errors import SchemaError
    try:
        validate_publication_board(worktree)
    except (SchemaError, OSError, ValueError) as exc:
        return _publication_blocked(
            "board", "board_validation_failed",
            f"Resolved checkout has invalid lifecycle documents ({type(exc).__name__}); repair the board before publication.", worktree,
        )
    try:
        command = validation_command(locate_trunk(worktree))
        timeout = review_validation_timeout(locate_trunk(worktree))
        check_result = run_review_validation(command, cwd=worktree, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return _publication_blocked(
            "checks", "repository_checks_timed_out",
            f"Repository checks exceeded {timeout:g} seconds; validation processes were stopped and the checkout preserved.", worktree,
            checks=(ReviewRebaseCheck(command, 124, str(exc.output or ""), str(exc.stderr or "")),),
        )
    except (OSError, ValueError) as exc:
        return _publication_blocked(
            "checks", "repository_checks_unavailable",
            f"Repository checks could not run ({type(exc).__name__}); no publication attempted.", worktree,
        )
    check = ReviewRebaseCheck(
        command, check_result.returncode,
        check_result.stdout, check_result.stderr,
    )
    if check.returncode:
        return _publication_blocked(
            "checks", "repository_checks_failed",
            "The repository-defined review-rebase checks failed; publication was not attempted.",
            worktree, checks=(check,),
        )
    if _dirty_paths(worktree):
        return _publication_blocked(
            "worktree_clean", "dirty_paths_after_checks",
            "Repository checks changed the authorized worktree; publication was not attempted.",
            worktree, checks=(check,),
        )

    if (validation_command(locate_trunk(worktree)) != command
            or review_validation_timeout(locate_trunk(worktree)) != timeout):
        return _publication_blocked(
            "checks", "validation_policy_changed",
            "The repository validation policy changed during checks; run the new policy before publication.",
            worktree, checks=(check,),
        )
    if _git(worktree, "rev-parse", "--verify", "HEAD^{commit}") != execution.source_head:
        return _publication_blocked(
            "source_head", "source_head_changed",
            "The source head changed during checks; the new head must be validated before publication.",
            worktree, checks=(check,),
        )

    # A network read after checks is required: the remote-tracking ref from
    # preflight may be stale, and the lease needs the exact remote source SHA.
    source_remote_sha = _remote_head(worktree, turn.remote, turn.source_ref)
    if source_remote_sha is None:
        return _publication_blocked("remote_source", "source_remote_unavailable", "Could not re-read the remote source head before publication.", worktree, checks=(check,))
    target_remote_sha = _remote_head(worktree, turn.remote, turn.target_ref)
    if target_remote_sha is None:
        return _publication_blocked("remote_target", "target_remote_unavailable", "Could not re-read the remote target head before publication.", worktree, checks=(check,))
    if source_remote_sha != turn.observed_source_sha:
        return _publication_blocked("remote_source", "source_remote_changed", "The remote source head changed after admission; publication was not attempted.", worktree, checks=(check,), observed_remote_source_sha=source_remote_sha)
    if target_remote_sha != turn.observed_target_sha:
        return _publication_blocked("remote_target", "target_remote_changed", "The remote target head changed after admission; publication was not attempted.", worktree, checks=(check,), observed_remote_source_sha=source_remote_sha)

    trunk = locate_trunk(worktree.resolve())
    expected_authorization = (worktree.resolve(), turn.source_ref, turn.target_ref, (turn.observed_source_sha, turn.observed_target_sha))
    if _authorized_action(turn.action_id, trunk=trunk) != expected_authorization:
        return _publication_blocked("authorization", "authorization_changed", "The durable review authorization changed before publication.", trunk / ".cascade" / "reviews.json", checks=(check,), observed_remote_source_sha=source_remote_sha)
    current_action = resolution_action(turn.action_id, root=trunk)
    if (
        not turn.push_credentials_available
        or not isinstance(current_action, Mapping)
        or not _push_credentials_available(trunk, current_action)
    ):
        return _publication_blocked("credentials", "push_credentials_unavailable", "Push credentials are not explicitly available for this review.", checks=(check,), observed_remote_source_sha=source_remote_sha)

    push = subprocess.run(
        [
            "git", "push", turn.remote,
            f"--force-with-lease=refs/heads/{turn.source_ref}:{source_remote_sha}",
            f"{execution.source_head}:refs/heads/{turn.source_ref}",
        ],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if push.returncode:
        output = f"{push.stdout}\n{push.stderr}".lower()
        code = "force_with_lease_failed" if "stale info" in output or "rejected" in output else "publication_failed"
        return _publication_blocked("publication", code, "The lease-protected source publication failed; local rebased work was preserved.", worktree, checks=(check,), observed_remote_source_sha=source_remote_sha)
    return ReviewRebasePublication(True, execution.source_head, source_remote_sha, (check,))


def recover_and_execute_review_rebase(
    action_id: str,
    *,
    root: Path,
    authorized_paths: tuple[str, ...] | list[str],
    reclaim_running: bool = False,
) -> ReviewRebaseRecovery:
    """Run an admitted rebase once, or safely recover the same logical action.

    The resolution-action identity is also the recovery identity.  Consequently
    retries cannot manufacture a second force-push, and a supervisor restart
    can prove a previously-published local rebased head before attempting any
    mutation.  This is intentionally the workflow boundary; callers should not
    compose the three lower-level stages when restart safety is required.
    """

    trunk = locate_trunk(Path(root).resolve())
    existing = load_action(action_id, root=trunk)
    if existing is None:
        preflight = prepare_review_rebase_turn(action_id, root=trunk)
        if preflight.blocker is not None:
            return ReviewRebaseRecovery(action_id, "blocked", blocker=preflight.blocker)
        assert preflight.turn is not None
        turn = preflight.turn
        create_or_load_action(
            action_id, "review_rebase", root=trunk, attempt_bound=3,
            metadata={"review_id": turn.review_id, "source_ref": turn.source_ref, "target_ref": turn.target_ref},
        )
        _record_rebase_checkpoint(
            action_id, "admitted", turn, root=trunk, affected_paths=(),
            command_summary="admitted review rebase; mutation has not started",
            test_summary="not run",
            resume_instructions="Resume the admitted rebase using the same action identity.",
        )
    else:
        turn = _recovery_turn(action_id, trunk)
        if turn is None:
            blocker = ReviewRebaseBlocker(
                "recovery", "recovery_metadata_unavailable",
                "The admitted rebase metadata is unavailable; no retry was attempted.",
            )
            return ReviewRebaseRecovery(action_id, "blocked", blocker=blocker)

        # Reclaiming a process-interrupted attempt must happen before its
        # reconciliation.  A durable ``running`` claim intentionally blocks
        # ordinary callers, but treating it as terminal here would make a
        # restart unable to reach the checkpoint it needs to resume safely.
        if not (existing.get("recovery_state") == "running" and reclaim_running):
            recovered = _reconcile_review_rebase(action_id, turn, root=trunk)
            if recovered.outcome == "already_completed":
                resume_action(
                    action_id, root=trunk, reclaim_running=reclaim_running,
                    execute=lambda _context: {"metadata": {"result": "already_completed"}},
                )
                return ReviewRebaseRecovery(action_id, "completed", reconciliation=recovered)
            if recovered.outcome == "blocker":
                return ReviewRebaseRecovery(action_id, "blocked", reconciliation=recovered)

    result: dict[str, object] = {}

    def execute(_context: object) -> dict[str, object]:
        # A rebase that was interrupted after it changed HEAD must be resumed
        # from that checkout, not restarted from an assumed clean source.
        recovered = _reconcile_review_rebase(action_id, turn, root=trunk)
        if recovered.outcome == "already_completed":
            result["reconciliation"] = recovered
            return {"metadata": {"result": "already_completed"}}
        if recovered.outcome == "blocker":
            result["reconciliation"] = recovered
            raise ActionFailure("terminal_blocker", recovered.reason, metadata=recovered.as_dict())
        if recovered.reason == "rebase_in_progress":
            blocker = ReviewRebaseBlocker(
                "conflict_resolution", "semantic_conflict_requires_decision",
                "The interrupted rebase remains in progress; resolve the recorded conflict before resuming.",
                _conflicted_paths(turn.worktree),
            )
            _record_blocker(action_id, turn, blocker, blocker.affected_paths, root=trunk)
            record_owner_decision(
                action_id, f"semantic-conflict:{action_id}", root=trunk,
                owner="feature_team",
                metadata={"blocker": blocker.code, "affected_paths": list(blocker.affected_paths)},
            )
            result["execution"] = ReviewRebaseExecution(False, conflicted_paths=blocker.affected_paths, blocker=blocker)
            raise ActionFailure("owner_decision", blocker.message, metadata={"blocker": blocker.code})
        if recovered.reason == "rebased_head_present":
            persisted = load_action(action_id, root=trunk) or {}
            checkpoint = persisted.get("checkpoint")
            paths = tuple(checkpoint.get("affected_paths") or ()) if isinstance(checkpoint, Mapping) else ()
            execution = ReviewRebaseExecution(
                True, _git(turn.worktree, "rev-parse", "--verify", "HEAD^{commit}"), paths,
            )
        else:
            execution = execute_review_rebase(turn, authorized_paths=authorized_paths)
        result["execution"] = execution
        if not execution.rebased:
            assert execution.blocker is not None
            _record_blocker(action_id, turn, execution.blocker, execution.conflicted_paths, root=trunk)
            if execution.blocker.code == "semantic_conflict_requires_decision":
                record_owner_decision(
                    action_id, f"semantic-conflict:{action_id}", root=trunk,
                    owner="feature_team",
                    metadata={"blocker": execution.blocker.code, "affected_paths": list(execution.conflicted_paths)},
                )
                raise ActionFailure("owner_decision", execution.blocker.message, metadata={"blocker": execution.blocker.code})
            raise ActionFailure("terminal_blocker", execution.blocker.message, metadata={"blocker": execution.blocker.code})

        _record_rebase_checkpoint(
            action_id, "rebased", turn, root=trunk, affected_paths=execution.modified_paths,
            command_summary="git rebase completed",
            test_summary="not run",
            resume_instructions="Run the repository checks and publish the rebased source with its recorded lease.",
            rebased_head=execution.source_head,
        )
        publication = check_and_publish_review_rebase(turn, execution)
        result["publication"] = publication
        if not publication.published:
            assert publication.blocker is not None
            _record_blocker(action_id, turn, publication.blocker, (), root=trunk)
            raise ActionFailure("terminal_blocker", publication.blocker.message, metadata={"blocker": publication.blocker.code})
        _record_rebase_checkpoint(
            action_id, "published", turn, root=trunk, affected_paths=execution.modified_paths,
            command_summary="git push --force-with-lease completed",
            test_summary=_checks_summary(publication.checks),
            resume_instructions="The source publication is complete; reconcile this action before emitting any follow-up lifecycle effects.",
            rebased_head=execution.source_head, published_head=publication.source_head,
        )
        return {"metadata": {"published_head": publication.source_head, "review_id": turn.review_id}}

    action = resume_action(action_id, root=trunk, execute=execute, reclaim_running=reclaim_running)
    reconciliation = result.get("reconciliation")
    if isinstance(reconciliation, ActionReconciliation) and reconciliation.outcome == "already_completed":
        return ReviewRebaseRecovery(action_id, "completed", reconciliation=reconciliation)
    execution = result.get("execution")
    publication = result.get("publication")
    if action.get("recovery_state") == "completed":
        return ReviewRebaseRecovery(
            action_id, "completed", execution=execution if isinstance(execution, ReviewRebaseExecution) else None,
            publication=publication if isinstance(publication, ReviewRebasePublication) else None,
        )
    blocker = None
    if isinstance(publication, ReviewRebasePublication):
        blocker = publication.blocker
    elif isinstance(execution, ReviewRebaseExecution):
        blocker = execution.blocker
    return ReviewRebaseRecovery(action_id, "blocked", execution=execution if isinstance(execution, ReviewRebaseExecution) else None, publication=publication if isinstance(publication, ReviewRebasePublication) else None, blocker=blocker)


def _recovery_turn(action_id: str, trunk: Path) -> ReviewRebaseTurn | None:
    """Recreate the bounded turn from durable admission and recovery evidence."""

    action = resolution_action(action_id, root=trunk)
    if not isinstance(action, Mapping):
        return None
    handoff, request = action.get("handoff"), action.get("request")
    if not isinstance(handoff, Mapping) or not isinstance(request, Mapping):
        return None
    parsed = _parse_handoff(action_id, handoff, request)
    if parsed is None:
        return None
    review_id, worktree, source_ref, target_ref, heads = parsed
    if not worktree.is_dir():
        return None
    return ReviewRebaseTurn(
        action_id, review_id, worktree, "origin", source_ref, target_ref,
        heads[0], heads[1],
        WorktreeSnapshot(
            _git(worktree, "rev-parse", "--verify", "HEAD^{commit}") or "",
            _git(worktree, "rev-parse", "--abbrev-ref", "HEAD") or "",
            _dirty_paths(worktree), (None, None),
        ),
        heads,
    )


def _reconcile_review_rebase(
    action_id: str, turn: ReviewRebaseTurn, *, root: Path
) -> ActionReconciliation:
    """Observe both refs before delegating the durable restart choice.

    ``reconcile_action`` owns the target/base comparison.  The source remote
    is additionally required here because it is the externally-visible effect
    of this workflow: after a crash immediately following push, it proves that
    retrying would duplicate publication.
    """

    local_head = _git(turn.worktree, "rev-parse", "--verify", "HEAD^{commit}")
    target_head = _remote_head(turn.worktree, turn.remote, turn.target_ref)
    source_head = _remote_head(turn.worktree, turn.remote, turn.source_ref)
    in_progress = _rebase_in_progress(turn.worktree)
    dirty = _dirty_paths(turn.worktree)
    action = load_action(action_id, root=root) or {}
    checkpoint = action.get("checkpoint") if isinstance(action.get("checkpoint"), Mapping) else {}
    shas = checkpoint.get("shas") if isinstance(checkpoint.get("shas"), Mapping) else {}
    rebased = shas.get("rebased_head")
    if (
        isinstance(rebased, str) and rebased and local_head == rebased
        and source_head == rebased and target_head == turn.observed_target_sha
    ):
        _record_rebase_checkpoint(
            action_id, "published-reconciled", turn, root=root,
            affected_paths=tuple(checkpoint.get("affected_paths") or ()),
            command_summary="remote source already equals the recorded rebased head",
            test_summary=str(checkpoint.get("test_summary") or "unknown"),
            resume_instructions="Publication was reconciled after restart; do not push again.",
            rebased_head=rebased, published_head=rebased,
        )
        # ``reconcile_action`` compares its remote argument with the target
        # head.  Here publication is proved by the *source* remote, so return
        # the completed result directly rather than treating the target head
        # as a published source SHA and attempting another push.
        persisted = load_action(action_id, root=root) or {}
        reconciled_checkpoint = persisted.get("checkpoint")
        reconciled_paths = (
            tuple(reconciled_checkpoint.get("affected_paths") or ())
            if isinstance(reconciled_checkpoint, Mapping)
            else ()
        )
        return ActionReconciliation(
            "already_completed", "published_head_on_remote", action_id,
            reconciled_checkpoint.get("checkpoint_id")
            if isinstance(reconciled_checkpoint, Mapping)
            else None,
            local_head, target_head, reconciled_paths,
            reconciled_checkpoint.get("resume_instructions")
            if isinstance(reconciled_checkpoint, Mapping)
            else None,
        )
    return reconcile_action(
        action_id, root=root, local_head=local_head, remote_head=target_head,
        rebase_in_progress=in_progress, dirty_paths=dirty,
    )


def _record_rebase_checkpoint(
    action_id: str, phase: str, turn: ReviewRebaseTurn, *, root: Path,
    affected_paths: tuple[str, ...], command_summary: str, test_summary: str,
    resume_instructions: str, rebased_head: str | None = None,
    published_head: str | None = None,
) -> None:
    shas = {"source_head": turn.observed_source_sha, "target_head": turn.observed_target_sha}
    if rebased_head:
        shas["rebased_head"] = rebased_head
    if published_head:
        shas["published_head"] = published_head
    suffix = published_head or rebased_head or "initial"
    record_action_checkpoint(
        action_id, f"{phase}:{suffix}", root=root,
        refs={"source": turn.source_ref, "target": turn.target_ref}, shas=shas,
        affected_paths=affected_paths, command_summary=command_summary,
        test_summary=test_summary, resume_instructions=resume_instructions,
    )


def _record_blocker(
    action_id: str, turn: ReviewRebaseTurn, blocker: ReviewRebaseBlocker,
    affected_paths: tuple[str, ...], *, root: Path,
) -> None:
    paths = affected_paths or tuple(Path(path).name for path in blocker.affected_paths)
    _record_rebase_checkpoint(
        action_id, f"blocked-{blocker.code}", turn, root=root, affected_paths=paths,
        command_summary=f"blocked at {blocker.checkpoint}: {blocker.code}",
        test_summary="not completed", resume_instructions=blocker.message,
    )


def _checks_summary(checks: tuple[ReviewRebaseCheck, ...]) -> str:
    return "; ".join(" ".join(check.command) + f" (exit {check.returncode})" for check in checks) or "not run"


def _rebase_in_progress(worktree: Path) -> bool:
    git_dir = _git(worktree, "rev-parse", "--git-dir")
    if not git_dir:
        return False
    path = Path(git_dir)
    if not path.is_absolute():
        path = worktree / path
    return (path / "rebase-merge").exists() or (path / "rebase-apply").exists()


def prepare_review_rebase_turn(action_id: str, *, root: Path) -> ReviewRebasePreflight:
    """Fetch and revalidate an admitted action without changing user work.

    Fetching is intentionally the sole Git state update here.  It updates only
    the two remote-tracking refs needed to prove the review heads; no checkout,
    reset, rebase, index update, or push is attempted on a failure path.
    """

    trunk = locate_trunk(Path(root).resolve())
    action = resolution_action(action_id, root=trunk)
    if not isinstance(action, dict) or action.get("status") != "mutation_ready":
        return _blocked("admission", "action_not_mutation_ready", "The action is not a mutation-ready admission.")
    handoff = action.get("handoff")
    request = action.get("request")
    if not isinstance(handoff, Mapping) or not isinstance(request, Mapping):
        return _blocked("admission", "action_metadata_missing", "The admitted action is missing its bounded handoff metadata.")

    parsed = _parse_handoff(action_id, handoff, request)
    if parsed is None:
        return _blocked("admission", "action_metadata_invalid", "The admitted action has invalid authorization metadata.")
    review_id, worktree, source_ref, target_ref, expected_shas = parsed
    if not worktree.is_dir():
        return _blocked("worktree", "worktree_unavailable", "The authorized worktree is unavailable.", worktree)

    dirty = _dirty_paths(worktree)
    initial = WorktreeSnapshot(
        head=_git(worktree, "rev-parse", "--verify", "HEAD^{commit}") or "",
        branch=_git(worktree, "rev-parse", "--abbrev-ref", "HEAD") or "",
        dirty_paths=dirty,
        remote_shas=(None, None),
    )
    if dirty:
        return _blocked("worktree_clean", "dirty_unrelated_paths", "The authorized worktree has uncommitted user paths; they were left untouched.", *(worktree / path for path in dirty))

    remote = _git(worktree, "remote")
    if not remote or "origin" not in remote.splitlines():
        return _blocked("git_metadata", "remote_missing", "The authorized worktree has no origin remote.", worktree)
    source_remote = f"refs/remotes/origin/{source_ref}"
    target_remote = f"refs/remotes/origin/{target_ref}"
    initial = WorktreeSnapshot(
        head=initial.head,
        branch=initial.branch,
        dirty_paths=initial.dirty_paths,
        remote_shas=(_git(worktree, "rev-parse", "--verify", f"{source_remote}^{{commit}}"), _git(worktree, "rev-parse", "--verify", f"{target_remote}^{{commit}}")),
    )
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"refs/heads/{source_ref}:{source_remote}", f"refs/heads/{target_ref}:{target_remote}"],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if fetched.returncode != 0:
        return _blocked("fetch", "authorized_refs_unavailable", "Could not fetch both authorized review refs.", worktree)

    # Re-read durable authorization after network I/O, then compare exactly the
    # two fetched heads to the immutable admission observation.
    authorization = _authorized_action(action_id, trunk=trunk)
    if authorization != (worktree, source_ref, target_ref, expected_shas):
        return _blocked("authorization", "authorization_changed", "The durable review authorization changed during preflight.", trunk / ".cascade" / "reviews.json")
    fetched_shas = (_git(worktree, "rev-parse", "--verify", f"{source_remote}^{{commit}}"), _git(worktree, "rev-parse", "--verify", f"{target_remote}^{{commit}}"))
    if None in fetched_shas or fetched_shas != expected_shas:
        return _blocked("remote_heads", "remote_heads_changed", "The fetched source or target head no longer matches the admitted review heads.", worktree)
    if not _push_credentials_available(trunk, action):
        return _blocked("credentials", "push_credentials_unavailable", "Push credentials are not explicitly available for this review.", trunk / ".cascade" / "reviews.json")
    return ReviewRebasePreflight(turn=ReviewRebaseTurn(action_id, review_id, worktree, "origin", source_ref, target_ref, expected_shas[0], expected_shas[1], initial, (fetched_shas[0], fetched_shas[1])))


def _parse_handoff(action_id: str, handoff: Mapping[str, object], request: Mapping[str, object]) -> tuple[str, Path, str, str, tuple[str, str]] | None:
    refs, shas = handoff.get("authorized_refs"), handoff.get("observed_shas")
    if handoff.get("action_id") != action_id or not isinstance(refs, list) or not isinstance(shas, list) or len(refs) != 2 or len(shas) != 2:
        return None
    if not all(isinstance(item, str) and item for item in [*refs, *shas]):
        return None
    if request.get("source_ref") != refs[0] or request.get("target_ref") != refs[1]:
        return None
    if request.get("observed_source_head") != shas[0] or request.get("observed_target_head") != shas[1]:
        return None
    worktree = handoff.get("worktree")
    review_id = handoff.get("review_id")
    if not isinstance(worktree, str) or not isinstance(review_id, str):
        return None
    return review_id, Path(worktree).resolve(), refs[0], refs[1], (shas[0], shas[1])


def _authorized_action(action_id: str, *, trunk: Path) -> tuple[Path, str, str, tuple[str, str]] | None:
    action = resolution_action(action_id, root=trunk)
    if not isinstance(action, dict) or action.get("status") != "mutation_ready":
        return None
    handoff, request = action.get("handoff"), action.get("request")
    if not isinstance(handoff, Mapping) or not isinstance(request, Mapping):
        return None
    parsed = _parse_handoff(action_id, handoff, request)
    if parsed is None:
        return None
    _review_id, worktree, source_ref, target_ref, shas = parsed
    records = _review_records(trunk)
    # Registry keys are owner IDs, so find by the handoff's durable review URL/number.
    record = next((item for item in records.values() if str(item.get("url") or item.get("review_url") or "") == request.get("review_url") or str(item.get("number") or "") == str(request.get("review_id"))), None)
    if not isinstance(record, Mapping) or bool(record.get("closed")) or str(record.get("state") or record.get("forge_state") or "open").lower() in {"closed", "merged"}:
        return None
    if (record.get("source_branch"), record.get("target_branch")) != (source_ref, target_ref):
        return None
    return worktree, source_ref, target_ref, shas


def _push_credentials_available(trunk: Path, action: Mapping[str, object]) -> bool:
    request = action.get("request")
    if not isinstance(request, Mapping):
        return False
    for record in _review_records(trunk).values():
        if str(record.get("url") or record.get("review_url") or "") == request.get("review_url") or str(record.get("number") or "") == str(request.get("review_id")):
            # Older Cascade review records predate capability markers. Treat
            # only an explicit denial as unavailable; the exact-head lease and
            # push remain the fail-closed credential check for those records.
            return record.get("push_credentials_available", record.get("credentials_available")) is not False
    return False


def _review_records(trunk: Path) -> dict[str, Mapping[str, object]]:
    try:
        raw = json.loads((trunk / ".cascade" / "reviews.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return {str(key): value for key, value in raw.items() if isinstance(value, Mapping)} if isinstance(raw, dict) else {}


def _dirty_paths(worktree: Path) -> tuple[str, ...]:
    output = _git(worktree, "status", "--porcelain", "--untracked-files=all") or ""
    return tuple(line[3:].split(" -> ")[-1] for line in output.splitlines() if len(line) >= 4 and not line[3:].startswith(".cascade/"))


def _normalized_authorized_paths(paths: tuple[str, ...] | list[str]) -> frozenset[str] | None:
    """Reject empty, absolute, or traversal paths before Git can mutate."""

    if not paths:
        return None
    normalized: set[str] = set()
    for path in paths:
        if not isinstance(path, str) or not path:
            return None
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            return None
        normalized.add(candidate.as_posix())
    return frozenset(normalized)


def _conflicted_paths(worktree: Path) -> tuple[str, ...]:
    return _git_paths(worktree, "diff", "--name-only", "--diff-filter=U")


def _git_paths(worktree: Path, *args: str) -> tuple[str, ...]:
    output = _git(worktree, *args)
    return tuple(path for path in (output or "").splitlines() if path)


def _remote_head(worktree: Path, remote: str, branch: str) -> str | None:
    """Return one advertised branch SHA without updating local refs."""

    result = subprocess.run(
        ["git", "ls-remote", "--exit-code", "--heads", remote, f"refs/heads/{branch}"],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if result.returncode:
        return None
    fields = result.stdout.split()
    return fields[0] if len(fields) >= 2 else None


def _execution_blocked(
    checkpoint: str,
    code: str,
    message: str,
    *paths: Path,
    conflicts: tuple[str, ...] = (),
    modified: tuple[str, ...] = (),
) -> ReviewRebaseExecution:
    return ReviewRebaseExecution(
        rebased=False,
        modified_paths=modified,
        conflicted_paths=conflicts,
        blocker=ReviewRebaseBlocker(checkpoint, code, message, tuple(str(path) for path in paths)),
    )


def _publication_blocked(
    checkpoint: str,
    code: str,
    message: str,
    *paths: Path,
    checks: tuple[ReviewRebaseCheck, ...] = (),
    observed_remote_source_sha: str | None = None,
) -> ReviewRebasePublication:
    return ReviewRebasePublication(
        published=False,
        checks=checks,
        observed_remote_source_sha=observed_remote_source_sha,
        blocker=ReviewRebaseBlocker(checkpoint, code, message, tuple(str(path) for path in paths)),
    )


def _git(worktree: Path, *args: str) -> str | None:
    result = subprocess.run(["git", *args], cwd=worktree, capture_output=True, text=True, encoding="utf-8")
    return result.stdout.strip() if result.returncode == 0 else None


def _blocked(checkpoint: str, code: str, message: str, *paths: Path) -> ReviewRebasePreflight:
    return ReviewRebasePreflight(blocker=ReviewRebaseBlocker(checkpoint, code, message, tuple(str(path) for path in paths)))
