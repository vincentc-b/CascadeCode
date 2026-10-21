"""Convert JSON-friendly work doc shapes to in-memory types."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.board.types import WorkDoc, WorkMeta, WorkId


def work_meta_from_dict(raw: Mapping[str, Any]) -> WorkMeta:
    """Parse a meta object (e.g. from tool JSON) into ``WorkMeta``."""

    path_val = raw.get("path")
    if path_val is None:
        raise ValueError("doc.meta.path is required")
    skills_raw = raw.get("skills") or []
    skills = [Path(p) for p in skills_raw]
    created = _parse_date(raw.get("created"), field="created")
    updated = _parse_date(raw.get("updated"), field="updated")
    return WorkMeta(
        id=str(raw["id"]),
        title=str(raw.get("title") or ""),
        tier=raw["tier"],  # type: ignore[arg-type]
        status=raw["status"],  # type: ignore[arg-type]
        parent=raw.get("parent"),
        children=list(raw.get("children") or []),
        depends_on=list(raw.get("depends_on") or []),
        owners=list(raw.get("owners") or []),
        skills=skills,
        parent_rev=raw.get("parent_rev"),
        created=created,
        updated=updated,
        path=Path(str(path_val)),
        model=raw.get("model"),
        models=dict(raw["models"]) if raw.get("models") else None,
        provider=raw.get("provider"),  # type: ignore[arg-type]
        integration_branch=raw.get("integration_branch"),
        integration_worktree=raw.get("integration_worktree"),
        approved_at=_parse_optional_datetime(raw.get("approved_at")),
        plan_approved_at=_parse_optional_datetime(raw.get("plan_approved_at")),
    )


def work_doc_from_dict(
    raw: Mapping[str, Any] | WorkDoc,
    *,
    root: Path,
    work_id_hint: WorkId | None = None,
) -> WorkDoc:
    """Coerce agent/MCP JSON into ``WorkDoc``.

    When ``meta.id`` is present, reload canonical ``meta`` (path, column, sha)
    from ``read_doc`` so commits land in the owning integration worktree.
    """

    if isinstance(raw, WorkDoc):
        return raw
    if not isinstance(raw, Mapping):
        raise TypeError(f"doc must be WorkDoc or mapping, got {type(raw).__name__}")
    body = raw.get("body")
    if body is None:
        raise ValueError("doc.body is required")
    meta_raw = raw.get("meta")
    work_id: WorkId | None = work_id_hint
    if isinstance(meta_raw, Mapping):
        wid = meta_raw.get("id")
        if isinstance(wid, str) and wid:
            work_id = wid
    if work_id:
        try:
            base = read_doc(work_id, root=root)
        except NotFound:
            base = None
        if base is not None:
            sha = raw.get("sha")
            return WorkDoc(meta=base.meta, body=str(body), sha=sha if sha is not None else base.sha)
    if not isinstance(meta_raw, Mapping):
        raise ValueError("doc.meta is required when work id cannot be resolved")
    meta = work_meta_from_dict(meta_raw)
    return WorkDoc(meta=meta, body=str(body), sha=raw.get("sha"))


def _parse_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        text = value.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    raise ValueError("approved_at must be an ISO datetime string or null")


def _parse_date(value: Any, *, field: str) -> date:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value[:10])
    raise ValueError(f"doc.meta.{field} must be an ISO date string")
