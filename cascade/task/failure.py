"""Task failure classification, retry budget, and fail_task side effects."""

from __future__ import annotations

import errno
from contextvars import ContextVar, Token
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Literal

from cascade.agent.errors import CursorAgentError
from cascade.board.errors import NotFound
from cascade.board.store import read_doc, save_doc
from cascade.task.registry import register_task_tool
from cascade.watchdog.events import append_event
from cascade.watchdog.hooks import invoke_teardown
from cascade.watchdog.types import Event

ErrorKind = Literal["infra", "spec"]

_INFRA_EXCEPTION_TYPES = (TimeoutError, ConnectionError, BrokenPipeError, BlockingIOError)
_deferred_teardown: ContextVar[set[str] | None] = ContextVar("_deferred_teardown", default=None)
_teardown_lock = RLock()
_active_teardown_scopes = 0
_process_pending_teardown: set[str] = set()

_TRANSIENT_ERRNOS = frozenset(
    {
        errno.ETIMEDOUT,
        errno.ECONNRESET,
        errno.ECONNREFUSED,
        errno.EPIPE,
        errno.ENETUNREACH,
        errno.EHOSTUNREACH,
    }
)


def classify_error(exc_or_result: object) -> ErrorKind:
    """Classify tool or test outcomes. Uncertain cases fail closed as spec."""

    if isinstance(exc_or_result, dict):
        explicit = exc_or_result.get("kind") or exc_or_result.get("error_kind")
        if explicit == "infra":
            return "infra"
        if explicit == "spec":
            return "spec"
        if exc_or_result.get("infra") is True:
            return "infra"
        return "spec"

    if isinstance(exc_or_result, BaseException):
        if isinstance(exc_or_result, CursorAgentError):
            return "infra" if exc_or_result.retryable else "spec"
        if isinstance(exc_or_result, _INFRA_EXCEPTION_TYPES):
            return "infra"
        if isinstance(exc_or_result, OSError):
            err = getattr(exc_or_result, "errno", None)
            if err in _TRANSIENT_ERRNOS:
                return "infra"
        return "spec"

    status = getattr(exc_or_result, "status", None)
    if status == "error":
        return "spec"

    kind = getattr(exc_or_result, "kind", None)
    if kind == "infra":
        return "infra"
    if kind == "spec":
        return "spec"

    return "spec"


def defer_task_teardown() -> Token:
    """Defer ``invoke_teardown`` until ``flush_deferred_task_teardown`` (graph invoke)."""
    global _active_teardown_scopes
    with _teardown_lock:
        _active_teardown_scopes += 1
    return _deferred_teardown.set(set())


def flush_deferred_task_teardown(token: Token) -> None:
    """Run teardown for tasks that failed while teardown was deferred."""
    global _active_teardown_scopes
    pending = _deferred_teardown.get()
    _deferred_teardown.reset(token)
    with _teardown_lock:
        if pending:
            _process_pending_teardown.update(pending)
        _active_teardown_scopes = max(0, _active_teardown_scopes - 1)
        if _active_teardown_scopes:
            return
        ready = sorted(_process_pending_teardown)
        _process_pending_teardown.clear()
    for task_id in ready:
        invoke_teardown("task", task_id)


def schedule_task_teardown(task_id: str) -> None:
    """Tear down now, or after the current Task graph finishes checkpointing."""

    pending = _deferred_teardown.get()
    if pending is not None:
        pending.add(task_id)
        return
    # LangGraph may execute the node in a worker thread, where ContextVar state
    # is not guaranteed to match the caller.  The process-wide scope prevents
    # that worker from closing its checkpointer before graph.invoke returns.
    with _teardown_lock:
        if _active_teardown_scopes:
            _process_pending_teardown.add(task_id)
            return
    invoke_teardown("task", task_id)


def maybe_retry(task_id: str, kind: ErrorKind, attempt: int, *, root: Path) -> bool:
    """Return whether another SWE turn may retry after this failure."""

    _ = task_id, root
    if kind == "spec":
        return False
    return attempt < 2


def fail_task(task_id: str, reason: str, *, root: Path) -> None:
    """Emit failure events, block the task in place, and tear down the graph."""

    repo = Path(root).resolve()
    from cascade.task.execution import mark_terminal

    mark_terminal(task_id, "failed", root=repo, error=reason)
    try:
        task = read_doc(task_id, root=repo)
    except NotFound:
        return
    if task.meta.tier != "task":
        return

    already_blocked = task.meta.status == "blocked"
    feature_id = task.meta.parent
    if feature_id and not already_blocked:
        append_event(
            feature_id,
            Event(
                type="TaskFailed",
                ts=datetime.now(timezone.utc),
                payload={"task_id": task_id, "reason": reason},
                dest=feature_id,
            ),
            root=repo,
        )

    if not already_blocked:
        message = f"Task {task_id} failed: {reason}"
        append_event(
            "war_room",
            Event(
                type="Toast",
                ts=datetime.now(timezone.utc),
                payload={
                    "kind": "task_failed",
                    "id": task_id,
                    "message": message,
                    "body": message,
                },
                dest="war_room",
            ),
            root=repo,
        )

        previous_path = task.meta.path.resolve()
        task.meta.status = "blocked"
        task.meta.updated = date.today()
        # `read_doc(..., root=trunk)` may resolve this Task from its owning
        # Feature worktree.  Commit the state transition in that checkout;
        # trying to stage `.cascade/worktrees/...` from trunk is both wrong and
        # rejected by the trunk's ignore rules.
        from cascade.workspace.integration_worktree import git_root_for_path

        owner_root = git_root_for_path(previous_path)
        save_doc(task, previous_path=previous_path, root=owner_root)

    from cascade.task.worktree import get_task_run

    run = get_task_run(task_id)
    if run is not None:
        run.state = "failed"

    schedule_task_teardown(task_id)


register_task_tool("fail_task", fail_task)
