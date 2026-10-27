"""Feature Team recovery tools for its own failed Task children."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import GitError, NotFound
from cascade.board.lock import process_lock
from cascade.board.store import read_doc, write_doc
from cascade.feature.registry import register_feature_tool
from cascade.watchdog.dispatch import dispatch_task
from cascade.workspace.integration_worktree import doc_filesystem_root, locate_trunk


def revise_task(task_id: str, body: str, *, feature_id: str, root: Path) -> str | None:
    """Replace an owned blocked/backlog Task body before a supervised retry."""

    trunk = locate_trunk(Path(root).resolve())
    feature_root = doc_filesystem_root(feature_id, trunk=trunk)
    try:
        task = read_doc(task_id, root=feature_root)
    except NotFound:
        raise ValueError(f"unknown task {task_id}") from None
    if task.meta.tier != "task" or task.meta.parent != feature_id:
        raise ValueError(f"{task_id} is not a child of {feature_id}")
    if task.meta.status not in ("backlog", "ready_to_plan", "blocked"):
        raise ValueError(f"{task_id} cannot be revised while {task.meta.status}")
    if not isinstance(body, str) or not body.strip():
        raise ValueError("task body must not be empty")
    task.body = body.strip() + "\n"
    return write_doc(task, root=feature_root)


def _typed_reason(error: object, *, blocked: bool) -> str:
    """Turn legacy execution errors into a small, operator-facing vocabulary."""

    value = str(error or "").strip().lower()
    if any(token in value for token in ("permission", "unauthorized", "forbidden", "credential")):
        return "permission_refused"
    if any(token in value for token in ("forge", "infra", "timeout", "connection", "network", "worker failed")):
        return "transient_forge_failure"
    if value in {"tests_red", "spec_error", "no_task_changes", "forbidden_commit_paths"}:
        return "execution_failure"
    return "blocked_execution" if blocked else "in_progress"


def recovery_status(task_id: str, *, feature_id: str, root: Path) -> dict[str, object]:
    """Return the recovery contract for one Feature-owned Task.

    Approval and review requirements remain distinct lifecycle actions; neither
    is represented as a retry control.
    """

    trunk = locate_trunk(Path(root).resolve())
    # Board reads can run against a lightweight, non-Git fixture.  The trunk
    # still owns the task document in that case, so preserve the recovery
    # contract instead of making the entire board unavailable.
    try:
        feature_root = doc_filesystem_root(feature_id, trunk=trunk)
    except GitError:
        feature_root = trunk
    try:
        task = read_doc(task_id, root=feature_root)
    except NotFound:
        raise ValueError(f"unknown task {task_id}") from None
    if task.meta.tier != "task" or task.meta.parent != feature_id:
        raise ValueError(f"{task_id} is not a child of {feature_id}")

    from cascade.task.execution import execution_view
    from cascade.workspace.integration_worktree import get_integration_worktree, integration_branch

    execution = execution_view(task_id, root=trunk) or {}
    recorded_phase = str(
        execution.get("phase") or ("terminal" if task.meta.status == "blocked" else "unknown")
    )
    # Dispatch changes the task document before the worker records its next
    # execution phase. Do not re-offer a retry from that stale terminal record.
    phase = "queued" if task.meta.status == "active" and recorded_phase == "terminal" else recorded_phase
    typed_reason = _typed_reason(execution.get("last_error"), blocked=task.meta.status == "blocked")
    terminal = task.meta.status == "blocked"
    retryable = terminal and typed_reason in {"transient_forge_failure", "blocked_execution"}
    checkout = get_integration_worktree(trunk, "task", task_id)
    affected: dict[str, object] = {"branch": integration_branch("task", task_id)}
    if checkout is not None:
        affected["checkout"] = checkout.path.as_posix()

    if typed_reason == "permission_refused":
        next_safe_step = "Resolve the required permission or credential; retry cannot bypass it."
        action = "permission"
    elif retryable:
        next_safe_step = "Retry the original Task execution through its existing dispatch path."
        action = "retry"
    elif terminal:
        next_safe_step = "Revise the Task or resolve its terminal blocker before another dispatch."
        action = "none"
    else:
        next_safe_step = "Wait for the original execution path to report progress."
        action = "none"

    return {
        "phase": phase,
        "reason": typed_reason,
        "attempt_count": int(execution.get("attempt") or 0),
        "owner": execution.get("owner_pid"),
        "affected": affected,
        "next_safe_step": next_safe_step,
        "terminal_blocker": {"retryable": retryable},
        "action": action,
    }


def retry_task(task_id: str, *, feature_id: str, root: Path) -> dict[str, object]:
    """Atomically claim one eligible retry through the normal dispatch gates."""

    trunk = locate_trunk(Path(root).resolve())
    # dispatch_task takes this same re-entrant lock while it changes the board.
    # The check and transition are therefore one atomic retry claim.
    with process_lock:
        status = recovery_status(task_id, feature_id=feature_id, root=trunk)
        if status["action"] != "retry":
            return {
                "ok": False,
                "reason": "not_retryable",
                "task_id": task_id,
                "recovery": status,
            }
        result = dispatch_task(task_id, "boss", root=trunk)
    return {
        "ok": result.ok,
        "reason": result.reason,
        "task_id": task_id,
        "recovery": recovery_status(task_id, feature_id=feature_id, root=trunk),
    }


register_feature_tool("revise_task", revise_task)
register_feature_tool("retry_task", retry_task)
register_feature_tool("recovery_status", recovery_status)
