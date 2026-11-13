"""Revision evidence for read-only feature readiness projections."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_tracking_root
from cascade.board.store import read_doc
from cascade.board.types import BoardIndex, WorkMeta
from cascade.watchdog.types import DispatchResult

SOURCES = ("board", "approval", "dependencies", "review", "provider", "dispatch_base")


def owning_revision(meta: WorkMeta, *, root: Path) -> str | None:
    try:
        body = read_doc(meta.id, root=root).body
    except (OSError, ValueError, KeyError):
        return None
    return digest(
        {
            "body": body,
            "parent": meta.parent,
            "provider": meta.provider,
            "model": meta.model,
            "models": meta.models,
            "reasoning": meta.reasoning,
            "flex_mode": meta.flex_mode,
        }
    )


def write_approval_evidence(meta: WorkMeta, *, root: Path) -> None:
    revision = owning_revision(meta, root=root)
    if revision is None:
        return
    path = _state_dir(root) / "feature_approvals.json"
    with _locked(path):
        payload = _read_json(path, {"version": 1, "features": {}})
        payload.setdefault("features", {})[meta.id] = {
            "approved_at": (meta.approved_at or datetime.now(timezone.utc))
            .astimezone(timezone.utc)
            .isoformat(),
            "revision": revision,
        }
        _atomic_json(path, payload)


def approval_evidence(
    meta: WorkMeta, *, root: Path
) -> tuple[Literal["current", "stale", "unknown"], str | None]:
    current = owning_revision(meta, root=root)
    if meta.approved_at is None:
        return "current", current
    record = (
        _read_json(_state_dir(root) / "feature_approvals.json", {})
        .get("features", {})
        .get(meta.id)
    )
    if (
        current is None
        or not isinstance(record, dict)
        or not isinstance(record.get("revision"), str)
    ):
        return "unknown", current
    return ("current" if record["revision"] == current else "stale"), current


def board_revision(board: BoardIndex) -> str:
    return digest(
        [
            {
                "id": row.id,
                "status": row.status,
                "parent": row.parent,
                "depends_on": sorted(row.depends_on),
                "column": row.path.parent.name,
            }
            for row in sorted(board.by_id.values(), key=lambda item: item.id)
        ]
    )


def dependency_revision(meta: WorkMeta, board: BoardIndex) -> str:
    return digest(
        [
            (dep_id, getattr(board.by_id.get(dep_id), "status", None))
            for dep_id in sorted(meta.depends_on)
        ]
    )


def review_revision(
    pending_review_ids: frozenset[str], review_refusal: str | None
) -> str:
    return digest({"pending": sorted(pending_review_ids), "refusal": review_refusal})


def provider_revision(selection_fingerprint: object, freshness: object) -> str | None:
    if not isinstance(freshness, dict) or freshness.get("stale") is not False:
        return None
    if not isinstance(selection_fingerprint, str):
        return None
    fetched_at = freshness.get("fetched_at")
    if not isinstance(fetched_at, (int, float)):
        return None
    return digest(
        {
            "selection_fingerprint": selection_fingerprint,
            "inventory_fetched_at": fetched_at,
        }
    )


def dispatch_base_revision(meta: WorkMeta, *, root: Path) -> str:
    from cascade.stacked_dispatch import read_feature_dispatch_selection

    return digest(
        {
            "owning_revision": owning_revision(meta, root=root),
            "parent": meta.parent,
            "depends_on": sorted(meta.depends_on),
            "selection": read_feature_dispatch_selection(meta.id, root=root),
        }
    )


def record_dispatch_attempt(
    feature_id: str,
    *,
    root: Path,
    outcome: Literal["refused", "started"],
    reason_code: str | None,
    detail: str | None,
    source_revisions: dict[str, str | None],
    source_states: dict[str, str] | None = None,
) -> dict[str, Any]:
    path = _state_dir(root) / "feature_dispatch_attempts.json"
    with _locked(path):
        payload = _read_json(path, {"version": 1, "sequence": 0, "features": {}})
        sequence = int(payload.get("sequence", 0)) + 1
        payload["sequence"] = sequence
        record = {
            "attempt_id": f"dispatch-{sequence:020d}",
            "sequence": sequence,
            "at": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome,
            "reason_code": reason_code,
            "detail": _safe_detail(detail),
            "source_revisions": {key: source_revisions.get(key) for key in SOURCES},
            "source_states": {
                key: (source_states or {}).get(key, "unknown") for key in SOURCES
            },
        }
        payload.setdefault("features", {})[feature_id] = record
        _atomic_json(path, payload)
        return record


def record_feature_dispatch_result(
    feature_id: str,
    *,
    root: Path,
    board: BoardIndex,
    meta: WorkMeta | None,
    result: DispatchResult,
    provider_preflight: object | None = None,
) -> dict[str, Any]:
    """Persist evidence for one real feature dispatch boundary.

    The caller supplies the board admitted under the lifecycle lock.  This
    function deliberately performs no provider discovery and no Git planning.
    """

    sources = dispatch_source_snapshot(
        feature_id,
        root=root,
        board=board,
        meta=meta,
        provider_preflight=provider_preflight,
    )
    return record_dispatch_attempt(
        feature_id,
        root=root,
        outcome="started" if result.ok else "refused",
        reason_code=None if result.ok else result.reason,
        detail=result.detail,
        source_revisions={key: sources[key]["revision"] for key in SOURCES},
        source_states={key: sources[key]["state"] for key in SOURCES},
    )


def dispatch_source_snapshot(
    feature_id: str,
    *,
    root: Path,
    board: BoardIndex,
    meta: WorkMeta | None,
    provider_preflight: object | None = None,
) -> dict[str, dict[str, str | None]]:
    """Return bounded source identities without discovery or expensive Git."""

    current_meta = meta or board.by_id.get(feature_id)
    board_source = {"state": "current", "revision": board_revision(board)}
    unknown = {"state": "unknown", "revision": None}
    if current_meta is None:
        return {
            key: (board_source if key == "board" else dict(unknown)) for key in SOURCES
        }

    approval_state, approval_revision = approval_evidence(current_meta, root=root)
    from cascade.comments.gate import blocking_threads_for_many, gate_refusal_reason
    from cascade.review import feature_review_views

    feature_ids = {row.id for row in board.by_id.values() if row.tier == "feature"}
    reviews = feature_review_views(feature_ids, root=root)
    pending_review_ids = frozenset(
        work_id
        for work_id, review in reviews.items()
        if review is not None
        and review.get("state") in {"preparing_review", "awaiting_review"}
    )
    thread = blocking_threads_for_many({feature_id}, root=root, board=board).get(
        feature_id
    )
    refusal = gate_refusal_reason(thread) if thread and thread.blocked else None
    provider_revision = _provider_preflight_revision(provider_preflight)
    from cascade.feature.readiness import _dispatch_base_unavailable

    dispatch_state = (
        "unknown"
        if _dispatch_base_unavailable(feature_id, current_meta, board, root=root)
        else "current"
    )
    return {
        "board": board_source,
        "approval": {"state": approval_state, "revision": approval_revision},
        "dependencies": {
            "state": "current",
            "revision": dependency_revision(current_meta, board),
        },
        "review": {
            "state": "current",
            "revision": review_revision(pending_review_ids, refusal),
        },
        "provider": {
            "state": "current" if provider_revision is not None else "unknown",
            "revision": provider_revision,
        },
        "dispatch_base": {
            "state": dispatch_state,
            "revision": dispatch_base_revision(current_meta, root=root),
        },
    }


def read_dispatch_attempt(feature_id: str, *, root: Path) -> dict[str, Any] | None:
    value = (
        _read_json(_state_dir(root) / "feature_dispatch_attempts.json", {})
        .get("features", {})
        .get(feature_id)
    )
    return dict(value) if isinstance(value, dict) else None


def source_history(
    attempt: dict[str, Any] | None, sources: dict[str, dict[str, str | None]]
) -> dict[str, Any] | None:
    if attempt is None:
        return None
    old = attempt.get("source_revisions")
    old_states = attempt.get("source_states")
    complete = isinstance(old, dict) and all(
        isinstance(old_states, dict)
        and old_states.get(key) == "current"
        and sources[key]["state"] == "current"
        and isinstance(sources[key]["revision"], str)
        and isinstance(old.get(key), str)
        for key in SOURCES
    )
    historical = bool(
        complete and any(old[key] != sources[key]["revision"] for key in SOURCES)
    )
    state = (
        "changed_sources"
        if historical
        else ("same_sources" if complete else "unverifiable")
    )
    return {
        "attempt_id": attempt.get("attempt_id"),
        "at": attempt.get("at"),
        "outcome": attempt.get("outcome"),
        "reason_code": attempt.get("reason_code"),
        "detail": attempt.get("detail"),
        "source_revisions": {
            key: old.get(key) if isinstance(old, dict) else None for key in SOURCES
        },
        "historical": historical,
        "history_state": state,
    }


def digest(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def _state_dir(root: Path) -> Path:
    return resolve_tracking_root(root) / ".cascade"


class _locked:
    def __init__(self, path: Path) -> None:
        self.path, self.handle = path.with_suffix(path.suffix + ".lock"), None

    def __enter__(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = self.path.open("a+", encoding="utf-8")
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_EX)

    def __exit__(self, *_args: object) -> None:
        fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        self.handle.close()


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default
    return value if isinstance(value, dict) else default


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temp = Path(raw)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _safe_detail(value: str | None) -> str | None:
    return " ".join(value.split())[:500] if value else None


def _provider_preflight_revision(value: object | None) -> str | None:
    if value is None:
        return None
    to_dict = getattr(value, "to_dict", None)
    if not callable(to_dict):
        return None
    projection = to_dict()
    if not isinstance(projection, dict):
        return None
    freshness = projection.get("inventory_freshness")
    if not isinstance(freshness, dict) or freshness.get("stale") is not False:
        return None
    return provider_revision(projection.get("selection_fingerprint"), freshness)
