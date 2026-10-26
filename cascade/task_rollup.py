"""Durable retry queue for automatic task-to-feature merges."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.gitutil import _run
from cascade.board.store import read_doc
from cascade.task.action_recovery import ActionResult, create_or_load_action, resume_action
from cascade.task.execution import mark_merge_blocked
from cascade.watchdog.events import append_event
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event


_QUEUED_MERGE_KIND = "queued_task_merge"
# The legacy queue retried indefinitely.  Keep recovery durable without making a
# short-lived transient refusal terminal during normal supervisor operation.
_QUEUED_MERGE_ATTEMPT_BOUND = 100


def _path(root: Path) -> Path:
    return root / ".cascade" / "pending-task-merges.json"


def _read(root: Path) -> list[str]:
    path = _path(root)
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [str(item) for item in raw if isinstance(item, str)] if isinstance(raw, list) else []


def _write(root: Path, task_ids: list[str]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(sorted(set(task_ids)), indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def _queued_merge_action_id(task_id: str) -> str:
    """Return the stable recovery identity for one legacy queue entry."""

    return f"{task_id}:queued_merge"


def _queued_merge_action(task_id: str, root: Path) -> dict:
    return create_or_load_action(
        _queued_merge_action_id(task_id),
        _QUEUED_MERGE_KIND,
        root=root,
        attempt_bound=_QUEUED_MERGE_ATTEMPT_BOUND,
        metadata={"task_id": task_id},
    )


def queue_task_merge(task_id: str, *, root: Path) -> None:
    repo = resolve_root(root)
    # Queue creation establishes the action identity.  Existing queue files
    # remain a plain list for compatibility with current callers.
    _queued_merge_action(task_id, repo)
    with process_lock:
        pending = _read(repo)
        if task_id not in pending:
            pending.append(task_id)
            _write(repo, pending)


def pending_task_merges(root: Path) -> set[str]:
    repo = resolve_root(root)
    with process_lock:
        return set(_read(repo))


def retry_pending_task_merges(root: Path) -> list[str]:
    """Retry durable task merges and return ids completed on this pass."""

    repo = resolve_root(root)
    completed: list[str] = []
    removable: list[str] = []
    with process_lock:
        pending = _read(repo)
    for task_id in pending:
        action = _queued_merge_action(task_id, repo)
        state = action.get("recovery_state")
        # A supervisor can be interrupted after recording success but before it
        # prunes the legacy queue.  Removing that entry must not replay merge
        # or rollup.
        if state == "completed":
            removable.append(task_id)
            continue
        if state in {"awaiting_owner_decision", "awaiting_human_gate", "blocked", "running"}:
            if state == "blocked":
                removable.append(task_id)
            continue

        action = resume_action(
            _queued_merge_action_id(task_id),
            root=repo,
            execute=lambda _context, task_id=task_id: _resume_queued_merge(task_id, repo),
        )
        if action.get("recovery_state") == "completed":
            completed.append(task_id)
            removable.append(task_id)
        elif action.get("recovery_state") == "blocked":
            removable.append(task_id)
    if removable:
        with process_lock:
            latest = _read(repo)
            removed = set(removable)
            _write(repo, [task_id for task_id in latest if task_id not in removed])
    return completed


def _resume_queued_merge(task_id: str, root: Path) -> ActionResult:
    """Execute the existing merge boundary once and classify its result."""

    from cascade.boss.merge import merge_task_branch

    result = merge_task_branch(task_id, root=root)
    metadata = _merge_outcome_metadata(task_id, result, root)
    if result.ok or _already_completed_equivalent(task_id, root):
        if result.ok:
            from cascade.boss.rollup import on_task_merged

            try:
                on_task_merged(task_id, root=root)
            except Exception:
                # The merge is durable; closeout scanning can recover an
                # independent rollup failure without replaying the merge.
                pass
        metadata["already_completed"] = not result.ok
        return ActionResult(metadata=metadata)

    reason = result.reason or "merge_refused"
    if reason == "branch_conflict":
        _record_merge_refusal(task_id, result, root)
        # Task 004 assigns the owner and records resolution.  Preserve evidence
        # and deliberately leave this action in its semantic decision state.
        return ActionResult("failed", "owner_decision", metadata)
    if reason in {
        "busy", "checkout_missing", "merge_target_missing", "wrong_branch", "post_merge_failed",
    }:
        if reason != "busy":
            _record_merge_refusal(task_id, result, root)
        classification = "transient_retry" if reason == "busy" else "deterministic_repair"
        return ActionResult("failed", classification, metadata)
    if reason not in {"task_not_found", "wrong_column", "not_mergeable"}:
        _record_merge_refusal(task_id, result, root)
    return ActionResult("failed", "terminal_blocker", metadata)


def _merge_outcome_metadata(task_id: str, result, root: Path) -> dict:
    heads = _merge_head_pair(task_id, root)
    source_sha, target_sha = heads if heads is not None else (None, None)
    return {
        "task_id": task_id,
        "reason": result.reason,
        "branch": result.branch,
        "target_branch": result.target_branch,
        "merge_sha": result.merge_sha,
        "conflict_paths": list(result.conflict_paths),
        "source_sha": source_sha,
        "target_sha": target_sha,
    }


def _already_completed_equivalent(task_id: str, root: Path) -> bool:
    """Recognize a merge committed by an interrupted earlier supervisor."""

    try:
        return read_doc(task_id, root=root).meta.status == "completed"
    except NotFound:
        return False


def _merge_head_pair(task_id: str, root: Path) -> tuple[str, str] | None:
    """The source and target refs that determine a task merge conflict."""

    try:
        task = read_doc(task_id, root=root)
    except NotFound:
        return None
    if task.meta.status != "active" or not task.meta.parent:
        return None
    refs = (f"refs/heads/task/{task_id}", f"refs/heads/feat/{task.meta.parent}")
    heads: list[str] = []
    for ref in refs:
        result = _run(["rev-parse", "--verify", ref], root, check=False)
        if result.returncode != 0:
            return None
        heads.append(result.stdout.strip())
    return heads[0], heads[1]


def _record_merge_refusal(task_id: str, result, root: Path) -> None:
    heads = _merge_head_pair(task_id, root)
    source_sha, target_sha = heads if heads is not None else (None, None)
    reason = result.reason or "merge_refused"
    paths = tuple(result.conflict_paths)
    if not mark_merge_blocked(
        task_id,
        root=root,
        reason=reason,
        conflict_paths=paths,
        source_sha=source_sha,
        target_sha=target_sha,
    ):
        return
    detail = f" Conflicting files: {', '.join(paths)}." if paths else ""
    recovery = (
        "Resolve the Task branch against its Feature branch, then retry Merge task."
        if reason == "branch_conflict"
        else "Check the merge refusal, then retry Merge task."
    )
    message = f"Task {task_id} could not merge ({reason}).{detail} {recovery}"
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "task_merge_blocked",
                "id": task_id,
                "reason": reason,
                "conflict_paths": list(paths),
                "message": message,
            },
            dest="war_room",
        ),
        root=root,
    )
