"""Human Boss orders consumed from the ``boss`` JSONL queue.

Event shapes
------------

``BossDispatchRequested`` (War Room ``POST /api/ask_boss_dispatch``):

``{ "kind": "feature" | "task", "id": "<work_id>", "by": "human" }``

Dispatches that single id via ``dispatch_feature`` / ``dispatch_task`` with
``by="boss"``.

``BossDrainRequested`` (task_044 will enqueue from ``POST /api/boss_drain``):

``{ "feature_id": "<feature_id>", "by": "human" }``

Once per order, dispatches backlog tasks under ``feature_id`` that appear in
``compute_boss_view().dispatchable_tasks``, in board sort order, stopping when
``dispatch_task`` returns ``cap`` or the list is exhausted. Blocked/failed tasks
are never inferred from a drain; use an explicit ``BossDispatchRequested`` for
that task id.
"""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.store import list_board
from cascade.boss.view import compute_boss_view
from cascade.watchdog.dispatch import dispatch_feature, dispatch_task
from cascade.watchdog.types import Event


def process_boss_event(event: Event, *, root: Path | None = None) -> None:
    """Apply one boss-queue event. Unknown types are ignored."""

    repo = resolve_root(root)
    if event.type == "BossDispatchRequested":
        _handle_dispatch_requested(event.payload, repo)
    elif event.type == "BossDrainRequested":
        _handle_drain_requested(event.payload, repo)


def _handle_dispatch_requested(payload: dict[str, object], root: Path) -> None:
    kind = payload.get("kind")
    work_id = payload.get("id")
    if kind not in ("feature", "task") or not isinstance(work_id, str) or not work_id:
        return
    if kind == "feature":
        dispatch_feature(work_id, "boss", root=root)
    else:
        dispatch_task(work_id, "boss", root=root)


def _handle_drain_requested(payload: dict[str, object], root: Path) -> None:
    feature_id = payload.get("feature_id")
    if not isinstance(feature_id, str) or not feature_id:
        return

    view = compute_boss_view(root=root)
    board = list_board(root)
    for task_id in view.dispatchable_tasks:
        meta = board.by_id.get(task_id)
        if meta is None or meta.parent != feature_id:
            continue
        result = dispatch_task(task_id, "boss", root=root)
        if not result.ok and result.reason == "cap":
            break
