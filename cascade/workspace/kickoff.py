"""Sole path to roster model turns (feat_014 kickoff gates)."""

from __future__ import annotations

import contextvars
import logging
import queue
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from cascade.agent.errors import TurnCancelledForDrain
from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.watchdog.queue_cursor import queue_byte_size, resolve_last_queue_offset
from cascade.workspace.drain import is_draining
from cascade.workspace.types import KickoffReason

_log = logging.getLogger(__name__)

_model_turn_authorized: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_model_turn_authorized",
    default=False,
)
_defer_turns: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "_defer_turns",
    default=False,
)

_default_root: Path | None = None

_COMMENT_KICKOFF_CONTENT_CAP = 2000
_COMMENT_KICKOFF_SIDECAR_NOTE = (
    "\n(Full text in the comment sidecar; use read_doc and thread comments.)"
)
_COMMENT_QUEUE_TYPES = frozenset({"CommentPosted", "CommentReplied", "CommentResolved"})
_graph_locks: dict[str, threading.RLock] = {}
_graph_queues: dict[str, "queue.Queue[Callable[[], None]]"] = {}
_pending_queue_delivery: set[str] = set()
_failed_queue_delivery: dict[tuple[Path, str], tuple[str, str | None, int, float]] = {}
_registry_lock = threading.Lock()


def model_turn_authorized() -> bool:
    """True while ``kickoff_turn`` is executing a roster model invocation."""

    return _model_turn_authorized.get()


def install_kickoff(root: Path) -> None:
    """Remember repo root for kickoff calls that omit ``reason.root``."""

    global _default_root
    _default_root = Path(root).resolve()


def kickoff_turn(reason: KickoffReason) -> None:
    """Run or enqueue one serialized roster model turn for an authorized edge."""

    repo = resolve_root(reason.root or _default_root)
    if _defer_turns.get():
        _submit_background(reason.work_id, lambda: _run_background_kickoff(reason, repo))
        return
    _run_kickoff(reason, repo)


@contextmanager
def deferred_kickoffs() -> Iterator[None]:
    """Queue kickoff turns in the background while an HTTP request is active."""

    token = _defer_turns.set(True)
    try:
        yield
    finally:
        _defer_turns.reset(token)


def clear_kickoff_delivery_state() -> None:
    """Reset per-graph delivery dedupe (tests only)."""

    with _registry_lock:
        _pending_queue_delivery.clear()
        _failed_queue_delivery.clear()


def reset_kickoff_test_state() -> None:
    """Clear deferred-kickoff context leakage between tests."""

    _defer_turns.set(False)
    clear_kickoff_delivery_state()
    with _registry_lock:
        _graph_locks.clear()


def wait_for_background_kickoffs(timeout: float = 30.0) -> bool:
    """Wait until every queued background turn has finished."""

    deadline = time.monotonic() + timeout
    with _registry_lock:
        queues = list(_graph_queues.values())
    for pending in queues:
        while pending.unfinished_tasks:
            if time.monotonic() >= deadline:
                return False
            time.sleep(0.02)
    return True


def _graph_lock(work_id: str) -> threading.RLock:
    with _registry_lock:
        lock = _graph_locks.get(work_id)
        if lock is None:
            lock = threading.RLock()
            _graph_locks[work_id] = lock
        return lock


def _run_kickoff(reason: KickoffReason, repo: Path) -> None:
    with _graph_lock(reason.work_id):
        token = _model_turn_authorized.set(True)
        try:
            _kickoff_turn(reason, repo)
        finally:
            _model_turn_authorized.reset(token)


def _submit_background(work_id: str, job: Callable[[], None]) -> bool:
    if is_draining():
        _log.info(
            "dropping background kickoff job for %s (worker draining)",
            work_id,
        )
        return False
    with _registry_lock:
        pending = _graph_queues.get(work_id)
        if pending is None:
            pending = queue.Queue()
            _graph_queues[work_id] = pending
            threading.Thread(
                target=_drain_background,
                args=(work_id, pending),
                name=f"kickoff-{work_id}",
                daemon=True,
            ).start()
    pending.put(job)
    return True


