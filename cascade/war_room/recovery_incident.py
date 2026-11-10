"""Canonical read-only War Room projection of durable action recovery."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any


def recovery_incidents_by_work_id(
    *, root, actions: Iterable[Mapping[str, Any]] | None = None
) -> dict[str, dict[str, object]]:
    """Return at most one active incident per affected board row."""

    from cascade.task.action_recovery import recovery_actions

    incidents: dict[str, tuple[str, dict[str, object]]] = {}
    for action in recovery_actions(root=root) if actions is None else actions:
        incident = recovery_incident_from_action(action)
        if incident is None:
            continue
        work_id = incident.pop("_affected_work_id")
        if not isinstance(work_id, str):
            continue
        stamp = str(action.get("updated_at") or action.get("created_at") or "")
        previous = incidents.get(work_id)
        if previous is None or stamp >= previous[0]:
            incidents[work_id] = (stamp, incident)
    return {work_id: incident for work_id, (_, incident) in incidents.items()}


def recovery_incident_from_action(
    action: Mapping[str, Any],
) -> dict[str, object] | None:
    """Make the stable public contract from one persisted action record."""

    recovery = _mapping(action.get("recovery"))
    evidence = _mapping(recovery.get("evidence"))
    provenance = _mapping(recovery.get("provenance"))
    affected_work_id = _text(evidence.get("affected_work_id"))
    if affected_work_id is None or action.get("recovery_state") == "completed":
        return None
    routing = _mapping(recovery.get("routing_marker"))
    blocker = _mapping(recovery.get("human_blocker"))
    owner = _owner(recovery.get("owning_team"))
    state = _state(action, routing, blocker)
    if state == "blocked" and owner is None:
        owner = {"kind": "human_operator", "work_id": affected_work_id}
    branch = _first_text(
        evidence.get("branch"),
        provenance.get("source_branch"),
        provenance.get("source_ref"),
        evidence.get("intended_target_ref"),
    )
    return {
        "state": state,
        "reason": _first_text(
            evidence.get("safe_summary"),
            blocker.get("message"),
            evidence.get("failure_code"),
            action.get("action_kind"),
            "Recovery action failed safely.",
        ),
        "owner": owner,
        "affected": {
            "branch": branch,
            "paths": _text_list(evidence.get("conflicting_paths")),
        },
        "last_attempt": _last_attempt(action),
        "target": _target(action, evidence, provenance, affected_work_id),
        "next_step": _next_step(state, blocker, owner),
        "_affected_work_id": affected_work_id,
    }


def _state(
    action: Mapping[str, Any], routing: Mapping[str, Any], blocker: Mapping[str, Any]
) -> str:
    if action.get("recovery_state") in {"blocked", "awaiting_human_gate"} or blocker:
        return "blocked"
    # A failure is not an investigation until the durable queue handoff exists.
    return "investigating" if routing.get("status") == "enqueued" else "failed"


def _last_attempt(action: Mapping[str, Any]) -> dict[str, object]:
    attempts = action.get("attempts")
    latest = (
        attempts[-1]
        if isinstance(attempts, list) and attempts and isinstance(attempts[-1], Mapping)
        else {}
    )
    return {
        "number": int(action.get("attempt_count") or 0),
        "at": _first_text(
            latest.get("completed_at"),
            latest.get("started_at"),
            action.get("updated_at"),
            action.get("created_at"),
        ),
    }


def _target(
    action: Mapping[str, Any],
    evidence: Mapping[str, Any],
    provenance: Mapping[str, Any],
    work_id: str,
) -> dict[str, object]:
    review_url = _first_text(evidence.get("review_url"), provenance.get("review_url"))
    if review_url is not None:
        return {"kind": "review", "href": review_url}
    return {
        "kind": "action",
        "id": _text(action.get("action_id")) or "unknown-action",
        "href": f"/api/doc/{work_id}",
    }


def _next_step(
    state: str, blocker: Mapping[str, Any], owner: dict[str, str] | None
) -> str:
    if state == "blocked":
        return (
            _text(blocker.get("required_action"))
            or "Resolve the recorded blocker before resuming the action."
        )
    if state == "investigating":
        return "The owning team has been durably asked to investigate this action."
    return (
        "Route this recovery action to an owning team before resuming."
        if owner is None
        else "The failure is recorded; queue the owning team investigation before resuming."
    )


def _owner(value: object) -> dict[str, str] | None:
    owner = _mapping(value)
    kind, work_id = _text(owner.get("kind")), _text(owner.get("work_id"))
    return (
        {"kind": kind, "work_id": work_id}
        if kind is not None and work_id is not None
        else None
    )


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _first_text(*values: object) -> str | None:
    return next((item for value in values if (item := _text(value)) is not None), None)


def _text_list(value: object) -> list[str]:
    return (
        [item for value in value if (item := _text(value)) is not None]
        if isinstance(value, list)
        else []
    )
