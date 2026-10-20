"""JSON-friendly shapes for board API responses.

GET /api/doc/{id} returns::

    {
        "meta": { ... WorkMeta fields ... },
        "body": "<markdown body>",
        "sha": "<commit sha or null>"
    }

Dates are ISO-8601 strings; paths are repo-relative or absolute posix strings.
"""

from __future__ import annotations

from datetime import date, timezone
from pathlib import Path
from typing import Any

from cascade.amendments.types import Amendment
from cascade.board.types import WorkDoc, WorkMeta
from cascade.comments.types import Comment
from cascade.feature.briefing import BriefingPack
from cascade.watchdog.types import DispatchResult, Event
from cascade.workspace.integration_worktree import IntegrationWorktree
from cascade.agent.providers import ProviderId, ProviderStatus
from cascade.workspace.types import FlightOverlap, FlightReport

_COLUMN_FOLDERS = frozenset({"1_backlog", "2_active", "3_completed"})
_TIER_TO_VIEW_KEY = {"epic": "epics", "feature": "features", "task": "tasks"}


def _date_iso(value: date) -> str:
    return value.isoformat()


def _path_str(path: Path) -> str:
    return path.as_posix()


def work_meta_to_dict(meta: WorkMeta, *, root: Path | None = None) -> dict:
    value = {
        "id": meta.id,
        "title": meta.title,
        "tier": meta.tier,
        "status": meta.status,
        "parent": meta.parent,
        "children": list(meta.children),
        "depends_on": list(meta.depends_on),
        "owners": list(meta.owners),
        "skills": [_path_str(p) for p in meta.skills],
        "parent_rev": meta.parent_rev,
        "created": _date_iso(meta.created),
        "updated": _date_iso(meta.updated),
        "path": _path_str(meta.path),
    }
    if meta.tier == "task" and root is not None:
        from cascade.task.execution import execution_view

        value["execution"] = execution_view(meta.id, root=root)
    return value


def work_doc_to_dict(doc: WorkDoc) -> dict:
    return {
        "meta": work_meta_to_dict(doc.meta),
        "body": doc.body,
        "sha": doc.sha,
    }


def column_folder_for_meta(meta: WorkMeta, *, root: Path) -> str:
    """Folder name (1_backlog, 2_active, 3_completed) from the doc path."""

    folder = meta.path.parent.name
    if folder in _COLUMN_FOLDERS:
        return folder

    from cascade.board.errors import GitError
    from cascade.workspace.integration_worktree import git_root_for_path

    try:
        doc_root = git_root_for_path(meta.path)
    except GitError:
        raise ValueError(f"cannot infer column folder from path {meta.path}") from None
    rel = meta.path.resolve().relative_to(doc_root.resolve())
    parts = rel.parts
    if len(parts) >= 3 and parts[0] == "docs" and parts[2] in _COLUMN_FOLDERS:
        return parts[2]
    raise ValueError(f"cannot infer column folder from path {meta.path}")


def _payload_json(value: dict[str, Any]) -> dict[str, Any]:
    """JSON-encode dispatch event payloads (paths → posix strings)."""

    out: dict[str, Any] = {}
    for key, item in value.items():
        if isinstance(item, Path):
            out[key] = _path_str(item)
        elif isinstance(item, list):
            out[key] = [_path_str(v) if isinstance(v, Path) else v for v in item]
        else:
            out[key] = item
    return out


def event_to_dict(event: Event) -> dict:
    return {
        "type": event.type,
        "ts": event.ts.astimezone(timezone.utc).isoformat(),
        "payload": _payload_json(event.payload),
        "dest": event.dest,
    }


def dispatch_result_to_dict(result: DispatchResult) -> dict:
    return {
        "ok": result.ok,
        "reason": result.reason,
        "event": event_to_dict(result.event) if result.event is not None else None,
    }


def message_to_dict(message: dict) -> dict:
    """Chat sidecar line as JSON (id, graph_id, author, body, ts)."""

    return {
        "id": message["id"],
        "graph_id": message["graph_id"],
        "author": message["author"],
        "body": message["body"],
        "ts": message["ts"],
    }