def _drain_background(work_id: str, pending: "queue.Queue[Callable[[], None]]") -> None:
    while True:
        job = pending.get()
        try:
            if is_draining():
                _log.info(
                    "dropping background kickoff job for %s (worker draining)",
                    work_id,
                )
            else:
                job()
        except Exception:
            _log.exception("background kickoff job crashed for %s", work_id)
        finally:
            pending.task_done()


def _run_background_kickoff(reason: KickoffReason, repo: Path) -> None:
    from cascade.workspace.supervisor_readiness import (
        note_recovery_turn_finished,
        note_recovery_turn_started,
    )

    note_recovery_turn_started(reason.work_id)
    try:
        _run_kickoff(reason, repo)
    except TurnCancelledForDrain:
        _log.info(
            "background kickoff turn cancelled for drain work_id=%s",
            reason.work_id,
        )
    except Exception as exc:
        _log.exception("background kickoff turn failed for %s", reason.work_id)
        _report_background_failure(reason.work_id, exc, repo)
    finally:
        note_recovery_turn_finished(reason.work_id)


def _report_background_failure(work_id: str, exc: Exception, repo: Path) -> None:
    from cascade.workspace.supervisor_readiness import record_recovery_failure

    record_recovery_failure(
        work_id,
        code="background_error",
        message=str(exc),
    )
    if work_id.startswith("task_"):
        try:
            from cascade.task.failure import fail_task

            fail_task(work_id, "background_error", root=repo)
        except Exception:
            _log.exception("could not fail crashed background task %s", work_id)
        return
    if not work_id.startswith(("epic_", "feat_")):
        return
    try:
        from cascade.war_room.chat_store import append_transcript_message

        append_transcript_message(
            work_id,
            author="system",
            body=f"Team turn failed: {exc}",
            root=repo,
        )
    except Exception:
        _log.exception("could not record kickoff failure for %s", work_id)


def resume_inflight_graphs(root: Path) -> None:
    """Resume interrupted turns and catch up queue cursors via the delivery path."""

    repo = Path(root).resolve()
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(repo)
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.path.parent.name != "2_active":
            continue
        if meta.tier not in ("epic", "feature", "task"):
            continue
        if meta.tier == "task":
            continue
        feature_id = meta.parent if meta.tier == "task" else None
        inflight = _graph_has_inflight_turn(
            work_id, meta.tier, root=repo, feature_id=feature_id
        )
        ahead = _queue_is_ahead(work_id, meta.tier, root=repo, feature_id=feature_id)
        if not inflight and not ahead and not _unanswered_staged_input(
            work_id, meta.tier, root=repo, feature_id=feature_id
        ):
            continue
        from cascade.workspace.supervisor_readiness import record_recovery_enqueued

        record_recovery_enqueued(work_id)
        _schedule_queue_delivery(work_id, meta.tier, repo, feature_id, retry_staged=True)


def kickoff_human_comment(doc_id: str, comment_id: str, *, root: Path) -> bool:
    """Start one comment-kind turn for a human comment on an active owning graph."""

    from cascade.comments.store import CommentStoreError, read_comments
    from cascade.workspace.integration_worktree import merged_board

    repo = Path(root).resolve()
    try:
        record = next(
            (row for row in read_comments(doc_id, root=repo) if row.id == comment_id),
            None,
        )
    except CommentStoreError:
        return False
    if record is None or record.author != "human":
        return False

    board = merged_board(repo)
    meta = board.by_id.get(doc_id)
    if meta is None or meta.path.parent.name != "2_active":
        return False
    if meta.tier not in ("epic", "feature"):
        return False

    message = {"role": "human", "content": _comment_kickoff_content(record)}
    kickoff_turn(
        KickoffReason(
            kind="comment",
            work_id=doc_id,
            by="watchdog",
            root=repo,
            message=message,
        )
    )
    return True


