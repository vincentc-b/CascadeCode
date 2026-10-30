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
from typing import TYPE_CHECKING, Any

from cascade.amendments.types import Amendment
from cascade.board.types import WorkDoc, WorkMeta
from cascade.comments.types import Comment
from cascade.feature.briefing import BriefingPack
from cascade.watchdog.types import DispatchResult, Event
from cascade.workspace.integration_worktree import IntegrationWorktree
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel, ReasoningCapability
from cascade.agent.providers import ProviderId, ProviderStatus
from cascade.review import OpenReview
from cascade.war_room.room_settings import RoomSettings
from cascade.workspace.types import FlightOverlap, FlightReport

if TYPE_CHECKING:
    from cascade.feature.readiness import FeatureReadiness

_COLUMN_FOLDERS = frozenset({"1_backlog", "2_active", "3_completed"})
_TIER_TO_VIEW_KEY = {"epic": "epics", "feature": "features", "task": "tasks"}
_OPEN_FEATURE_STATUS = frozenset({"backlog", "ready_to_plan"})


def _date_iso(value: date) -> str:
    return value.isoformat()


def _path_str(path: Path) -> str:
    return path.as_posix()


def work_meta_to_dict(
    meta: WorkMeta,
    *,
    root: Path | None = None,
    execution: dict[str, Any] | None = None,
    review: dict[str, object] | None = None,
    branch_sync: dict[str, Any] | None = None,
    sidecars_preloaded: bool = False,
) -> dict:
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
        if sidecars_preloaded:
            value["execution"] = execution
        else:
            from cascade.task.execution import execution_view

            value["execution"] = execution_view(meta.id, root=root)
        # Recovery stays attached to the original action; its contract, rather
        # than broad board state, authorizes any safe retry control.
        if meta.parent and meta.status in {"active", "blocked"}:
            from cascade.feature.recovery import recovery_status

            value["recovery"] = recovery_status(
                meta.id, feature_id=meta.parent, root=root
            )
        else:
            value["recovery"] = None
    if meta.tier == "feature":
        value["approved"] = meta.approved_at is not None
        if meta.approved_at is not None:
            value["approved_at"] = meta.approved_at.isoformat()
    if meta.tier == "epic":
        value["plan_approved"] = meta.plan_approved_at is not None
        if (
            root is not None
            and meta.plan_approved_at is None
            and meta.path.parent.name == "2_active"
        ):
            from cascade.epic.plan_readiness import (
                compute_epic_plan_readiness,
                epic_plan_readiness_to_dict,
            )

            readiness = compute_epic_plan_readiness(meta.id, root=root)
            if readiness is not None:
                value["plan_readiness"] = epic_plan_readiness_to_dict(readiness)
    if meta.tier == "feature" and root is not None:
        if sidecars_preloaded:
            value["review"] = review
        else:
            from cascade.review import feature_review_view

            value["review"] = feature_review_view(meta.id, root=root)
        from cascade.stacked_dispatch import feature_stacked_dispatch_view

        stacked = feature_stacked_dispatch_view(meta.id, root=root)
        if stacked is not None:
            value["stacked_dispatch"] = stacked
    if branch_sync is not None:
        value["branch_sync"] = branch_sync
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