def briefing_stub_to_dict(graph_id: str) -> dict:
    return {
        "graph_id": graph_id,
        "doc_excerpt": "stub until feat_005",
        "messages": [],
    }


def graph_message_to_dict(message: dict) -> dict:
    """One LangGraph transcript line for briefing / API responses."""

    out: dict[str, Any] = {
        "role": message.get("role"),
        "content": message.get("content", ""),
    }
    if message.get("id") is not None:
        out["id"] = message["id"]
    if message.get("ts") is not None:
        out["ts"] = message["ts"]
    if message.get("name") is not None:
        out["name"] = message["name"]
    return out


def comment_to_dict(comment: Comment) -> dict:
    return comment.to_dict()


def briefing_pack_to_dict(pack: BriefingPack) -> dict:
    parent = (
        work_doc_to_dict(pack.parent_constraints)
        if pack.parent_constraints is not None
        else None
    )
    return {
        "doc": work_doc_to_dict(pack.doc),
        "decision_log": pack.decision_log,
        "open_comments": [comment_to_dict(c) for c in pack.open_comments],
        "parent_constraints": parent,
        "recent_messages": [graph_message_to_dict(m) for m in pack.recent_messages],
    }


def _rationale_summary(text: str, *, limit: int = 160) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return collapsed[: limit - 1].rstrip() + "…"


def amendment_summary_to_dict(record: Amendment) -> dict[str, Any]:
    return {
        "amd_id": record.id,
        "feature_id": record.feature_id,
        "section": record.section,
        "diff_path": _path_str(record.diff_path),
        "rationale_summary": _rationale_summary(record.rationale),
        "state": record.state,
    }


def integration_worktree_to_dict(entry: IntegrationWorktree, *, root: Path) -> dict[str, str]:
    rel_path = entry.path
    try:
        rel_path = entry.path.resolve().relative_to(root.resolve())
    except ValueError:
        pass
    return {
        "kind": entry.kind,
        "work_id": entry.work_id,
        "branch": entry.branch,
        "path": _path_str(rel_path),
        "base_sha": entry.base_sha,
    }


def flight_overlap_to_dict(record: FlightOverlap) -> dict[str, list[str]]:
    return {
        "paths": list(record.paths),
        "work_ids": list(record.work_ids),
    }


def flight_report_to_dict(report: FlightReport, *, root: Path) -> dict[str, Any]:
    return {
        "epics": [integration_worktree_to_dict(e, root=root) for e in report.epics],
        "features": [integration_worktree_to_dict(e, root=root) for e in report.features],
        "tasks": [integration_worktree_to_dict(e, root=root) for e in report.tasks],
        "changed_paths": {wid: list(paths) for wid, paths in sorted(report.changed_paths.items())},
        "overlaps": [flight_overlap_to_dict(o) for o in report.overlaps],
    }


def provider_status_to_dict(status: ProviderStatus) -> dict[str, Any]:
    return {
        "id": status.id,
        "installed": status.installed,
        "authenticated": status.authenticated,
        "auth_source": status.auth_source,
    }


def providers_view_to_dict(
    default: ProviderId, statuses: list[ProviderStatus]
) -> dict[str, Any]:
    return {
        "default": default,
        "providers": [provider_status_to_dict(item) for item in statuses],
    }


def board_view_from_index(board, *, root: Path) -> dict:
    """Build feat_003 BoardView from a BoardIndex scan."""

    columns = ("1_backlog", "2_active", "3_completed")
    view: dict[str, dict[str, list]] = {
        "epics": {col: [] for col in columns},
        "features": {col: [] for col in columns},
        "tasks": {col: [] for col in columns},
    }
    for meta in sorted(board.by_id.values(), key=lambda m: m.id):
        key = _TIER_TO_VIEW_KEY[meta.tier]
        folder = column_folder_for_meta(meta, root=root)
        view[key][folder].append(work_meta_to_dict(meta, root=root))
    return view