def deliver_queue_kickoffs(root: Path) -> None:
    """Submit coalesced delivery jobs when a graph queue is ahead of its cursor."""

    repo = Path(root).resolve()
    from cascade.workspace.integration_worktree import merged_board

    board = merged_board(repo)
    for work_id in sorted(board.by_id):
        meta = board.by_id[work_id]
        if meta.path.parent.name != "2_active":
            continue
        if meta.tier not in ("epic", "feature", "task"):
            continue
        feature_id = meta.parent if meta.tier == "task" else None
        if not _queue_is_ahead(work_id, meta.tier, root=repo, feature_id=feature_id):
            continue
        _schedule_queue_delivery(work_id, meta.tier, repo, feature_id)


def retry_failed_queue_kickoffs(root: Path) -> None:
    """Retry failed deliveries from memory without scanning every graph queue."""

    repo = Path(root).resolve()
    now = time.monotonic()
    with _registry_lock:
        due = [
            (work_id, tier, feature_id)
            for (failed_root, work_id), (tier, feature_id, _attempts, retry_at)
            in _failed_queue_delivery.items()
            if failed_root == repo and retry_at <= now
        ]
    for work_id, tier, feature_id in due:
        _schedule_queue_delivery(work_id, tier, repo, feature_id, retry_staged=True)


def kickoff_graph_queue_event(
    work_id: str,
    *,
    root: Path | None = None,
    by: str = "watchdog",
) -> bool:
    """Schedule one delivery job when the graph queue is ahead of its cursor."""

    repo = resolve_root(root)
    from cascade.workspace.integration_worktree import merged_board

    meta = merged_board(repo).by_id.get(work_id)
    if meta is None or meta.tier not in ("epic", "feature", "task"):
        return False
    feature_id = meta.parent if meta.tier == "task" else None
    if not _queue_is_ahead(work_id, meta.tier, root=repo, feature_id=feature_id):
        return False
    _schedule_queue_delivery(work_id, meta.tier, repo, feature_id)
    return True


