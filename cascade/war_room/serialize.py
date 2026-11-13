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

from datetime import date, datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cascade.amendments.types import Amendment
from cascade.board.types import BoardIndex, WorkDoc, WorkMeta
from cascade.comments.types import Comment
from cascade.feature.briefing import BriefingPack
from cascade.watchdog.types import DispatchResult, Event
from cascade.workspace.integration_worktree import IntegrationWorktree
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryFailure,
    ProviderInventoryItem,
    ProviderInventoryResult,
    get_provider_inventory,
    project_inventory_freshness,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderCompatibilityEvidence,
    ReasoningCapability,
)
from cascade.agent.providers import ProviderId, ProviderStatus
from cascade.review import EpicReviewSnapshot, OpenReview, epic_close_documents_staged
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
    recovery_incident: dict[str, object] | None = None,
    sidecars_preloaded: bool = False,
    board_snapshot: BoardIndex | None = None,
    delivery_actions: dict[str, dict] | None = None,
    pending_deliveries: set[str] | None = None,
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
        "monitoring_blockers": [
            {
                "child_id": item.child_id,
                "reason": item.reason,
                "incident_id": item.incident_id,
                "blocked_supervisor": item.blocked_supervisor,
            }
            for item in meta.monitoring_blockers
        ],
    }
    if meta.tier == "task" and root is not None:
        if sidecars_preloaded:
            value["execution"] = execution
        else:
            from cascade.task.execution import execution_view

            value["execution"] = execution_view(meta.id, root=root)
        from cascade.task_rollup import pending_task_merges
        from cascade.task.action_recovery import load_action

        action_id = f"{meta.id}:queued_merge"
        delivery_action = (
            delivery_actions.get(action_id)
            if delivery_actions is not None
            else load_action(action_id, root=root)
        )
        pending = (
            pending_deliveries
            if pending_deliveries is not None
            else pending_task_merges(root)
        )
        validation = ((delivery_action or {}).get("metadata") or {}).get(
            "final_validation"
        )
        value["delivery_review"] = {
            "kind": "local_task_delivery",
            "owner": meta.id,
            "supervisor": meta.parent,
            "source_branch": f"task/{meta.id}",
            "target_branch": f"feat/{meta.parent}",
            "validation": validation,
            "queued": meta.id in pending,
            "action": delivery_action,
        }
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
        if root is not None:
            from cascade.review import epic_review_snapshot
            from cascade.epic.dependency_status import project_dependency_status

            snapshot = epic_review_snapshot(meta.id, root=root)
            value["implementation_review"] = (
                epic_review_snapshot_to_dict(snapshot) if snapshot is not None else None
            )
            if meta.path.parent.name == "2_active":
                # Software setup approvals are separate from work-item dependency status.
                value["software_dependency_status"] = project_dependency_status(
                    meta.id, root=root, board_snapshot=board_snapshot
                )
        if (
            root is not None
            and meta.plan_approved_at is None
            and meta.path.parent.name == "2_active"
        ):
            from cascade.epic.plan_readiness import (
                compute_epic_plan_readiness,
                project_epic_plan_readiness,
                epic_plan_readiness_to_dict,
            )

            readiness = (
                project_epic_plan_readiness(meta.id, root=root, board=board_snapshot)
                if board_snapshot is not None
                else compute_epic_plan_readiness(meta.id, root=root)
            )
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
    value["recovery_incident"] = recovery_incident
    return value


