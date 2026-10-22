"""Dependency-aware, no-click progression between human approval boundaries."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.paths import column_for_status
from cascade.boss.view import compute_boss_view
from cascade.watchdog.config import read_automation_config
from cascade.watchdog.dispatch import dispatch_feature, dispatch_task
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import merged_board
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.errors import WorkspaceError

_last_remote_poll: dict[str, float] = {}
_last_review_poll: dict[str, float] = {}


def reset_automation_memory() -> None:
    _last_remote_poll.clear()
    _last_review_poll.clear()


def sync_briefs(root: Path, *, force: bool = False) -> dict[str, object]:
    """Refresh remote backlog briefs and report newly visible epic ids."""

    repo = Path(root).resolve()
    cfg = read_automation_config(repo)
    now = time.monotonic()
    key = str(repo)
    if not force and now - _last_remote_poll.get(key, 0.0) < cfg.poll_seconds:
        return {"ok": True, "skipped": True, "new_briefs": []}
    before = {
        meta.id for meta in merged_board(repo).by_id.values()
        if meta.tier == "epic" and column_for_status(meta.status) == "backlog"
    }
    trunk_branch = resolve_product_trunk(repo)
    if cfg.enabled:
        from cascade.workspace.backlog_snapshot import refresh_remote_backlog_snapshot

        refresh = refresh_remote_backlog_snapshot(
            repo,
            remote=cfg.remote,
            trunk_branch=trunk_branch,
        )
        sha = refresh.sha
        payload_extras: dict[str, object] = {
            "unchanged": refresh.unchanged,
            "omitted_ids": list(refresh.omitted_ids),
            "diagnostics": list(refresh.diagnostics),
        }
    else:
        from cascade.tracking import fast_forward_trunk

        sha = fast_forward_trunk(repo, trunk_branch, remote=cfg.remote)
        payload_extras = {}
    _last_remote_poll[key] = now
    after = {
        meta.id for meta in merged_board(repo).by_id.values()
        if meta.tier == "epic" and column_for_status(meta.status) == "backlog"
    }
    added = sorted(after - before)
    for epic_id in added:
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload={
                    "kind": "brief_imported",
                    "id": epic_id,
                    "message": f"New brief {epic_id} is ready to activate",
                },
                dest="war_room",
            ),
            root=repo,
        )
    return {
        "ok": True,
        "skipped": False,
        "sha": sha,
        "new_briefs": added,
        **payload_extras,
    }


def maybe_sync_briefs(root: Path) -> None:
    cfg = read_automation_config(root)
    if not cfg.enabled:
        return
    try:
        sync_briefs(root)
    except (GitError, OSError, WorkspaceError):
        # Dirty/offline workspaces remain usable. The force-pull endpoint exposes
        # the concrete error when the operator wants to resolve it.
        return


def poll_reviews(root: Path) -> None:
    cfg = read_automation_config(root)
    if not cfg.enabled:
        return
    key = str(Path(root).resolve())
    now = time.monotonic()
    if now - _last_review_poll.get(key, 0.0) < cfg.poll_seconds:
        return
    _last_review_poll[key] = now
    try:
        from cascade.review import poll_feature_reviews

        poll_feature_reviews(root)
        from cascade.completion_reconcile import reconcile_completion_with_prompts

        reconcile_completion_with_prompts(root=root)
    except (GitError, OSError, WorkspaceError):
        return


def advance_work(root: Path) -> dict[str, list[str]]:
    """Start eligible feature plans and tasks in dependency order.

    One feature per epic is planned at a time so the Epic Team can incorporate
    each result holistically. Tasks use the configured parallelism cap.
    """

    repo = Path(root).resolve()
    cfg = read_automation_config(repo)
    if not cfg.enabled:
        return {"features": [], "tasks": []}
    from cascade.task_rollup import retry_pending_task_merges

    retry_pending_task_merges(repo)
    from cascade.completion_reconcile import reconcile_completion_with_prompts

    reconcile_completion_with_prompts(root=repo)
    return reconcile_approval_dispatch(repo)


def reconcile_approval_dispatch(root: Path) -> dict[str, list[str]]:
    """Re-evaluate durable approval and dependency gates through canonical dispatch.

    Restart-safe: already-dispatched work is skipped by dispatch law; idempotent
    approval timestamps are not rewritten.
    """

    repo = Path(root).resolve()
    cfg = read_automation_config(repo)
    result: dict[str, list[str]] = {"features": [], "tasks": []}
    if not cfg.enabled:
        return result

    from cascade.approvals import feature_approved
    from cascade.review import feature_review_pending

    board = merged_board(repo)
    view = compute_boss_view(root=repo)
    active_feature_parents = {
        meta.parent
        for meta in board.by_id.values()
        if meta.tier == "feature" and meta.path.parent.name == "2_active"
    }
    active_feature_parents.update(
        meta.parent
        for meta in board.by_id.values()
        if meta.tier == "feature"
        and meta.parent
        and feature_review_pending(meta.id, root=repo)
    )
    for feature_id in view.dispatchable_features:
        meta = board.by_id.get(feature_id)
        if meta is None or meta.parent in active_feature_parents:
            continue
        parent = board.by_id.get(meta.parent or "")
        if parent is None or parent.path.parent.name != "2_active":
            continue
        if not feature_approved(feature_id, root=repo):
            continue
        dispatched = dispatch_feature(feature_id, "boss", root=repo)
        if dispatched.ok:
            result["features"].append(feature_id)
            active_feature_parents.add(meta.parent)
            if meta.parent:
                append_event(
                    meta.parent,
                    Event(
                        type="FeaturePlanningStarted",
                        ts=datetime.now(timezone.utc),
                        payload={
                            "feature_id": feature_id,
                            "epic_id": meta.parent,
                            "instruction": "Provide holistic constraints or sequencing input to the Feature Team through the shared plan artifacts and amendment protocol.",
                        },
                        dest=meta.parent,
                    ),
                    root=repo,
                )

    # Recompute after feature activation because its integration worktree may
    # change the merged board and expose task specs.
    view = compute_boss_view(root=repo)
    for task_id in _stale_parent_failures(view.failed_tasks, board=merged_board(repo), root=repo):
        dispatched = dispatch_task(task_id, "boss", root=repo)
        if dispatched.ok:
            result["tasks"].append(task_id)
        elif dispatched.reason == "cap":
            break

    view = compute_boss_view(root=repo)
    for task_id in view.dispatchable_tasks:
        dispatched = dispatch_task(task_id, "boss", root=repo)
        if dispatched.ok:
            result["tasks"].append(task_id)
        elif dispatched.reason == "cap":
            break
    return result


def _stale_parent_failures(
    failed_tasks: list[str], *, board, root: Path
) -> list[str]:
    """Return failed children whose latest lifecycle event is stale-parent boot.

    This recovery is deterministic: no SWE work ran before the revision guard
    failed.  Other task failures remain with the Feature Team for diagnosis so
    the supervisor cannot loop an unchanged implementation indefinitely.
    """

    recoverable: list[str] = []
    for task_id in failed_tasks:
        meta = board.by_id.get(task_id)
        if meta is None or not meta.parent:
            continue
        events, _ = read_events(meta.parent, 0, root=root)
        latest: str | None = None
        for event in events:
            if event.payload.get("task_id") != task_id:
                continue
            if event.type == "TaskActivated":
                latest = "activated"
            elif event.type == "TaskFailed":
                latest = str(event.payload.get("reason") or "")
        if latest == "stale_parent_rev":
            recoverable.append(task_id)
    return recoverable