def _queue_is_ahead(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    cursor = _queue_offset(work_id, tier, root=root, feature_id=feature_id)
    return queue_byte_size(work_id, root=root) > cursor


def _schedule_queue_delivery(
    work_id: str,
    tier: str,
    repo: Path,
    feature_id: str | None,
    *,
    retry_staged: bool = False,
) -> None:
    if _defer_turns.get():
        _submit_queue_delivery(work_id, tier, repo, feature_id, retry_staged=retry_staged)
        return
    _run_queue_delivery(work_id, tier, repo, feature_id, retry_staged=retry_staged)


def _submit_queue_delivery(
    work_id: str,
    tier: str,
    repo: Path,
    feature_id: str | None,
    *,
    retry_staged: bool = False,
) -> None:
    with _registry_lock:
        if work_id in _pending_queue_delivery:
            return
        _pending_queue_delivery.add(work_id)

    def job() -> None:
        try:
            _run_queue_delivery(work_id, tier, repo, feature_id, retry_staged=retry_staged)
        except Exception:
            with _registry_lock:
                key = (repo, work_id)
                previous = _failed_queue_delivery.get(key)
                attempts = (previous[2] if previous else 0) + 1
                delay = min(60.0, 2.0 ** min(attempts, 6))
                _failed_queue_delivery[key] = (
                    tier, feature_id, attempts, time.monotonic() + delay
                )
            raise
        else:
            with _registry_lock:
                _failed_queue_delivery.pop((repo, work_id), None)
        finally:
            with _registry_lock:
                _pending_queue_delivery.discard(work_id)

    if not _submit_background(work_id, job):
        with _registry_lock:
            _pending_queue_delivery.discard(work_id)


def _run_queue_delivery(
    work_id: str,
    tier: str,
    repo: Path,
    feature_id: str | None,
    *,
    retry_staged: bool = False,
) -> None:
    with _graph_lock(work_id):
        token = _model_turn_authorized.set(True)
        try:
            _run_queue_delivery_locked(
                work_id, tier, repo, feature_id, retry_staged=retry_staged
            )
        finally:
            _model_turn_authorized.reset(token)


def _log_queue_delivery(
    work_id: str,
    *,
    cursor_before: int,
    cursor_after: int,
    queue_size: int,
    turn_started: bool,
) -> None:
    _log.info(
        "graph queue delivery work_id=%s cursor_before=%s cursor_after=%s "
        "queue_size=%s turn_started=%s",
        work_id,
        cursor_before,
        cursor_after,
        queue_size,
        turn_started,
        extra={
            "work_id": work_id,
            "cursor_before": cursor_before,
            "cursor_after": cursor_after,
            "queue_size": queue_size,
            "turn_started": turn_started,
        },
    )


def _resume_inflight_turn_if_needed(
    work_id: str,
    tier: str,
    repo: Path,
    feature_id: str | None,
) -> bool:
    """Re-read ``snapshot.next`` under the graph lock and resume at most once."""

    if not _graph_has_inflight_turn(work_id, tier, root=repo, feature_id=feature_id):
        return False
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=repo)
        config = thread_config(work_id)
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=repo)
        config = thread_config(work_id)
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph = ensure_task_graph(work_id, root=repo, feature_id=feature_id)
        config = thread_config(work_id)
    snapshot = graph.get_state(config)
    if not snapshot.next:
        return False
    if not _checkpoint_has_models(work_id, tier, root=repo, feature_id=feature_id):
        return False
    cursor_before = _queue_offset(work_id, tier, root=repo, feature_id=feature_id)
    queue_size = queue_byte_size(work_id, root=repo)
    _log_queue_delivery(
        work_id,
        cursor_before=cursor_before,
        cursor_after=cursor_before,
        queue_size=queue_size,
        turn_started=True,
    )
    _invoke_role_turn(
        work_id,
        tier,
        root=repo,
        feature_id=feature_id,
        resume=True,
    )
    return True


def _run_queue_delivery_locked(
    work_id: str,
    tier: str,
    repo: Path,
    feature_id: str | None,
    *,
    retry_staged: bool = False,
) -> None:
    from cascade.watchdog.events import read_events

    _resume_inflight_turn_if_needed(work_id, tier, repo, feature_id)

    if retry_staged and _unanswered_staged_input(
        work_id, tier, root=repo, feature_id=feature_id
    ):
        kickoff_turn(
            KickoffReason(
                kind="queue_event",
                work_id=work_id,
                by="watchdog",
                root=repo,
                feature_id=feature_id,
            )
        )

    for _pass in range(2):
        before = _queue_offset(work_id, tier, root=repo, feature_id=feature_id)
        queue_size = queue_byte_size(work_id, root=repo)
        if queue_size <= before:
            return
        new_events, new_offset = read_events(work_id, before, root=repo)
        if not new_events:
            return
        from cascade.workspace.queue_observability import (
            note_batch_delivered,
            warn_duplicate_kickoff_if_needed,
        )

        warn_duplicate_kickoff_if_needed(work_id, new_offset, root=repo)
        staged = _staged_messages_from_queue_events(new_events, repo)
        after = _commit_classified_queue_batch(
            work_id,
            tier,
            staged,
            current_offset=before,
            new_offset=new_offset,
            root=repo,
            feature_id=feature_id,
        )
        if after <= before:
            return
        note_batch_delivered(work_id, after)
        _log_queue_delivery(
            work_id,
            cursor_before=before,
            cursor_after=after,
            queue_size=queue_size,
            turn_started=bool(staged),
        )
        if staged:
            kickoff_turn(
                KickoffReason(
                    kind="queue_event",
                    work_id=work_id,
                    by="watchdog",
                    root=repo,
                    feature_id=feature_id,
                )
            )