def _provider_recovery_view(
    meta: WorkMeta,
    *,
    root: Path,
    return_to_backlog: dict[str, object] | None = None,
    inventory: ProviderInventoryResult | None = None,
    compatibility_cache: dict[str, ProviderCompatibilityEvidence] | None = None,
) -> dict[str, object] | None:
    """Attach the safe, server-computed provider recovery projection to a row."""

    from cascade.agent.execution_preflight import provider_blocker
    from cascade.epic.lifecycle_gate import lifecycle_gate
    from cascade.provider_recovery_state import provider_recovery_state

    blocker = provider_blocker(meta.id, root=root)
    continuation = None
    if blocker and isinstance(blocker.get("failed_action"), dict):
        from cascade.provider_recovery_command import continue_without_flex_eligibility

        continuation = continue_without_flex_eligibility(
            meta.id,
            root=root,
            inventory=inventory,
            compatibility_cache=compatibility_cache,
        ).to_dict()

    recovery = provider_recovery_state(
        blocker,
        tier=meta.tier,
        status=meta.status,
        turn_stoppable=lifecycle_gate().turn_stoppable(meta.id),
        return_to_backlog=return_to_backlog,
        continue_without_flex=continuation,
    )
    if recovery is None:
        return None
    # These are the same persisted selection controls used by the command
    # boundary.  They deliberately exclude credentials and provider errors.
    recovery["selection"] = {
        "provider": meta.provider,
        "models": dict(meta.models or {}),
        "reasoning": dict(meta.reasoning or {}),
        "flex_mode": meta.flex_mode,
    }
    # The live readiness projection can change after an inventory refresh.
    # Keep the failed execution snapshot available for the recovery dialog.
    failed_preflight = blocker.get("failed_preflight")
    if isinstance(failed_preflight, dict):
        recovery["failed_diagnostics"] = dict(failed_preflight)
    elif isinstance(blocker.get("checks"), list):
        # Older execution blockers still retained the ordered role checks.
        recovery["failed_diagnostics"] = {
            "work_id": blocker.get("work_id"),
            "action": blocker.get("action"),
            "selection_fingerprint": blocker.get("selection_fingerprint"),
            "inventory_freshness": blocker.get("inventory_freshness"),
            "classification": blocker.get("classification"),
            "reason_code": blocker.get("reason_code"),
            "message": blocker.get("reason"),
            "checks": blocker["checks"],
        }
    failed_action = blocker.get("failed_action")
    if isinstance(failed_action, dict):
        recovery["failed_action"] = dict(failed_action)
    return recovery


def _provider_readiness_actions(
    readiness: dict[str, object],
    *,
    recovery: dict[str, object] | None,
) -> dict[str, dict[str, object]]:
    """Project read-only controls without granting command authority."""

    remedies = {
        remedy for remedy in readiness.get("remedies", ()) if isinstance(remedy, str)
    }
    freshness = readiness.get("inventory_freshness")
    stale = isinstance(freshness, dict) and freshness.get("stale") is True
    transient = readiness.get("outcome") == "transient"
    recovery_actions = recovery.get("actions") if isinstance(recovery, dict) else None
    recovery_actions = recovery_actions if isinstance(recovery_actions, dict) else {}

    def recovery_action(name: str) -> dict[str, object]:
        value = recovery_actions.get(name)
        if isinstance(value, dict):
            return dict(value)
        return {
            "eligible": False,
            "reason_code": "no_provider_blocker",
            "reason": "No failed provider action is available for recovery.",
        }

    refresh_eligible = stale or transient or "refresh_and_retry" in remedies
    return {
        "refresh": (
            {"eligible": True}
            if refresh_eligible
            else {
                "eligible": False,
                "reason_code": "inventory_current",
                "reason": "Provider inventory is current and no transient failure requires refresh.",
            }
        ),
        "retry": recovery_action("retry"),
        "provider_setup": (
            {"eligible": True}
            if "open_provider_setup" in remedies
            else recovery_action("provider_setup")
        ),
        "change_provider": (
            {"eligible": True}
            if remedies.intersection({"choose_configuration", "migrate_or_default"})
            else recovery_action("change_provider")
        ),
        "continue_without_flex": recovery_action("continue_without_flex"),
    }


def _unknown_provider_inventory() -> ProviderInventoryResult:
    """Fail closed when the bounded inventory snapshot cannot be acquired."""

    return ProviderInventoryResult(
        providers=(),
        failures=(),
        freshness=InventoryFreshness(
            from_cache=False,
            fetched_at=None,
            expires_at=None,
            ttl_seconds=0.0,
        ),
    )