def room_settings_to_dict(settings: RoomSettings) -> dict[str, object]:
    return {
        "graph_id": settings.graph_id,
        "stacked_pr_enabled": settings.stacked_pr_enabled,
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


def reasoning_capability_to_dict(capability: ReasoningCapability | None) -> dict[str, Any] | None:
    if capability is None:
        return None
    return {
        "default_level": capability.default_level,
        "override_levels": list(capability.override_levels),
        "default_only": not capability.supports_overrides,
    }


def inventory_freshness_to_dict(freshness: InventoryFreshness) -> dict[str, Any]:
    return {
        "from_cache": freshness.from_cache,
        "fetched_at": freshness.fetched_at,
        "expires_at": freshness.expires_at,
        "ttl_seconds": freshness.ttl_seconds,
    }


def provider_inventory_model_to_dict(model: DiscoveredModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "display_name": model.display_name,
        "reasoning": reasoning_capability_to_dict(model.reasoning),
    }


def provider_inventory_item_to_dict(item: ProviderInventoryItem) -> dict[str, Any]:
    return {
        "id": item.provider_id,
        "display_name": item.display_name,
        "models": [provider_inventory_model_to_dict(model) for model in item.models],
        "supports_flex_mode": item.supports_flex_mode,
    }


def provider_inventory_failure_to_dict(failure: ProviderInventoryFailure) -> dict[str, Any]:
    return {
        "id": failure.provider_id,
        "reason": failure.reason,
        "message": failure.message,
    }


def _brief_inventory_availability(result: ProviderInventoryResult) -> str:
    if result.providers:
        if result.failures:
            return "partial"
        return "available"
    return "unavailable"


def brief_provider_inventory_to_dict(
    result: ProviderInventoryResult,
    *,
    default_provider: ProviderId,
    force_refresh: bool = False,
    refresh_failed: bool = False,
    refresh_error: str | None = None,
) -> dict[str, Any]:
    """UI-facing brief provider inventory (feat_006 / task_006_001_003)."""

    available_ids = {item.provider_id for item in result.providers}
    selected_default = default_provider if default_provider in available_ids else None
    if selected_default is None and result.providers:
        selected_default = result.providers[0].provider_id

    return {
        "availability": _brief_inventory_availability(result),
        "loading": False,
        "default_provider": selected_default,
        "providers": [provider_inventory_item_to_dict(item) for item in result.providers],
        "failures": [provider_inventory_failure_to_dict(item) for item in result.failures],
        "freshness": inventory_freshness_to_dict(result.freshness),
        "refresh": {
            "forced": force_refresh,
            "failed": refresh_failed,
            "error": refresh_error,
        },
    }


def feature_readiness_to_dict(readiness: "FeatureReadiness") -> dict[str, Any]:
    return {"approved": readiness.approved, "blockers": list(readiness.blockers)}


def _backlog_open_feature(meta: WorkMeta) -> bool:
    return (
        meta.tier == "feature"
        and meta.status in _OPEN_FEATURE_STATUS
        and meta.path.parent.name == "1_backlog"
    )


def open_review_to_dict(review: OpenReview) -> dict[str, Any]:
    ctx = review.context
    return {
        "id": review.id,
        "url": review.url,
        "state": review.state,
        "context": {
            "feature_id": ctx.feature_id,
            "epic_id": ctx.epic_id,
            "feature_title": ctx.feature_title,
            "epic_title": ctx.epic_title,
        },
    }


def board_view_from_index(board, *, root: Path) -> dict:
    """Build feat_003 BoardView from a BoardIndex scan."""

    from cascade.review import feature_review_views
    from cascade.task.execution import execution_views
    from cascade.war_room.branch_sync import branch_sync_views

    metas = sorted(board.by_id.values(), key=lambda meta: meta.id)
    executions = execution_views(
        {meta.id for meta in metas if meta.tier == "task"}, root=root
    )
    reviews = feature_review_views(
        {meta.id for meta in metas if meta.tier == "feature"}, root=root
    )
    pending_review_ids = frozenset(
        feature_id
        for feature_id, review in reviews.items()
        if review is not None
        and review.get("state") in {"preparing_review", "awaiting_review"}
    )
    sync_views = branch_sync_views(metas, root=root)

    columns = ("1_backlog", "2_active", "3_completed")
    view: dict[str, dict[str, list]] = {
        "epics": {col: [] for col in columns},
        "features": {col: [] for col in columns},
        "tasks": {col: [] for col in columns},
    }
    for meta in metas:
        key = _TIER_TO_VIEW_KEY[meta.tier]
        folder = column_folder_for_meta(meta, root=root)
        item = work_meta_to_dict(
            meta,
            root=root,
            execution=executions.get(meta.id),
            review=reviews.get(meta.id),
            branch_sync=sync_views.get(meta.id),
            sidecars_preloaded=True,
        )
        if _backlog_open_feature(meta):
            from cascade.feature.readiness import compute_feature_readiness

            readiness = compute_feature_readiness(
                meta.id,
                root=root,
                board=board,
                pending_review_ids=pending_review_ids,
            )
            if readiness is not None:
                item["readiness"] = feature_readiness_to_dict(readiness)
        review = item.get("review")
        if (
            meta.tier == "feature"
            and isinstance(review, dict)
            and review.get("state") in {"preparing_review", "awaiting_review"}
        ):
            # The source plan is already in completed so the MR contains its
            # final location, but operationally the feature remains in flight.
            folder = "2_active"
        view[key][folder].append(item)

    from cascade.war_room.completed_epics import (
        bound_completed_epic_rows,
        completed_epics_board_settings,
    )

    settings = completed_epics_board_settings(root)
    limit = int(settings["completed_epic_display_limit"])
    view["epics"]["3_completed"] = bound_completed_epic_rows(
        view["epics"]["3_completed"],
        limit=limit,
    )
    view["board"] = settings
    return view