def _comment_kickoff_content(record) -> str:
    blocking = " [blocking]" if record.blocking else ""
    header = f"{record.id} on {record.doc_id} #{record.section}{blocking}\n"
    body = record.body
    full = header + body
    if len(full) <= _COMMENT_KICKOFF_CONTENT_CAP:
        return full
    reserve = len(header) + len(_COMMENT_KICKOFF_SIDECAR_NOTE)
    max_body = _COMMENT_KICKOFF_CONTENT_CAP - reserve
    if max_body <= 0:
        return (header + _COMMENT_KICKOFF_SIDECAR_NOTE)[:_COMMENT_KICKOFF_CONTENT_CAP]
    trimmed = body[:max_body].rstrip()
    if len(body) > max_body:
        trimmed = f"{trimmed}…"
    return header + trimmed + _COMMENT_KICKOFF_SIDECAR_NOTE


def _staged_messages_from_queue_events(events: list, repo: Path) -> list[dict]:
    """Map one queue batch to graph input messages, preserving queue order."""

    from cascade.feature.graph import _event_message

    staged: list[dict] = []
    for event in events:
        if event.type in _COMMENT_QUEUE_TYPES:
            if event.type in ("CommentPosted", "CommentReplied"):
                if event.payload.get("author") == "human":
                    message = _human_message_from_comment_event(event, repo)
                    if message is not None:
                        staged.append(message)
            continue
        staged.append(_event_message(event))
    return staged


def _human_message_from_comment_event(event, repo: Path) -> dict | None:
    doc_id = event.payload.get("doc_id")
    comment_id = event.payload.get("comment_id")
    if not isinstance(doc_id, str) or not isinstance(comment_id, str):
        return None
    from cascade.comments.store import CommentStoreError, read_comments

    try:
        record = next(
            (row for row in read_comments(doc_id, root=repo) if row.id == comment_id),
            None,
        )
    except CommentStoreError:
        return None
    if record is None or record.author != "human":
        return None
    return {"role": "human", "content": _comment_kickoff_content(record)}


