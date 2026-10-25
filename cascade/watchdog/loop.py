"""Poll the board and revert work that reached 2_active without a fresh dispatch."""

from __future__ import annotations

import time
import traceback
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import BoardError, GitError
from cascade.board.gitutil import head_sha, introduced_at
from cascade.board.parse import parse_doc
from cascade.board.paths import filename_work_id
from cascade.board.store import move_doc
from cascade.board.types import WorkMeta
from cascade.boss.graph import install_boss_consumer, tick_boss_consumer
from cascade.boss.orphans import OrphanRecord, detect_orphans
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event

# Appearances already toasted. This suppresses duplicate toasts, not retries.
_stuck: set[tuple[str, int, int]] = set()
_orphan_toast_signatures: dict[Path, frozenset[tuple[str, str]]] = {}
# Work queues are the latency-sensitive watchdog input. Remember their cheap
# filesystem signature so idle polls do not rebuild the merged board merely to
# discover that no graph has anything new to ingest.
_work_queue_signatures: dict[Path, tuple[tuple[str, int, int, int, int], ...]] = {}
# Event is written just after the introducing commit; allow a little clock skew.
_AUTH_SKEW = timedelta(seconds=2)
# Filesystem/lifecycle reconciliation is not latency-sensitive; explicit queue
# traffic still uses the 500ms loop below. This also aligns with the advisory
# flight cache TTL, avoiding an extra all-worktree rebuild between refreshes.
_MAINTENANCE_INTERVAL_SECONDS = 10.0


def clear_watchdog_memory() -> None:
    """Forget toast suppression. Tests call this so cases do not leak."""

    from cascade.workspace.convergence import clear_convergence_diagnostic_memory
    from cascade.workspace.turn_progress import clear_turn_progress_memory
    from cascade.workspace.flight import clear_flight_memory
    from cascade.workspace.queue_observability import clear_queue_observability_memory
    from cascade.watchdog.health import clear_health_memory

    with process_lock:
        _stuck.clear()
        _orphan_toast_signatures.clear()
        _work_queue_signatures.clear()
        clear_flight_memory()
        clear_health_memory()
    clear_queue_observability_memory()
    clear_convergence_diagnostic_memory()
    clear_turn_progress_memory()


def watchdog_tick(root: Path | None = None) -> None:
    """Scan `2_active` once. Unauthorized docs are moved back to backlog and toasted."""

    repo = resolve_root(root)
    from cascade.automation import maybe_sync_briefs

    maybe_sync_briefs(repo)
    # Authorization is the first lifecycle gate after importing remote board
    # state.  Later consumers can dispatch descendants or apply other durable
    # lifecycle transitions based on active status, so they must never observe
    # an illegal filesystem move as authorized work.
    with process_lock:
        _tick_scan_active(repo)
    _consume_explicit_events(repo, force_work_queues=True)
    with process_lock:
        _maybe_enqueue_orphan_toasts(repo)
    from cascade.automation import advance_work, poll_reviews
    from cascade.workspace.kickoff import deferred_kickoffs

    with deferred_kickoffs():
        advance_work(repo)
    poll_reviews(repo)
    with process_lock:
        from cascade.workspace.flight import refresh_flight_report_if_stale

        refresh_flight_report_if_stale(repo)
    from cascade.watchdog.events import prune_completed_work_queues
    from cascade.workspace.queue_observability import scan_graph_queue_stalls

    prune_completed_work_queues(root=repo)
    scan_graph_queue_stalls(repo)
    from cascade.workspace.convergence import publish_convergence_diagnostics

    publish_convergence_diagnostics(root=repo)
    from cascade.workspace.in_flight_turn_watchdog import maintain_in_flight_turn_progress

    maintain_in_flight_turn_progress(repo)
    from cascade.watchdog.health import maybe_sweep_supervisor_health

    maybe_sweep_supervisor_health(repo)


def _event_tick(root: Path) -> None:
    """Consume explicit orders without running broad board maintenance."""

    _consume_explicit_events(root, force_work_queues=False)


def _consume_explicit_events(root: Path, *, force_work_queues: bool) -> None:
    """Consume boss and graph queues, skipping unchanged graph queues when idle."""

    install_boss_consumer(root)
    with process_lock:
        tick_boss_consumer()

    from cascade.workspace.kickoff import (
        deferred_kickoffs,
        deliver_queue_kickoffs,
        retry_failed_queue_kickoffs,
    )

    with deferred_kickoffs():
        retry_failed_queue_kickoffs(root)

    signature = _work_queue_signature(root)
    previous = _work_queue_signatures.get(root.resolve())
    if not force_work_queues and signature == previous:
        return

    # Model turns can take minutes. Enqueue them so this supervisory loop keeps
    # scanning health, retrying merges, and dispatching independent work.
    with deferred_kickoffs():
        deliver_queue_kickoffs(root)
    # A failed delivery must remain retryable on the next fast poll.
    _work_queue_signatures[root.resolve()] = signature


