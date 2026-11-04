"""Bounded, repository-backed preflight for an admitted review rebase.

This boundary deliberately stops before rebasing, editing, testing, or pushing.
It converts a durable ``mutation_ready`` action into a small execution contract
only after the live remote and durable review record still agree.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from cascade.resolution_actions import resolution_action
from cascade.workspace.integration_worktree import locate_trunk


_ALLOWED_OPERATIONS = (
    "rebase_owned_source",
    "edit_conflicted_owned_paths",
    "run_repository_checks",
    "push_source_with_force_with_lease",
)

# This is intentionally a concrete repository command rather than caller input:
# the execution turn must not turn an admitted rebase capability into arbitrary
# shell execution.  It is also the narrowest regression suite for this boundary.
_REPOSITORY_CHECK_COMMAND = (
    sys.executable,
    "-m",
    "pytest",
    "tests/test_review_rebase.py",
)


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

    check_result = subprocess.run(
        _REPOSITORY_CHECK_COMMAND, cwd=worktree, capture_output=True,
        text=True, encoding="utf-8",
    )
    check = ReviewRebaseCheck(
        _REPOSITORY_CHECK_COMMAND, check_result.returncode,
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
            f"HEAD:refs/heads/{turn.source_ref}",
        ],
        cwd=worktree, capture_output=True, text=True, encoding="utf-8",
    )
    if push.returncode:
        output = f"{push.stdout}\n{push.stderr}".lower()
        code = "force_with_lease_failed" if "stale info" in output or "rejected" in output else "publication_failed"
        return _publication_blocked("publication", code, "The lease-protected source publication failed; local rebased work was preserved.", worktree, checks=(check,), observed_remote_source_sha=source_remote_sha)
    return ReviewRebasePublication(True, execution.source_head, source_remote_sha, (check,))


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
            return record.get("push_credentials_available", record.get("credentials_available")) is True
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