def _commit_classified_queue_batch(
    work_id: str,
    tier: str,
    messages: list[dict],
    *,
    current_offset: int,
    new_offset: int,
    root: Path,
    feature_id: str | None,
) -> int:
    """Advance the cursor for a batch and stage classified messages when needed."""

    resolved = resolve_last_queue_offset(
        work_id,
        current=current_offset,
        proposed=new_offset,
        root=root,
    )
    update: dict = {"last_queue_offset": resolved}
    if messages:
        update["messages"] = messages

    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            update.setdefault("epic_id", work_id)
            if not messages:
                update.setdefault("messages", [])
        graph.update_state(config, update)
        return int(resolved)

    if tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            update.setdefault("feature_id", work_id)
            if not messages:
                update.setdefault("messages", [])
        graph.update_state(config, update)
        return int(resolved)

    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
    config = thread_config(work_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        update.setdefault("task_id", work_id)
        update.setdefault("feature_id", feature_id or "")
        update.setdefault("skill_playbooks", [])
        if not messages:
            update.setdefault("messages", [])
    graph.update_state(config, update)
    return int(resolved)


def _kickoff_turn(reason: KickoffReason, repo: Path) -> None:
    from cascade.workspace.integration_worktree import doc_filesystem_root

    doc = None
    tier: str | None = None
    try:
        from cascade.board.errors import GitError
        from cascade.board.gitutil import has_git
        from cascade.workspace.integration_worktree import doc_filesystem_root

        if has_git(repo):
            doc_root = doc_filesystem_root(reason.work_id, trunk=repo)
        else:
            doc_root = repo
        doc = read_doc(reason.work_id, root=doc_root)
        tier = doc.meta.tier
    except (NotFound, GitError):
        tier = _tier_from_work_id(reason.work_id)
    if tier not in ("epic", "feature", "task"):
        return

    feature_id = reason.feature_id or (doc.meta.parent if doc is not None else None)
    if reason.kind != "resume_inflight" and not _graph_has_inflight_turn(
        reason.work_id,
        tier,
        root=repo,
        feature_id=feature_id,
    ):
        _ingest_queue_only(
            reason.work_id,
            tier,
            root=repo,
            feature_id=feature_id,
        )

    if reason.kind in ("human_message", "comment") and reason.message is not None:
        meta = doc.meta if doc is not None else None
        feature_id = reason.feature_id or (doc.meta.parent if doc else None)
        if _graph_has_inflight_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=feature_id,
        ) and _checkpoint_has_models(
            reason.work_id,
            tier,
            root=repo,
            feature_id=feature_id,
        ):
            _invoke_role_turn(
                reason.work_id,
                tier,
                root=repo,
                feature_id=feature_id,
                model_id=reason.model_id,
                resume=True,
            )
        _stage_human_message(
            reason.work_id,
            tier,
            reason.message,
            root=repo,
            feature_id=feature_id,
            model_id=reason.model_id,
        )
        if not _ensure_role_models(
            reason.work_id,
            tier,
            meta,
            repo,
            reason.model_id,
            toast_on_failure=reason.kind in ("human_message", "comment"),
        ):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
            model_id=reason.model_id,
        )
        return

    if reason.kind == "resume_inflight":
        if not _graph_has_inflight_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
        ):
            return
        if not _checkpoint_has_models(reason.work_id, tier, root=repo, feature_id=reason.feature_id):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or (doc.meta.parent if doc else None),
            model_id=reason.model_id,
            resume=True,
        )
        return

    if doc is None:
        return

    if reason.kind in ("activate", "dispatch", "queue_event"):
        if not _checkpoint_has_models(reason.work_id, tier, root=repo, feature_id=reason.feature_id):
            if reason.kind in ("activate", "dispatch"):
                if not _ensure_role_models(
                    reason.work_id,
                    tier,
                    doc.meta,
                    repo,
                    reason.model_id,
                    toast_on_failure=False,
                ):
                    return
            else:
                return
        if not _has_turn_input(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or doc.meta.parent,
        ):
            return
        _invoke_role_turn(
            reason.work_id,
            tier,
            root=repo,
            feature_id=reason.feature_id or doc.meta.parent,
            model_id=reason.model_id,
        )


def _tier_from_work_id(work_id: str) -> str | None:
    if work_id.startswith("epic_"):
        return "epic"
    if work_id.startswith("feat_"):
        return "feature"
    if work_id.startswith("task_"):
        return "task"
    return None


