"""One-shot replay context shared by canonical dispatch and kickoff boundaries."""

from __future__ import annotations

import contextvars
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from cascade.agent.capability_contract import EffectiveSelection
from cascade.board.context import resolve_root
from cascade.provider_recovery_ledger_lock import recovery_ledger_lock
from cascade.provider_recovery_receipt import record_continuation_lifecycle_effect
from cascade.watchdog.model_resolve import (
    resolve_effective_selections,
    selection_member_fingerprint,
)
from cascade.watchdog.types import DispatchResult
from cascade.workspace.doc_root import read_doc_resolved


@dataclass(frozen=True, slots=True)
class ReplayContext:
    receipt_id: str
    handoff_id: str
    waiver_id: str
    work_id: str
    before: dict[str, object]
    root: Path


_active: contextvars.ContextVar[ReplayContext | None] = contextvars.ContextVar(
    "provider_recovery_replay", default=None
)


def selection_snapshot(work_id: str, *, root: Path) -> dict[str, object]:
    doc = read_doc_resolved(work_id, root=root)
    batch = resolve_effective_selections(doc, root=root)
    roles = []
    for item in batch.roles:
        if not isinstance(item, EffectiveSelection):
            raise ValueError("continuation selection is incomplete")
        roles.append(
            {
                "role": item.role,
                "provider": item.provider,
                "model_id": item.model_id,
                "reasoning_level": item.reasoning_level,
                "requested_flex": item.reviewed_flex_mode,
                "document_revision": item.document_revision,
                "member_fingerprint": selection_member_fingerprint(item),
            }
        )
    return {
        "document_path": next(
            (item.document_path for item in batch.selections),
            str(doc.meta.path),
        ),
        "document_revision": next(
            (item.document_revision for item in batch.selections), ""
        ),
        "selection_fingerprint": batch.selection_fingerprint,
        "parent_revision": doc.meta.parent_rev,
        "roles": roles,
    }


@contextmanager
def continuation_replay_context(context: ReplayContext) -> Iterator[None]:
    token = _active.set(context)
    try:
        yield
    finally:
        _active.reset(token)


def active_replay_context(work_id: str, root: Path) -> ReplayContext | None:
    context = _active.get()
    if (
        context is None
        or context.work_id != work_id
        or context.root != resolve_root(root)
    ):
        return None
    return context


def record_canonical_replay_transition(
    result: DispatchResult,
    *,
    work_id: str,
    root: Path,
) -> bool:
    """Persist verified relocation/pin lineage before canonical boot begins."""

    context = active_replay_context(work_id, root)
    if context is None or not result.ok or result.event is None:
        return context is None or not result.ok
    try:
        after = selection_snapshot(work_id, root=context.root)
    except (OSError, ValueError, TypeError, KeyError):
        return False
    if not _same_selection(context.before, after):
        return False
    if context.before != after:
        _persist_lineage(context, after)
    record_continuation_lifecycle_effect(
        context.receipt_id,
        context.handoff_id,
        root=context.root,
        event_type=result.event.type,
        event_dest=result.event.dest,
    )
    return True


def kickoff_receipt(work_id: str, root: Path) -> tuple[str, str] | None:
    context = active_replay_context(work_id, root)
    if context is None:
        return None
    return context.receipt_id, context.handoff_id


def _same_selection(before: dict[str, object], after: dict[str, object]) -> bool:
    def stable(snapshot: dict[str, object]) -> list[tuple[object, ...]]:
        rows = snapshot.get("roles")
        if not isinstance(rows, list):
            return []
        return sorted(
            (
                row.get("role"),
                row.get("provider"),
                row.get("model_id"),
                row.get("reasoning_level"),
                row.get("requested_flex"),
            )
            for row in rows
            if isinstance(row, dict)
        )

    return bool(stable(before)) and stable(before) == stable(after)


def _persist_lineage(context: ReplayContext, after: dict[str, object]) -> None:
    transition_kinds = []
    if context.before.get("document_path") != after.get("document_path"):
        transition_kinds.append("status_relocation")
    if context.before.get("parent_revision") != after.get("parent_revision"):
        transition_kinds.append("task_parent_pin_refresh")
    row = {
        "receipt_id": context.receipt_id,
        "handoff_id": context.handoff_id,
        "waiver_id": context.waiver_id,
        "work_id": context.work_id,
        "transition_kinds": transition_kinds,
        "before": context.before,
        "after": after,
    }
    key = f"{context.receipt_id}:{context.handoff_id}"
    with recovery_ledger_lock(context.root):
        ledger = _read(context.root)
        existing = ledger.get("flex_waiver_lineage")
        rows = dict(existing) if isinstance(existing, dict) else {}
        previous = rows.get(key)
        if previous is not None and previous != row:
            raise ValueError("handoff already names different waiver lineage")
        rows[key] = row
        ledger["flex_waiver_lineage"] = rows
        _write(context.root, ledger)


def _path(root: Path) -> Path:
    return root / ".cascade" / "provider_recoveries.json"


def _read(root: Path) -> dict[str, object]:
    path = _path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, json.JSONDecodeError):
        return {"version": 2}
    return {**payload, "version": 2} if isinstance(payload, dict) else {"version": 2}


def _write(root: Path, payload: dict[str, object]) -> None:
    path = _path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        Path(name).replace(path)
    finally:
        Path(name).unlink(missing_ok=True)


__all__ = [
    "ReplayContext",
    "active_replay_context",
    "continuation_replay_context",
    "kickoff_receipt",
    "record_canonical_replay_transition",
    "selection_snapshot",
]
