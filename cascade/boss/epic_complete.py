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
from cascade.board.paths import column_for_status
from cascade.board.store import move_doc, read_doc
from cascade.board.types import WorkId
from cascade.comments.store import read_comments
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


def reset_epic_close_prompt_surfaces() -> None:
    """Clear in-process ``surface_epic_close_prompt`` deduplication (tests only)."""

    _surfaced_prompts.clear()


def epic_ready_to_close(epic_id: WorkId, *, root: Path | None = None) -> bool:
    """True when every child feature is completed and the epic has no open human comments."""

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

    return _finish_epic_completion(epic_id, root=root)


def confirm_epic_complete(epic_id: WorkId, by: Principal, *, root: Path | None = None) -> bool:
    """Human-only: move the epic to completed and emit ``EpicCompleted`` on ``war_room``."""

    return confirm_epic_complete_result(epic_id, by, root=root).ok


def confirm_epic_complete_result(
    epic_id: WorkId, by: Principal, *, root: Path | None = None
) -> EpicCompleteResult:
    """Complete an epic and retain the refusal reason for API callers."""

    if by != "human":
        return EpicCompleteResult(ok=False, reason="unauthorized")
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
        _emit_epic_completed(epic_id, repo)
        if _completed_on_operator_trunk(epic_id, repo):
            _retire_epic_worktree(epic_id, repo)
        return EpicCompleteResult(ok=True)
    blocker = _epic_close_blocker(epic_id, repo=repo, board=board)
    if blocker is not None:
        return blocker
    try:
        epic_doc = read_doc(epic_id, root=repo)
    except NotFound:
        return EpicCompleteResult(ok=False, reason="not_found")
    from cascade.boss.merge import promote_epic_to_trunk
    from cascade.review import ensure_epic_review

    try:
        review = ensure_epic_review(epic_id, root=repo)
    except GitError:
        _LOG.exception("could not open epic review for %s", epic_id)
        return EpicCompleteResult(ok=False, reason="review_failed")

    # A merged review already put the epic on the product trunk upstream.  The
    # operator checkout can be dirty or behind that merge; updating it here
    # would overwrite unrelated work.  Persist the terminal document in its
    # owning integration worktree and keep that worktree until the operator
    # checkout itself contains the completed document.
    if review is not None and _merged_epic_review_landed(epic_id, review, repo):
        trunk = locate_trunk(repo)
        remote_doc = _remote_epic_doc(epic_id, trunk=trunk, target=review.target_branch)
        if remote_doc is not None and remote_doc.meta.status == "completed":
            from cascade.workspace.integration_worktree import get_integration_worktree

            entry = get_integration_worktree(trunk, "epic", epic_id)
            if entry is None:
                return EpicCompleteResult(ok=False, reason="checkout_missing")
            move_doc(epic_id, "completed", root=entry.path)
            _emit_epic_completed(epic_id, repo)
            return EpicCompleteResult(ok=True)
        from cascade.boss.epic_close_review import ensure_epic_close_review

        try:
            close_review = ensure_epic_close_review(
                epic_id, trunk=trunk, target=review.target_branch
            )
        except GitError:
            _LOG.exception("could not open epic closeout review for %s", epic_id)
            return EpicCompleteResult(ok=False, reason="review_failed")
        return EpicCompleteResult(
            ok=False, reason="pending_close_review", review_url=close_review.url
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
    return EpicCompleteResult(ok=True)


def _merged_epic_review_landed(epic_id: WorkId, review, repo: Path) -> bool:
    """Require both forge merge state and the reviewed tip on remote trunk."""

    import subprocess

    from cascade.board.store import read_doc_in_worktree
    from cascade.review import merge_request_snapshot
    from cascade.workspace.integration_worktree import get_integration_worktree, locate_trunk
    from cascade.workspace.trunk import resolve_product_trunk

    trunk = locate_trunk(repo)
    target = resolve_product_trunk(trunk)
    if review.source_branch != f"epic/{epic_id}" or review.target_branch != target:
        return False
    try:
        snapshot = merge_request_snapshot(trunk, review)
        if snapshot.get("state") != "merged":
            return False
    except GitError:
        return False
    merge_sha = snapshot.get("merge_sha")
    if not isinstance(merge_sha, str) or len(merge_sha) != 40:
        return False
    remote_ref = f"refs/remotes/origin/{target}"
    fetched = subprocess.run(
        ["git", "fetch", "--no-tags", "origin", f"refs/heads/{target}:{remote_ref}"],
        cwd=trunk, capture_output=True, text=True,
    )
    if fetched.returncode != 0:
        return False
    landed = subprocess.run(
        ["git", "merge-base", "--is-ancestor", merge_sha, remote_ref],
        cwd=trunk, capture_output=True, text=True,
    )
    if landed.returncode != 0:
        return False
    entry = get_integration_worktree(trunk, "epic", epic_id)
    if entry is None or not entry.path.is_dir():
        return False
    try:
        source_doc = read_doc_in_worktree(epic_id, entry.path)
        source_path = source_doc.meta.path.relative_to(entry.path).as_posix()
    except (NotFound, ValueError):
        return False
    remote_doc = _remote_epic_doc(epic_id, trunk=trunk, target=target)
    if remote_doc is None:
        return False
    if remote_doc.meta.status == "completed":
        return (
            remote_doc.meta.path.parent.name == "3_completed"
            and remote_doc.meta.title == source_doc.meta.title
            and remote_doc.meta.children == source_doc.meta.children
            and remote_doc.body == source_doc.body
        )
    if remote_doc.meta.status != "active" or remote_doc.meta.path.parent.name != "2_active":
        return False
    # An ancestry relation alone is insufficient: a merge can resolve the
    # activation pointer by keeping the trunk stub instead of the live spec.
    source_blob = subprocess.run(
        ["git", "rev-parse", f"{review.source_branch}:{source_path}"],
        cwd=trunk, capture_output=True, text=True,
    )
    target_blob = subprocess.run(
        ["git", "rev-parse", f"{remote_ref}:{source_path}"],
        cwd=trunk, capture_output=True, text=True,
    )
    return (
        source_blob.returncode == 0
        and target_blob.returncode == 0
        and source_blob.stdout.strip() == target_blob.stdout.strip()
    )


def _remote_epic_doc(epic_id: WorkId, *, trunk: Path, target: str):
    """Read the approved epic doc from the fetched remote trunk tree."""

    from cascade.board.errors import SchemaError
    from cascade.board.gitutil import path_for_work_id, read_blob
    from cascade.board.parse import parse_text

    remote_ref = f"refs/remotes/origin/{target}"
    try:
        rel = path_for_work_id(trunk, remote_ref, epic_id)
        if rel is None:
            return None
        doc = parse_text(read_blob(trunk, remote_ref, rel), trunk / rel)
    except (GitError, SchemaError):
        return None
    return doc if doc.meta.tier == "epic" and doc.meta.id == epic_id else None


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
        retire_integration_worktree,
    )

    try:
        retire_integration_worktree(
            "epic", epic_id, merged_into="HEAD", trunk=locate_trunk(repo)
        )
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


def _incomplete_child_feature_ids(epic_id: WorkId, board) -> set[WorkId] | None:
    """Return incomplete/missing children, or ``None`` when no features exist."""

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
        if (
            meta.status != "completed"
            or column_for_status(meta.status) != "completed"
            or meta.path.parent.name != "3_completed"
        ):
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