def _ensure_role_models(
    work_id: str,
    tier: str,
    meta,
    repo: Path,
    model_id: str | None,
    *,
    toast_on_failure: bool = False,
) -> bool:
    parent = meta.parent if meta is not None else None
    explicit_model = model_id is not None and str(model_id).strip()
    if _checkpoint_has_models(work_id, tier, root=repo, feature_id=parent):
        return True
    if meta is None and not explicit_model:
        return False
    doc_meta = meta
    from cascade.watchdog.boot_model import toast_model_config_failure
    from cascade.watchdog.config import ConfigError
    from cascade.agent.errors import ProviderConfigError
    from cascade.watchdog.model_resolve import (
        ModelConfigError,
        ResolvedBackend,
        ResolvedModel,
        resolve_backend,
        resolve_project_provider,
    )

    explicit_model_id = str(model_id).strip() if explicit_model else None

    def _with_explicit_model(role: str, backend: ResolvedBackend) -> ResolvedBackend:
        if explicit_model_id is None:
            return backend
        return ResolvedBackend(
            provider=backend.provider,
            provider_source=backend.provider_source,
            model=ResolvedModel(role=role, model_id=explicit_model_id, source="document"),  # type: ignore[arg-type]
        )

    def _provider_only_backend(role: str) -> ResolvedBackend:
        provider, provider_source = resolve_project_provider(doc_meta, root=repo)
        return ResolvedBackend(
            provider=provider,
            provider_source=provider_source,
            model=ResolvedModel(
                role=role,  # type: ignore[arg-type]
                model_id=explicit_model_id or "",
                source="document",
            ),
        )

    def _resolve_role_backend(role: str) -> ResolvedBackend:
        try:
            return _with_explicit_model(role, resolve_backend(role, doc_meta, root=repo))  # type: ignore[arg-type]
        except ModelConfigError:
            if explicit_model_id is None:
                raise
            backend = _provider_only_backend(role)
            if not backend.model.model_id:
                raise
            return backend

    try:
        if tier == "epic":
            from cascade.epic.graph import seed_epic_role_models

            manager = _resolve_role_backend("epic_manager")
            architect = _resolve_role_backend("epic_architect")
            seed_epic_role_models(
                work_id,
                manager=manager,
                architect=architect,
                root=repo,
            )
        elif tier == "feature":
            from cascade.feature.graph import seed_feature_role_models

            lead = _resolve_role_backend("feature_lead")
            architect = _resolve_role_backend("feature_architect")
            seed_feature_role_models(
                work_id,
                lead=lead,
                architect=architect,
                root=repo,
            )
        else:
            from cascade.task.graph import seed_task_role_models

            swe = _resolve_role_backend("swe")
            seed_task_role_models(
                work_id,
                swe=swe,
                root=repo,
                feature_id=parent,
            )
    except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
        if toast_on_failure:
            toast_model_config_failure(work_id, str(exc), root=repo)
        return False
    return True


