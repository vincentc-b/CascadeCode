"""Revision evidence for read-only feature readiness projections."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_tracking_root
from cascade.board.errors import BoardError
from cascade.board.store import read_doc
from cascade.board.types import BoardIndex, WorkDoc, WorkMeta
from cascade.watchdog.types import DispatchResult

SOURCES = ("board", "approval", "dependencies", "review", "provider", "dispatch_base")


# These are the named mutable planning and handoff sections of Feature documents.
# Everything else (including unknown sections) remains part of the approved scope.
_PLANNING_SECTIONS = {
    "data structures",
    "api contracts",
    "logic flow",
    "task breakdown",
    "risks & upward questions",
    "decision log",
    "candidate repair and delivery handoff",
}


def _scope_body(body: str) -> str:
    """Exclude delegated planning details, not scope or acceptance requirements."""
    retained: list[str] = []
    include = True
    fence: tuple[str, int] | None = None
    for line in body.splitlines():
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            chars, suffix = marker.groups()
            if fence is None:
                fence = (chars[0], len(chars))
            elif chars[0] == fence[0] and len(chars) >= fence[1] and not suffix.strip():
                fence = None
            if include:
                retained.append(line)
            continue
        if fence is None:
            heading = re.match(r"^ {0,3}##[ \t]+(.+?)\s*#*\s*$", line)
            if heading:
                include = heading.group(1).strip().casefold() not in _PLANNING_SECTIONS
        if include:
            retained.append(line)
    return "\n".join(retained).strip()


def _revision(doc: WorkDoc, *, scope: bool = False) -> str:
    meta = doc.meta
    value = {
        "body": _scope_body(doc.body) if scope else doc.body,
        "parent": meta.parent,
        "depends_on": sorted(meta.depends_on),
        "provider": meta.provider,
        "model": meta.model,
        "models": meta.models,
        "reasoning": meta.reasoning,
        "flex_mode": meta.flex_mode,
    }
    if scope:
        value["title"] = meta.title
    return digest(value)


def owning_revision(meta: WorkMeta, *, root: Path) -> str | None:
    try:
        return _revision(read_doc(meta.id, root=root))
    except (OSError, ValueError, KeyError, BoardError):
        return None


def _approval_timestamp(meta: WorkMeta) -> str | None:
    return meta.approved_at.astimezone(timezone.utc).isoformat() if meta.approved_at else None


def write_approval_evidence(meta: WorkMeta, *, root: Path) -> None:
    try:
        doc = read_doc(meta.id, root=root)
    except (OSError, ValueError, KeyError, BoardError):
        return
    from cascade.epic.change_dispositions import is_corrective_feature

    record = {
        "approved_at": _approval_timestamp(doc.meta),
        "revision": _revision(doc),
    }
    if is_corrective_feature(meta.id, root=root):
        record["approval_mode"] = "exact"
    else:
        record["approval_mode"] = "scope"
        record["scope_revision"] = _revision(doc, scope=True)
    path = _state_dir(root) / "feature_approvals.json"
    with _locked(path):
        payload = _read_json(path, {"version": 1, "features": {}})
        payload.setdefault("features", {})[meta.id] = record
        _atomic_json(path, payload)


def approval_evidence(
    meta: WorkMeta, *, root: Path
) -> tuple[Literal["current", "stale", "unknown"], str | None]:
    try:
        doc = read_doc(meta.id, root=root)
    except (OSError, ValueError, KeyError, BoardError):
        return "unknown", None
    current = _revision(doc)
    if meta.approved_at is None:
        return "current", current
    record = (
        _read_json(_state_dir(root) / "feature_approvals.json", {})
        .get("features", {})
        .get(meta.id)
    )
    if (
        not isinstance(record, dict)
        or not isinstance(record.get("revision"), str)
        or record.get("approved_at") != _approval_timestamp(doc.meta)
    ):
        return "unknown", current
    if record.get("approval_mode") == "scope":
        current = _revision(doc, scope=True)
        accepted = record.get("scope_revision")
        if not isinstance(accepted, str):
            return "unknown", current
    else:
        accepted = record["revision"]
    return ("current" if accepted == current else "stale"), current


def migrate_legacy_approvals(board: BoardIndex, *, root: Path) -> None:
    """Upgrade old exact records only from a document proven to be approved.

    Run at the supervisor action boundary, never on a board/API read. Preserve
    the original timestamp and full revision; no new authorization is minted.
    """
    path = _state_dir(root) / "feature_approvals.json"
    if not path.is_file():
        return
    from cascade.epic.change_dispositions import is_corrective_feature

    with _locked(path):
        payload = _read_json(path, {})
        records = payload.get("features", {})
        if not isinstance(records, dict):
            return
        changed = False
        for meta in board.by_id.values():
            if (
                meta.tier != "feature" or meta.approved_at is None
                or meta.status not in {"backlog", "ready_to_plan"}
                or meta.path.parent.name != "1_backlog"
            ):
                continue
            record = records.get(meta.id)
            if (
                not isinstance(record, dict) or "approval_mode" in record
                or record.get("approved_at") != _approval_timestamp(meta)
                or not isinstance(record.get("revision"), str)
            ):
                continue
            if is_corrective_feature(meta.id, root=root):
                record["approval_mode"] = "exact"
                changed = True
                continue
            try:
                doc = read_doc(meta.id, root=root)
            except (OSError, ValueError, KeyError, BoardError):
                continue
            if _approval_timestamp(doc.meta) != record["approved_at"]:
                continue
            current = _revision(doc)
            if record.get("migration_checked_revision") == current:
                continue
            approved = doc if current == record["revision"] else _historical_approved_doc(doc, record["revision"])
            if approved is None:
                record["migration_checked_revision"] = current
            else:
                record["approval_mode"] = "scope"
                record["scope_revision"] = _revision(approved, scope=True)
                record.pop("migration_checked_revision", None)
            changed = True
        if changed:
            _atomic_json(path, payload)


def _historical_approved_doc(doc: WorkDoc, revision: str) -> WorkDoc | None:
    """Bounded owning-path history search; only an exact legacy digest is proof."""
    from cascade.board.parse import parse_text
    from cascade.workspace.integration_worktree import git_root_for_path

    try:
        checkout = git_root_for_path(doc.meta.path)
        rel = doc.meta.path.resolve().relative_to(checkout.resolve()).as_posix()
        history = subprocess.run(
            ["git", "log", "-n", "32", "--format=%H", "--", rel],
            cwd=checkout, capture_output=True, text=True, timeout=5, check=True,
        ).stdout.splitlines()
        for commit in history:
            raw = subprocess.run(
                ["git", "show", f"{commit}:{rel}"], cwd=checkout,
                capture_output=True, text=True, timeout=5, check=True,
            ).stdout
            old = parse_text(raw, doc.meta.path)
            if (
                old.meta.id == doc.meta.id
                and _approval_timestamp(old.meta) == _approval_timestamp(doc.meta)
                and _revision(old) == revision
            ):
                return old
    except (OSError, ValueError, BoardError, subprocess.SubprocessError):
        pass
    return None


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
        and review.get("state") in {"preparing_review", "awaiting_review", "awaiting_integration", "awaiting_closeout"}
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
