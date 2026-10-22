"""Dispatch law. Planning graphs do not call move_doc; this module does."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import head_sha
from cascade.board.paths import column_dir
from cascade.board.gitutil import commit_paths, has_git
from cascade.board.store import move_doc, read_doc, save_doc, write_doc
from cascade.board.types import BoardIndex, WorkMeta
from cascade.epic.activation import _drop_stale_copies, activate_epic_on_worktree
from cascade.watchdog.config import task_parallelism
from cascade.watchdog.events import append_event
from cascade.watchdog.hooks import invoke_boot
from cascade.watchdog.lock import process_lock
from cascade.watchdog.skills import SkillPathError, effective_skill_paths, rewrite_skills_section
from cascade.watchdog.types import DispatchResult, Event, Principal
from cascade.workspace.backlog_snapshot import resolve_epic_brief_base_sha
from cascade.workspace.integration_worktree import (
    create_integration_worktree,
    doc_filesystem_root,
    get_integration_worktree,
    integration_branch,
    merged_board,
)

_OPEN = {"backlog", "ready_to_plan"}


def activate_epic(work_id: str, by: Principal, *, root: Path | None = None) -> DispatchResult:
    """Human-only epic activation. Success lands the file in 2_active with status active."""

    repo = resolve_root(root)
    with process_lock:
        result = _activate_epic(work_id, by, repo)
    return _boot_after(result, "epic", work_id, by, repo)


def dispatch_feature(
    work_id: str,
    by: Principal,
    *,
    root: Path | None = None,
) -> DispatchResult:
    """Human or Boss starts feature planning. Success status is active, not ready_to_plan."""

    repo = resolve_root(root)
    with process_lock:
        result = _dispatch_feature(work_id, by, repo)
    return _boot_after(result, "feature", work_id, by, repo)


def dispatch_task(
    work_id: str,
    by: Principal,
    skills: list[Path] | None = None,
    *,
    root: Path | None = None,
) -> DispatchResult:
    """Human or Boss starts a task when dependencies are done and a slot is free.

    A `blocked` task already in `2_active` is the legal restart. `skills is not None`
    replaces the skill list on the same write as the transition to `active`.
    Over cap: the file stays put and no TaskDispatched event is written.
    """

    repo = resolve_root(root)
    with process_lock:
        result = _dispatch_task(work_id, by, skills, repo)
    return _boot_after(result, "task", work_id, by, repo)


def _boot_after(
    result: DispatchResult,
    tier: str,
    work_id: str,
    by: Principal,
    root: Path,
) -> DispatchResult:
    """Boot runs after the process lock is released so a hook can tick without deadlock."""

    if result.ok:
        if tier == "task":
            from cascade.task.execution import mark_queued

            mark_queued(work_id, root=root)
        invoke_boot(tier, work_id)
        from cascade.workspace.kickoff import kickoff_turn
        from cascade.workspace.types import KickoffReason

        kind = "activate" if tier == "epic" else "dispatch"
        kickoff_turn(
            KickoffReason(
                kind=kind,  # type: ignore[arg-type]
                work_id=work_id,
                by=by,  # type: ignore[arg-type]
                root=root,
            )
        )
    return result


def _activate_epic(work_id: str, by: str, root: Path) -> DispatchResult:
    if by != "human":
        return _fail("unauthorized")
    board = merged_board(root)
    meta = board.by_id.get(work_id)
    if meta is None:
        return _fail("not_found")
    if meta.tier != "epic" or meta.status not in _OPEN:
        return _fail("bad_state")
    if not _deps_met(board, meta, root=root):
        return _fail("unmet_deps")
    if not has_git(root):
        move_doc(work_id, "active", root=root)
        event = _emit(root, work_id, "EpicActivated", {"epic_id": work_id, "by": by})
        return DispatchResult(ok=True, reason=None, event=event)
    base_sha = resolve_epic_brief_base_sha(work_id, trunk=root)
    if base_sha is None:
        return _fail("brief_not_on_trunk")
    if head_sha(root) is None:
        return _fail("bad_state")
    branch = integration_branch("epic", work_id)
    epic_wt = create_integration_worktree(
        "epic",
        work_id,
        branch=branch,
        base_ref=base_sha,
        trunk=root,
    )
    activate_epic_on_worktree(work_id, trunk=root, epic_wt=epic_wt)
    event = _emit(root, work_id, "EpicActivated", {"epic_id": work_id, "by": by})
    return DispatchResult(ok=True, reason=None, event=event)


def _dispatch_feature(work_id: str, by: str, root: Path) -> DispatchResult:
    if by not in ("human", "boss"):
        return _fail("unauthorized")
    board = merged_board(root)
    meta = board.by_id.get(work_id)
    if meta is None:
        return _fail("not_found")
    if meta.tier != "feature" or meta.status not in _OPEN:
        return _fail("bad_state")
    if not meta.parent:
        return _fail("bad_state")
    if not _deps_met(board, meta, root=root):
        return _fail("unmet_deps")
    from cascade.approvals import feature_approved

    if not feature_approved(work_id, root=root):
        return _fail("not_approved")
    if _epic_has_feature_awaiting_merge(meta.parent, root=root):
        return _fail("feature_awaiting_merge")
    from cascade.comments.gate import refusal_if_blocked

    if blocked := refusal_if_blocked(work_id, root=root):
        return _fail(blocked)

    if not has_git(root):
        move_doc(work_id, "active", root=root)
        event = _emit(
            root,
            work_id,
            "FeatureReadyToPlan",
            {"id": work_id, "feature_id": work_id, "by": by},
        )
        return DispatchResult(ok=True, reason=None, event=event)

    epic_id = meta.parent
    epic_wt = get_integration_worktree(root, "epic", epic_id)
    if epic_wt is None:
        return _fail("bad_state")
    base_ref = epic_wt.branch
    if head_sha(root) is None:
        return _fail("bad_state")

    feat_branch = integration_branch("feature", work_id)
    feat_wt = create_integration_worktree(
        "feature",
        work_id,
        branch=feat_branch,
        base_ref=base_ref,
        trunk=root,
    )

    _relocate_active(work_id, dest_root=feat_wt.path, trunk=root)

    event = _emit(
        root,
        work_id,
        "FeatureReadyToPlan",
        {"id": work_id, "feature_id": work_id, "by": by},
    )
    return DispatchResult(ok=True, reason=None, event=event)


def _dispatch_task(
    work_id: str,
    by: str,
    skills: list[Path] | None,
    root: Path,
) -> DispatchResult:
    if by not in ("human", "boss"):
        return _fail("unauthorized")
    if isinstance(skills, (str, Path)):
        raise TypeError("skills must be a list of paths or None")
    board = merged_board(root)
    meta = board.by_id.get(work_id)
    if meta is None:
        return _fail("not_found")
    if not _task_can_start(meta):
        return _fail("bad_state")
    if not meta.parent:
        return _fail("bad_state")
    if not _deps_met(board, meta, root=root):
        return _fail("unmet_deps")
    if _active_task_count(board) >= task_parallelism(root):
        return _fail("cap")
    from cascade.comments.gate import refusal_if_blocked

    if blocked := refusal_if_blocked(work_id, root=root):
        return _fail(blocked)

    if not has_git(root):
        move_doc(work_id, "active", root=root)
        event = _emit(
            root,
            work_id,
            "TaskDispatched",
            {
                "id": work_id,
                "task_id": work_id,
                "feature_id": meta.parent,
                "by": by,
                "skills": [],
            },
        )
        return DispatchResult(ok=True, reason=None, event=event)

    feat_id = meta.parent
    feat_wt = get_integration_worktree(root, "feature", feat_id)
    if feat_wt is None:
        return _fail("bad_state")

    chosen = list(meta.skills) if skills is None else [Path(item) for item in skills]
    try:
        skill_paths = effective_skill_paths(root, chosen)
    except SkillPathError:
        return _fail("bad_state")

    # A Feature Team commonly mints several Tasks while it continues editing
    # the Feature plan.  The revision captured at mint time is therefore only
    # a draft pin.  Refresh it immediately before cutting the execution branch
    # so a not-yet-started Task cannot fail merely because a sibling was added
    # or the parent plan was clarified.
    meta = _refresh_task_parent_pin(
        work_id,
        feat_id,
        feature_root=feat_wt.path,
        trunk=root,
    )

    feat_branch = integration_branch("feature", feat_id)
    from cascade.task.worktree import create_task_worktree

    create_task_worktree(
        work_id,
        root=root,
        parent_rev=meta.parent_rev,
        skills=skill_paths,
        base_ref=feat_branch,
    )

    feature_root = feat_wt.path
    _place_task_active(
        feature_root,
        work_id,
        None if skills is None else skill_paths,
        trunk=root,
    )
    event = _emit(
        root,
        work_id,
        "TaskDispatched",
        {
            "id": work_id,
            "task_id": work_id,
            "feature_id": feat_id,
            "by": by,
            "skills": skill_paths,
            "instruction": (
                "Read the Task and pinned Feature plans, implement the scoped change, "
                "run the relevant tests, and leave a deliverable commit on the Task branch. "
                "A finished turn with only board lifecycle changes fails closed."
            ),
        },
    )
    return DispatchResult(ok=True, reason=None, event=event)


def _refresh_task_parent_pin(
    task_id: str,
    feature_id: str,
    *,
    feature_root: Path,
    trunk: Path,
) -> WorkMeta:
    """Commit the live Feature revision onto a Task before its branch is cut."""

    source_root = doc_filesystem_root(task_id, trunk=trunk)
    task = read_doc(task_id, root=source_root)
    feature = read_doc(feature_id, root=feature_root)
    task.meta.parent_rev = feature.sha
    write_doc(task, root=source_root)
    return read_doc(task_id, root=source_root).meta


def _task_can_start(meta: WorkMeta) -> bool:
    """Backlog/ready_to_plan, or a blocked task already sitting in 2_active."""

    if meta.tier != "task" or not meta.parent:
        return False
    if meta.status in _OPEN:
        return True
    return meta.status == "blocked" and meta.path.parent.name == "2_active"


def _place_task_active(
    board_root: Path,
    work_id: str,
    skill_paths: list[str] | None,
    *,
    trunk: Path,
) -> None:
    """One write: status active in 2_active, with a skill override applied only here."""

    source_root = doc_filesystem_root(work_id, trunk=trunk)
    doc = read_doc(work_id, root=source_root)
    previous = doc.meta.path.resolve()
    if skill_paths is not None:
        doc.meta.skills = [Path(item) for item in skill_paths]
        doc.body = rewrite_skills_section(doc.body, skill_paths)
    doc.meta.status = "active"
    doc.meta.path = (board_root / column_dir("task", "active") / previous.name).resolve()
    if source_root.resolve() == board_root.resolve():
        save_doc(doc, previous_path=previous, root=board_root)
        return
    write_doc(doc, root=board_root)
    _drop_stale_copies(
        work_id,
        tier=doc.meta.tier,
        keep=doc.meta.path,
        board_root=board_root,
    )
    if previous.exists() and previous != doc.meta.path.resolve():
        previous.unlink()
        if has_git(source_root):
            commit_paths(source_root, [previous], f"docs: relocate {work_id}")


def _deps_met(board: BoardIndex, meta: WorkMeta, *, root: Path) -> bool:
    for dep_id in meta.depends_on:
        dep = board.by_id.get(dep_id)
        if dep is None or dep.status != "completed" or dep.path.parent.name != "3_completed":
            return False
        if dep.tier == "feature":
            from cascade.review import feature_review_pending

            if feature_review_pending(dep_id, root=root):
                return False
    return True


def _epic_has_feature_awaiting_merge(epic_id: str, *, root: Path) -> bool:
    from cascade.review import epic_has_pending_feature_review

    return epic_has_pending_feature_review(epic_id, root=root)


def _active_task_count(board: BoardIndex) -> int:
    count = 0
    for meta in board.by_id.values():
        if meta.tier == "task" and meta.status == "active" and meta.path.parent.name == "2_active":
            count += 1
    return count


def _emit(root: Path, dest: str, event_type: str, payload: dict[str, object]) -> Event:
    event = Event(
        type=event_type,
        ts=datetime.now(timezone.utc),
        payload=payload,
        dest=dest,
    )
    append_event(dest, event, root=root)
    return event


def _fail(reason: str) -> DispatchResult:
    return DispatchResult(ok=False, reason=reason, event=None)


def _relocate_active(work_id: str, *, dest_root: Path, trunk: Path) -> None:
    """Move a work doc into ``dest_root`` ``2_active`` and drop the prior copy."""

    source_root = doc_filesystem_root(work_id, trunk=trunk)
    doc = read_doc(work_id, root=source_root)
    old_path = doc.meta.path.resolve()
    tier = doc.meta.tier
    doc.meta.status = "active"
    doc.meta.path = (dest_root / column_dir(tier, "active") / old_path.name).resolve()
    write_doc(doc, root=dest_root)
    _drop_stale_copies(
        work_id,
        tier=doc.meta.tier,
        keep=doc.meta.path,
        board_root=dest_root,
    )
    if old_path.exists() and old_path != doc.meta.path.resolve():
        old_path.unlink()
        if has_git(source_root) and source_root.resolve() != dest_root.resolve():
            commit_paths(source_root, [old_path], f"docs: relocate {work_id}")
