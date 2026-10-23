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
from cascade.board.errors import NotFound
from cascade.board.paths import column_for_status
from cascade.board.store import move_doc, read_doc
from cascade.board.types import WorkId
from cascade.comments.store import read_comments
from cascade.watchdog.events import append_event, read_events
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
    if key in _surfaced_prompts:
        return
    _surfaced_prompts.add(key)
    message = f"Epic {epic_id} is ready to close"
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