def _work_queue_signature(root: Path) -> tuple[tuple[str, int, int, int, int], ...]:
    """Return a cheap change token for graph queues (not UI or boss feeds)."""

    queue_dir = root / "docs" / "_queue"
    if not queue_dir.is_dir():
        return ()
    rows: list[tuple[str, int, int, int, int]] = []
    for path in queue_dir.glob("*.jsonl"):
        if path.stem in {"boss", "war_room"}:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append((path.name, stat.st_dev, stat.st_ino, stat.st_mtime_ns, stat.st_size))
    return tuple(sorted(rows))


def _resume_reclaimable_task_runs(repo: Path) -> None:
    """Resume active Tasks whose durable execution lease has gone stale."""

    from cascade.task.wiring import restore_active_task_runs
    from cascade.workspace.kickoff import deferred_kickoffs, kickoff_graph_queue_event

    restored_tasks = restore_active_task_runs(repo)
    if not restored_tasks:
        return
    with deferred_kickoffs():
        for task_id, feature_id in restored_tasks:
            append_event(
                task_id,
                Event(
                    type="TaskResumeRequested",
                    ts=datetime.now(timezone.utc),
                    payload={
                        "task_id": task_id,
                        "feature_id": feature_id,
                        "instruction": (
                            "Resume the Task by reading its plan and pinned Feature plan, "
                            "then implement, test, and commit the deliverable. Do not report "
                            "completion without a non-lifecycle commit."
                        ),
                    },
                    dest=task_id,
                ),
                root=repo,
            )
            kickoff_graph_queue_event(task_id, root=repo, by="watchdog")


def run_watchdog(
    *,
    root: Path | None = None,
    poll_interval: float = 0.5,
    stop_when: Callable[[], bool] | None = None,
) -> None:
    """Loop `watchdog_tick` until `stop_when` is true. Default poll is 0.5s.

    With no stop condition this function does not return.
    """

    repo = resolve_root(root)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.task.boot import install_task_boot_hook
    from cascade.task.wiring import install_task_wiring

    install_epic_boot_hook(repo)
    install_feature_boot_hook(repo)
    install_task_boot_hook(repo)
    install_task_wiring(repo)
    install_boss_consumer(repo)
    from cascade.workspace.kickoff import install_kickoff

    install_kickoff(repo)
    _resume_reclaimable_task_runs(repo)
    from cascade.automation import reconcile_approval_dispatch
    from cascade.workspace.kickoff import deferred_kickoffs

    # Start work already authorized by durable approval before completion
    # reconciliation, which may need slow remote review I/O. Completion still
    # runs on startup even when automation is disabled.
    with deferred_kickoffs():
        reconcile_approval_dispatch(repo)
    from cascade.completion_reconcile import reconcile_completion_with_prompts
    from cascade.workspace.supervisor_readiness import (
        record_loop_error,
        record_loop_started,
        record_loop_success,
    )

    record_loop_started("reconciliation")
    try:
        reconcile_completion_with_prompts(root=repo)
    except Exception as exc:
        record_loop_error(
            "reconciliation",
            code=type(exc).__name__,
            message=str(exc) or type(exc).__name__,
        )
        raise
    else:
        record_loop_success("reconciliation")
    with deferred_kickoffs():
        reconcile_approval_dispatch(repo)

    last_maintenance_at: float | None = None

    while True:
        if stop_when is not None and stop_when():
            return
        # A fresh lease fences duplicate recovery.  Once its heartbeat ages out,
        # this creates one process-local TaskRun; subsequent ticks see that run
        # and cannot enqueue another resume.
        maintenance_due = (
            last_maintenance_at is None
            or time.monotonic() - last_maintenance_at >= _MAINTENANCE_INTERVAL_SECONDS
        )
        try:
            if maintenance_due:
                _resume_reclaimable_task_runs(repo)
                record_loop_started("watchdog")
                watchdog_tick(root)
                record_loop_success("watchdog")
                last_maintenance_at = time.monotonic()
            else:
                _event_tick(repo)
        except Exception as exc:
            # The War Room and watchdog intentionally share one supervisor.
            # A transient forge/git failure must not tear down the HTTP server;
            # keep the loop alive and leave a full traceback in supervisor.log.
            record_loop_error(
                "watchdog",
                code=type(exc).__name__,
                message=str(exc) or type(exc).__name__,
            )
            traceback.print_exc()
        if stop_when is not None and stop_when():
            return
        time.sleep(poll_interval)


def _tick_scan_active(root: Path) -> None:
    still: set[tuple[str, int, int]] = set()
    for path in _active_markdown(root):
        try:
            _consider(root, path, still)
        except Exception:
            # A single bad file must not kill the tick or run_watchdog.
            continue
    _stuck.clear()
    _stuck.update(still)


