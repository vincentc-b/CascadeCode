"""Task boot hook: stale parent_rev check, graph compile, TaskActivated on feature queue."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.store import read_doc
from cascade.task.graph import seed_task_role_models
from cascade.watchdog.events import append_event
from cascade.watchdog.hooks import register_boot_hook
from cascade.watchdog.config import ConfigError
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend
from cascade.watchdog.types import Event

_boot_root: Path | None = None
_last_fail_closed: tuple[str, str] | None = None


def fail_closed_boot(task_id: str, reason: str) -> None:
    """Record boot-time failure intent; must not dispatch or compile a graph."""

    global _last_fail_closed
    _last_fail_closed = (task_id, reason)
    if _boot_root is not None:
        from cascade.task.failure import fail_task

        fail_task(task_id, reason, root=_boot_root)


def last_fail_closed_boot() -> tuple[str, str] | None:
    """Return the most recent fail_closed_boot call, if any."""

    return _last_fail_closed


def boot_task(work_id: str) -> None:
    if _boot_root is None:
        raise RuntimeError("install_task_boot_hook(root) must run before boot_task")
    from cascade.workspace.integration_worktree import doc_filesystem_root

    try:
        doc_root = doc_filesystem_root(work_id, trunk=_boot_root)
        task = read_doc(work_id, root=doc_root)
    except Exception:
        return
    if task.meta.tier != "task":
        return
    feature_id = task.meta.parent
    if not feature_id:
        return

    pinned = task.meta.parent_rev
    try:
        feature_root = doc_filesystem_root(feature_id, trunk=_boot_root)
    except Exception:
        fail_closed_boot(work_id, reason="parent_feature_unavailable")
        return
    try:
        if pinned is not None:
            read_doc(feature_id, rev=pinned, root=feature_root)
        else:
            read_doc(feature_id, root=feature_root)
    except Exception:
        fail_closed_boot(work_id, reason="parent_feature_unavailable")
        return

    if pinned is not None:
        try:
            current_parent = read_doc(feature_id, root=feature_root)
        except Exception:
            fail_closed_boot(work_id, reason="parent_feature_unavailable")
            return
        if current_parent.sha != pinned:
            fail_closed_boot(work_id, reason="stale_parent_rev")
            return

    try:
        swe = resolve_backend("swe", task.meta, root=_boot_root)
    except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
        fail_closed_boot(work_id, reason=str(exc))
        return

    seed_task_role_models(
        work_id,
        swe=swe,
        root=_boot_root,
        feature_id=feature_id,
    )
    append_event(
        feature_id,
        Event(
            type="TaskActivated",
            ts=datetime.now(timezone.utc),
            payload={"task_id": work_id, "feature_id": feature_id},
            dest=feature_id,
        ),
        root=_boot_root,
    )


def install_task_boot_hook(root: Path) -> None:
    """Register the task boot hook for this repo root (idempotent)."""

    global _boot_root
    _boot_root = Path(root).resolve()
    from cascade.watchdog.hooks import _boot

    if not any(fn is boot_task for fn in _boot["task"]):
        register_boot_hook("task", boot_task)