def _provider_readiness_view(
    meta: WorkMeta,
    *,
    root: Path,
    inventory: ProviderInventoryResult,
    recovery: dict[str, object] | None,
    compatibility_cache: dict[str, ProviderCompatibilityEvidence] | None = None,
) -> dict[str, object]:
    """Evaluate one row using the board's single normalized inventory snapshot."""

    from cascade.agent.selection_preflight import evaluate_work_selection

    result = evaluate_work_selection(
        meta,
        root=root,
        inventory=inventory,
        action="readiness",
        compatibility_cache=compatibility_cache,
    ).result.to_dict()
    result["actions"] = _provider_readiness_actions(result, recovery=recovery)
    return result


def work_doc_to_dict(doc: WorkDoc, *, root: Path | None = None) -> dict:
    incident = None
    if root is not None:
        from cascade.war_room.recovery_incident import recovery_incidents_by_work_id

        incident = recovery_incidents_by_work_id(root=root).get(doc.meta.id)
    return {
        "meta": work_meta_to_dict(doc.meta, root=root, recovery_incident=incident),
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
    payload = {
        "ok": result.ok,
        "reason": result.reason,
        "event": event_to_dict(result.event) if result.event is not None else None,
    }
    if result.preflight is not None:
        # Keep the stable machine reason for compatibility, but lead consumers
        # with the evaluator's safe operator-facing explanation.  The complete
        # batch remains available for role-by-role diagnostics.
        preflight = result.preflight.to_dict()
        message = getattr(result.preflight, "message", None)
        if not isinstance(message, str) or not message:
            candidate = preflight.get("message")
            message = (
                candidate
                if isinstance(candidate, str) and candidate
                else "Provider configuration blocked this action."
            )
        payload["code"] = result.reason
        payload["error"] = message
        payload["message"] = message
        payload["preflight"] = preflight
    if result.selections is not None:
        payload["selections"] = result.selections.to_dict()
    if result.detail is not None:
        payload["code"] = result.reason
        payload["error"] = result.detail
        payload["message"] = result.detail
    return payload


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


def integration_worktree_to_dict(
    entry: IntegrationWorktree, *, root: Path
) -> dict[str, str]:
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
        "features": [
            integration_worktree_to_dict(e, root=root) for e in report.features
        ],
        "tasks": [integration_worktree_to_dict(e, root=root) for e in report.tasks],
        "changed_paths": {
            wid: list(paths) for wid, paths in sorted(report.changed_paths.items())
        },
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


def reasoning_capability_to_dict(
    capability: ReasoningCapability | None,
) -> dict[str, Any] | None:
    if capability is None:
        return None
    return {
        "default_level": capability.default_level,
        "override_levels": list(capability.override_levels),
        "default_only": not capability.supports_overrides,
    }


def inventory_freshness_to_dict(freshness: InventoryFreshness) -> dict[str, Any]:
    freshness = project_inventory_freshness(freshness)
    return {
        "from_cache": freshness.from_cache,
        "fetched_at": freshness.fetched_at,
        "expires_at": freshness.expires_at,
        "ttl_seconds": freshness.ttl_seconds,
        "age_seconds": freshness.age_seconds,
        "stale": freshness.stale,
    }


def provider_inventory_model_to_dict(model: DiscoveredModel) -> dict[str, Any]:
    return {
        "id": model.id,
        "display_name": model.display_name,
        "reasoning": reasoning_capability_to_dict(model.reasoning),
        "supports_flex_mode": model.supports_flex_mode,
    }


def provider_inventory_item_to_dict(item: ProviderInventoryItem) -> dict[str, Any]:
    return {
        "id": item.provider_id,
        "display_name": item.display_name,
        "models": [provider_inventory_model_to_dict(model) for model in item.models],
        "supports_flex_mode": item.supports_flex_mode,
    }


def provider_inventory_failure_to_dict(
    failure: ProviderInventoryFailure,
) -> dict[str, Any]:
    return {
        "id": failure.provider_id,
        "reason": failure.reason,
        "message": failure.message,
        "failure_kind": failure.failure_kind,
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
        "providers": [
            provider_inventory_item_to_dict(item) for item in result.providers
        ],
        "failures": [
            provider_inventory_failure_to_dict(item) for item in result.failures
        ],
        "freshness": inventory_freshness_to_dict(result.freshness),
        "refresh": {
            "forced": force_refresh,
            "failed": refresh_failed,
            "error": refresh_error,
        },
    }


_REASON_SOURCES = {
    "not_approved": ("board", "approval"),
    "approval_status_unavailable": ("board", "approval"),
    "dependency_unmet": ("board", "dependencies"),
    "dependency_status_unavailable": ("board", "dependencies"),
    "sibling_active_execution": ("board",),
    "feature_awaiting_merge": ("board", "review"),
    "review_threads_blocking": ("board", "review"),
    "epic_inactive": ("board",),
    "parent_cancellation_pending": ("board",),
    "not_in_backlog": ("board",),
    "dispatch_base_unavailable": ("board", "review", "dispatch_base"),
}


def feature_readiness_to_dict(
    readiness: "FeatureReadiness",
    *,
    meta: WorkMeta | None = None,
    board: BoardIndex | None = None,
    root: Path | None = None,
    approval_state: str = "unknown",
    approval_revision: str | None = None,
    provider_readiness: dict[str, object] | None = None,
    pending_review_ids: frozenset[str] = frozenset(),
    review_refusal: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "approved": readiness.approved,
        "blockers": list(readiness.blockers),
    }
    if readiness.explanation is None or meta is None or board is None or root is None:
        return result
    from cascade.feature.readiness_evidence import (
        SOURCES,
        board_revision,
        dependency_revision,
        dispatch_base_revision,
        provider_revision,
        read_dispatch_attempt,
        review_revision,
        source_history,
    )

    reasons = [
        {
            "code": reason.code,
            "kind": reason.kind,
            "message": reason.message,
            "actor": reason.actor,
            "next_action": reason.next_action,
            "affected_work_ids": list(reason.affected_work_ids),
            "links": _readiness_reason_links(
                reason.code, reason.affected_work_ids, board
            ),
            "source_ids": list(_REASON_SOURCES.get(reason.code, ("board",))),
        }
        for reason in readiness.explanation.reasons
    ]
    freshness = (provider_readiness or {}).get("inventory_freshness")
    provider_stale = (
        not isinstance(freshness, dict) or freshness.get("stale") is not False
    )
    provider_outcome = (provider_readiness or {}).get("outcome")
    if provider_stale or provider_outcome in {None, "transient"}:
        reasons.append(
            {
                "code": "provider_evidence_unavailable",
                "kind": "unknown",
                "message": "Provider compatibility evidence is unavailable or stale.",
                "actor": "system",
                "next_action": None,
                "affected_work_ids": [meta.id],
                "links": [],
                "source_ids": ["board", "provider"],
            }
        )
    elif provider_outcome != "supported":
        reasons.append(
            {
                "code": "provider_configuration_unsupported",
                "kind": "human_action",
                "message": "The selected provider configuration must be corrected.",
                "actor": "human",
                "next_action": "Choose a supported provider configuration.",
                "affected_work_ids": [meta.id],
                "links": [],
                "source_ids": ["board", "provider"],
            }
        )
    priority = {"human_action": 0, "unknown": 1, "work_wait": 2, "system_wait": 3}
    reasons.sort(
        key=lambda row: (
            priority.get(str(row["kind"]), 4),
            str(row["code"]),
            tuple(row["affected_work_ids"]),
        )
    )
    provider_identity = provider_revision(
        (provider_readiness or {}).get("selection_fingerprint"), freshness
    )
    sources: dict[str, dict[str, str | None]] = {
        "board": {"state": "current", "revision": board_revision(board)},
        "approval": {"state": approval_state, "revision": approval_revision},
        "dependencies": {
            "state": "unknown"
            if any(r["code"] == "dependency_status_unavailable" for r in reasons)
            else "current",
            "revision": dependency_revision(meta, board),
        },
        "review": {
            "state": "current",
            "revision": review_revision(pending_review_ids, review_refusal),
        },
        "provider": {
            "state": "stale" if provider_stale else "current",
            "revision": provider_identity,
        },
        "dispatch_base": {
            "state": "unknown"
            if any(r["code"] == "dispatch_base_unavailable" for r in reasons)
            else "current",
            "revision": dispatch_base_revision(meta, root=root),
        },
    }
    primary = reasons[0] if reasons else None
    summary = (
        "ready_awaiting_dispatch"
        if primary is None
        else {
            "human_action": "needs_action",
            "unknown": "unavailable",
            "work_wait": "waiting",
            "system_wait": "waiting",
        }[str(primary["kind"])]
    )
    result["explanation"] = {
        "version": 1,
        "summary": summary,
        "primary_reason_code": primary["code"] if primary else None,
        "reasons": reasons,
        "satisfied": [
            {
                "code": item.code,
                "message": item.message,
                "affected_work_ids": list(item.affected_work_ids),
            }
            for item in readiness.explanation.satisfied
        ],
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "sources": {key: sources[key] for key in SOURCES},
        "last_dispatch_attempt": source_history(
            read_dispatch_attempt(meta.id, root=root), sources
        ),
    }
    return result


def _readiness_reason_links(
    code: str, affected_work_ids: tuple[str, ...], board: BoardIndex
) -> list[dict[str, str]]:
    """Use only the existing local plan route; missing work has no dead link."""

    linkable = {
        "not_approved",
        "approval_status_unavailable",
        "dependency_unmet",
        "sibling_active_execution",
        "feature_awaiting_merge",
        "review_threads_blocking",
        "epic_inactive",
        "parent_cancellation_pending",
    }
    if code not in linkable:
        return []
    return [
        {"label": f"Open {work_id} plan", "href": f"/plan/{work_id}"}
        for work_id in affected_work_ids
        if work_id in board.by_id
    ]


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


def epic_review_snapshot_to_dict(snapshot: EpicReviewSnapshot) -> dict[str, Any]:
    """Serialize the canonical epic implementation-review state unchanged."""

    blocker = snapshot.blocker
    return {
        "close_stage": snapshot.stage,
        "review_url": snapshot.review_url,
        "source_branch": snapshot.source_branch,
        "target_branch": snapshot.target_branch,
        "forge_state": snapshot.forge_state,
        "blocker": (
            {
                "code": blocker.code,
                "message": blocker.message,
                "retryable": blocker.retryable,
            }
            if blocker is not None
            else None
        ),
    }


def board_view_from_index(board, *, root: Path) -> dict:
    """Build feat_003 BoardView from a BoardIndex scan."""

    from cascade.review import feature_review_views
    from cascade.task.execution import execution_views
    from cascade.war_room.branch_sync import branch_sync_views
    from cascade.war_room.recovery_incident import recovery_incidents_by_work_id

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
    backlog_feature_ids = {meta.id for meta in metas if _backlog_open_feature(meta)}
    from cascade.comments.gate import blocking_threads_for_many, gate_refusal_reason

    gate_results = blocking_threads_for_many(
        backlog_feature_ids, root=root, board=board
    )
    review_refusals = {
        feature_id: gate_refusal_reason(result) if result.blocked else None
        for feature_id, result in gate_results.items()
    }
    sync_views = branch_sync_views(metas, root=root)
    from cascade.task.action_recovery import recovery_actions
    from cascade.task_rollup import pending_task_merges

    actions = recovery_actions(root=root)
    incidents = recovery_incidents_by_work_id(root=root, actions=actions)
    delivery_actions = {action["action_id"]: action for action in actions}
    staged_epics = epic_close_documents_staged(metas, root=root)
    pending_deliveries = pending_task_merges(root)

    # A board render is one projection boundary.  Acquire the bounded cache
    # once and reuse that immutable evidence for every backlog/active row so a
    # large board cannot trigger provider discovery per item (or mix snapshots
    # within one response).
    if metas:
        try:
            provider_inventory = get_provider_inventory()
        except Exception:
            provider_inventory = _unknown_provider_inventory()
    else:
        provider_inventory = None

    columns = ("1_backlog", "2_active", "3_completed")
    view: dict[str, dict[str, list]] = {
        "epics": {col: [] for col in columns},
        "features": {col: [] for col in columns},
        "tasks": {col: [] for col in columns},
    }
    compatibility_cache: dict[str, ProviderCompatibilityEvidence] = {}
    for meta in metas:
        feature_readiness = None
        approval_state = "unknown"
        approval_revision = None
        key = _TIER_TO_VIEW_KEY[meta.tier]
        folder = column_folder_for_meta(meta, root=root)
        item = work_meta_to_dict(
            meta,
            root=root,
            execution=executions.get(meta.id),
            review=reviews.get(meta.id),
            branch_sync=sync_views.get(meta.id),
            recovery_incident=incidents.get(meta.id),
            sidecars_preloaded=True,
            board_snapshot=board,
            delivery_actions=delivery_actions,
            pending_deliveries=pending_deliveries,
        )
        if meta.tier in {"epic", "feature"}:
            readiness = item.get("plan_readiness")
            if isinstance(readiness, dict) and isinstance(
                readiness.get("dependency_status"), dict
            ):
                # Use the exact action-boundary projection already shown by
                # readiness so two live labels cannot disagree.
                item["dependency_status"] = readiness["dependency_status"]
            else:
                # Other rooms project this board snapshot, never chat prose.
                # The normal board poll therefore clears completed blockers.
                from cascade.dependency_projection import project_dependency_status

                item["dependency_status"] = project_dependency_status(
                    meta, root=root, board=board
                ).to_dict()
        if _backlog_open_feature(meta):
            from cascade.feature.readiness import compute_feature_readiness
            from cascade.feature.readiness_evidence import approval_evidence

            approval_state, approval_revision = approval_evidence(meta, root=root)

            feature_readiness = compute_feature_readiness(
                meta.id,
                root=root,
                board=board,
                pending_review_ids=pending_review_ids,
                review_refusals=review_refusals,
                approval_state=approval_state,
            )
        if meta.tier == "epic" and folder == "2_active":
            # The row consumes the exact evaluator serialization used by the
            # command boundary.  Keep this read-only: command execution always
            # re-evaluates before handing off to the durable transition.
            from cascade.epic.return_command import load_return_eligibility_snapshot
            from cascade.epic.return_eligibility import evaluate_return_eligibility

            item["return_to_backlog"] = evaluate_return_eligibility(
                load_return_eligibility_snapshot(meta.id, root=root)
            ).to_dict()
        provider_recovery = _provider_recovery_view(
            meta,
            root=root,
            return_to_backlog=item.get("return_to_backlog"),
            inventory=provider_inventory,
            compatibility_cache=compatibility_cache,
        )
        review = item.get("review")
        if (
            meta.tier == "feature"
            and isinstance(review, dict)
            and review.get("state") in {"preparing_review", "awaiting_review"}
        ):
            # The source plan is already in completed so the MR contains its
            # final location, but operationally the feature remains in flight.
            folder = "2_active"
        close_review = item.get("implementation_review")
        if (
            meta.tier == "epic"
            and folder == "3_completed"
            and (
                (
                    isinstance(close_review, dict)
                    and close_review.get("close_stage") != "completed"
                )
                or (close_review is None and staged_epics.get(meta.id, False))
            )
        ):
            # The reviewed source doc is staged in completed before the forge
            # merge. Keep the Epic visible as active until close reconciliation
            # verifies that the review landed.
            folder = "2_active"
            item["status"] = "active"
        if folder in {"1_backlog", "2_active"} and provider_inventory is not None:
            provider_readiness = _provider_readiness_view(
                meta,
                root=root,
                inventory=provider_inventory,
                recovery=provider_recovery,
                compatibility_cache=compatibility_cache,
            )
            item["provider_readiness"] = provider_readiness
            if feature_readiness is not None:
                item["readiness"] = feature_readiness_to_dict(
                    feature_readiness,
                    meta=meta,
                    board=board,
                    root=root,
                    approval_state=approval_state,
                    approval_revision=approval_revision,
                    provider_readiness=provider_readiness,
                    pending_review_ids=pending_review_ids,
                    review_refusal=review_refusals.get(meta.id),
                )
            if provider_recovery is not None:
                # The incident remains durable until a fresh execution-boundary
                # recheck resolves it.  Live diagnostics may change after a
                # cache refresh, but never erase or authorize recovery from the
                # persisted blocker.
                provider_recovery["diagnostics"] = provider_readiness
        item["provider_recovery"] = provider_recovery
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