def _consider(root: Path, path: Path, still: set[tuple[str, int, int]]) -> None:
    try:
        key = _appearance(path)
    except OSError:
        return
    try:
        doc = parse_doc(path)
    except Exception:
        renamed = _raw_rename_to_backlog(path)
        if key not in _stuck:
            work_id = filename_work_id(path) or path.stem
            _toast(root, work_id, f"{work_id} in 2_active is not a valid work doc")
        if not renamed:
            still.add(key)
        return
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(root)
    canonical = board.by_id.get(doc.meta.id)
    if canonical is None or canonical.path.resolve() != path.resolve():
        return
    try:
        authorized = _authorized(root, doc.meta)
    except Exception:
        authorized = False
    if authorized:
        return
    reverted = _try_revert(root, doc.meta.id)
    if key not in _stuck:
        _toast(
            root,
            doc.meta.id,
            f"{doc.meta.id} appeared in 2_active without dispatch authorization",
        )
    if not reverted and path.exists() and path.parent.name == "2_active":
        try:
            still.add(_appearance(path))
        except OSError:
            still.add(key)


def _active_markdown(root: Path) -> list[Path]:
    from cascade.workspace.integration_worktree import scan_active_markdown_roots

    found: list[Path] = []
    for scan_root in scan_active_markdown_roots(root):
        for dirname in ("epics", "features", "tasks"):
            folder = scan_root / "docs" / dirname / "2_active"
            if not folder.is_dir():
                continue
            found.extend(sorted(path for path in folder.glob("*.md") if path.is_file()))
    return found


def _appearance(path: Path) -> tuple[str, int, int]:
    stat = path.stat()
    return (str(path.resolve()), stat.st_mtime_ns, stat.st_size)


def _authorized(root: Path, meta: WorkMeta) -> bool:
    """The work id's own queue authorizes, and only if it covers this path introduction."""

    newest = _newest_authorizing_event(root, meta)
    if newest is None:
        return False
    from cascade.workspace.integration_worktree import git_root_for_path

    try:
        doc_root = git_root_for_path(meta.path)
        rel = meta.path.resolve().relative_to(doc_root.resolve())
    except (ValueError, GitError):
        return True
    if head_sha(doc_root) is None:
        return True
    introduced = introduced_at(doc_root, rel)
    latest = newest.ts.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    if introduced is None:
        return now - latest <= _AUTH_SKEW
    intro = introduced.astimezone(timezone.utc)
    if now - latest > _AUTH_SKEW and intro > latest + _AUTH_SKEW:
        return False
    if intro <= latest + _AUTH_SKEW:
        return True
    return intro - latest <= timedelta(minutes=1)


def _newest_authorizing_event(root: Path, meta: WorkMeta) -> Event | None:
    events, _offset = read_events(meta.id, 0, root=root)
    matches = [event for event in events if _event_authorizes(meta, event)]
    if not matches:
        return None
    return max(matches, key=lambda event: event.ts)


def _event_authorizes(meta: WorkMeta, event: Event) -> bool:
    payload = event.payload
    if meta.tier == "epic":
        return event.type == "EpicActivated" and payload.get("epic_id") == meta.id
    if meta.tier == "feature":
        if event.type != "FeatureReadyToPlan":
            return False
        return payload.get("id") == meta.id or payload.get("feature_id") == meta.id
    if meta.tier == "task":
        # TaskFailed is not a dispatch and does not authorize a file in 2_active.
        if event.type != "TaskDispatched":
            return False
        return payload.get("id") == meta.id or payload.get("task_id") == meta.id
    return False


def _try_revert(root: Path, work_id: str) -> bool:
    try:
        move_doc(work_id, "backlog", root=root)
    except BoardError:
        return False
    return True


def _raw_rename_to_backlog(path: Path) -> bool:
    """Move an unparseable file to 1_backlog without validating or committing."""

    try:
        dest_dir = path.parent.parent / "1_backlog"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / path.name
        if dest.exists():
            return False
        path.rename(dest)
        return not path.exists()
    except OSError:
        return False


def _orphan_signature(records: list[OrphanRecord]) -> frozenset[tuple[str, str]]:
    return frozenset((record.kind, record.work_id) for record in records)


def _maybe_enqueue_orphan_toasts(root: Path) -> None:
    repo = root.resolve()
    try:
        records = detect_orphans(root=repo)
    except Exception:
        # Unparseable board files must not abort the tick (see _consider).
        return
    if not records:
        _orphan_toast_signatures.pop(repo, None)
        return
    signature = _orphan_signature(records)
    if signature == _orphan_toast_signatures.get(repo):
        return
    for record in records:
        event = Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload=dict(record.toast_payload),
            dest="war_room",
        )
        try:
            append_event("war_room", event, root=repo)
        except OSError:
            return
    _orphan_toast_signatures[repo] = signature


def _toast(root: Path, work_id: str, message: str) -> None:
    event = Event(
        type="Toast",
        ts=datetime.now(timezone.utc),
        payload={
            "kind": "illegal_move",
            "id": work_id,
            "message": message,
            "reason": "unauthorized",
        },
        dest="war_room",
    )
    try:
        append_event("war_room", event, root=root)
    except OSError:
        return