def _checkpoint_has_providers(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    provider_ids = state.get("provider_ids") or {}
    if tier == "epic":
        return bool(str(provider_ids.get("epic_manager") or "").strip()) and bool(
            str(provider_ids.get("epic_architect") or "").strip()
        )
    if tier == "feature":
        return bool(str(provider_ids.get("feature_lead") or "").strip()) and bool(
            str(provider_ids.get("feature_architect") or "").strip()
        )
    return bool(str(provider_ids.get("swe") or "").strip())


def _checkpoint_has_models(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    if not _checkpoint_has_providers(work_id, tier, root=root, feature_id=feature_id):
        return False
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    if model_id_from_state(state) is not None:
        return True
    model_ids = state.get("model_ids") or {}
    if tier == "epic":
        return bool(str(model_ids.get("epic_manager") or "").strip()) and bool(
            str(model_ids.get("epic_architect") or "").strip()
        )
    if tier == "feature":
        return bool(str(model_ids.get("feature_lead") or "").strip()) and bool(
            str(model_ids.get("feature_architect") or "").strip()
        )
    return bool(str(model_ids.get("swe") or "").strip())


def model_id_from_state(state: dict) -> str | None:
    from cascade.agent.graph_turn import model_id_from_state as _from_graph

    return _from_graph(state)


def _has_turn_input(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    from cascade.agent.graph_turn import latest_input

    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return False
    return latest_input(state.get("messages") or []) is not None


def _unanswered_staged_input(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    """True when the last checkpointed message is input with no role reply yet."""

    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state or not _checkpoint_has_models(
        work_id, tier, root=root, feature_id=feature_id
    ):
        return False
    messages = state.get("messages") or []
    return bool(messages) and messages[-1].get("role") in {"event", "human"}


def _queue_offset(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> int:
    state = _graph_state(work_id, tier, root=root, feature_id=feature_id)
    if not state:
        return 0
    return int(state.get("last_queue_offset") or 0)


def _ingest_queue_only(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> dict:
    if tier == "epic":
        from cascade.epic.graph import ingest_queue

        return dict(ingest_queue(work_id, root=root))
    if tier == "feature":
        from cascade.feature.graph import ingest_queue

        return dict(ingest_queue(work_id, root=root))
    from cascade.task.graph import ingest_queue

    return dict(ingest_queue(work_id, root=root, feature_id=feature_id))


def _graph_state(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> dict | None:
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
        config = thread_config(work_id)
    values = graph.get_state(config).values
    return dict(values) if values else None


def _graph_has_inflight_turn(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
) -> bool:
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        role_names = frozenset({"epic_manager", "epic_architect"})
    elif tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        role_names = frozenset({"feature_lead", "feature_architect"})
    else:
        from cascade.task.checkpoint import thread_config
        from cascade.task.graph import ensure_task_graph

        graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
        config = thread_config(work_id)
        role_names = frozenset({"swe"})
    snapshot = graph.get_state(config)
    if not snapshot.next:
        return False
    messages = (snapshot.values or {}).get("messages") or []
    return any(m.get("role") in role_names for m in messages)


def _stage_human_message(
    work_id: str,
    tier: str,
    message: dict,
    *,
    root: Path,
    feature_id: str | None,
    model_id: str | None,
) -> None:
    payload: dict = {"messages": [message]}
    if model_id is not None:
        payload["model_id"] = model_id
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            payload["epic_id"] = work_id
            payload["last_queue_offset"] = resolve_last_queue_offset(
                work_id, current=0, proposed=0, root=root
            )
        graph.update_state(config, payload)
        return
    if tier == "feature":
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        if not snapshot.values:
            payload["feature_id"] = work_id
            payload["last_queue_offset"] = resolve_last_queue_offset(
                work_id, current=0, proposed=0, root=root
            )
        graph.update_state(config, payload)
        return
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph

    graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
    config = thread_config(work_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        payload.update(
            {
                "task_id": work_id,
                "feature_id": feature_id or "",
                "last_queue_offset": resolve_last_queue_offset(
                    work_id, current=0, proposed=0, root=root
                ),
                "skill_playbooks": [],
            }
        )
    graph.update_state(config, payload)


def _invoke_role_turn(
    work_id: str,
    tier: str,
    *,
    root: Path,
    feature_id: str | None,
    model_id: str | None = None,
    resume: bool = False,
) -> None:
    if tier == "epic":
        from cascade.agent.graph_turn import clear_turn_model_override
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        before = len((snapshot.values or {}).get("messages") or [])
        graph.invoke({}, config)
        after = graph.get_state(config).values or {}
        new_messages = (after.get("messages") or [])[before:]
        from cascade.war_room.planning_transcript import append_planning_turn_to_chat

        append_planning_turn_to_chat(work_id, new_messages, root=root)
        if model_id is not None:
            clear_turn_model_override(graph, config)
        return
    if tier == "feature":
        from cascade.agent.graph_turn import clear_turn_model_override
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(work_id, root=root)
        config = thread_config(work_id)
        snapshot = graph.get_state(config)
        before = len((snapshot.values or {}).get("messages") or [])
        graph.invoke({}, config)
        after = graph.get_state(config).values or {}
        new_messages = (after.get("messages") or [])[before:]
        from cascade.war_room.planning_transcript import append_planning_turn_to_chat

        append_planning_turn_to_chat(work_id, new_messages, root=root)
        if model_id is not None:
            clear_turn_model_override(graph, config)
        return
    from cascade.agent.graph_turn import clear_turn_model_override
    from cascade.task.checkpoint import thread_config
    from cascade.task.graph import ensure_task_graph
    from cascade.task.failure import defer_task_teardown, flush_deferred_task_teardown

    graph = ensure_task_graph(work_id, root=root, feature_id=feature_id)
    config = thread_config(work_id)
    payload: dict = {}
    if model_id is not None:
        payload["model_id"] = model_id
    token = defer_task_teardown()
    try:
        graph.invoke(payload, config)
        if model_id is not None:
            clear_turn_model_override(graph, config)
    finally:
        flush_deferred_task_teardown(token)
