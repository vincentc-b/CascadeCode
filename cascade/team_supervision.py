"""Durable communication and recovery limited to an immediate family of teams."""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cascade.board.lock import process_lock
from cascade.board.store import read_doc
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event

_REVIEW_REPAIR_REQUEST_FIELDS = frozenset(
    {
        "approval_reference",
        "claim_id",
        "claim_owner",
        "evidence",
        "expected_generation",
        "incident_budget_id",
        "observed_review_generation",
        "observed_source_head",
        "observed_target_head",
        "reason",
        "review_forge",
        "review_url",
        "scope_reference",
        "source_ref",
        "target_ref",
    }
)


def message_team(
    recipient_id: str,
    body: str,
    request_id: str,
    *,
    root: Path,
    epic_id: str | None = None,
    feature_id: str | None = None,
    task_id: str | None = None,
):
    sender_id = task_id or feature_id or epic_id
    if not sender_id or not body.strip() or not request_id.strip():
        raise ValueError("sender, body and stable request_id required")
    with process_lock:
        sender = read_doc(sender_id, root=root)
        recipient = read_doc(recipient_id, root=root)
        if recipient.meta.parent != sender_id and sender.meta.parent != recipient_id:
            raise PermissionError("communication is scoped to direct parent or child")
        identity = f"{sender_id}:{request_id}"
        events, _ = read_events(recipient_id, 0, root=root)
        for event in events:
            if (
                event.type == "TeamMessage"
                and event.payload.get("request_id") == identity
            ):
                if event.payload.get("body") != body:
                    raise ValueError("request_id already used with different message")
                return {
                    "recipient": recipient_id,
                    "request_id": identity,
                    "status": "enqueued",
                }
        append_event(
            recipient_id,
            Event(
                type="TeamMessage",
                ts=datetime.now(timezone.utc),
                payload={
                    "sender": sender_id,
                    "recipient": recipient_id,
                    "request_id": identity,
                    "body": body,
                },
                dest=recipient_id,
            ),
            root=root,
        )
        return {"recipient": recipient_id, "request_id": identity, "status": "enqueued"}


def supervise_child(
    child_id: str,
    action: str = "inspect",
    *,
    root: Path,
    epic_id: str | None = None,
    feature_id: str | None = None,
    repair_request: dict[str, Any] | None = None,
    authenticated_human: AuthenticatedHuman | None = None,
):
    parent_id = feature_id or epic_id
    child = read_doc(child_id, root=root)
    if child.meta.parent != parent_id:
        raise PermissionError("recovery is scoped to a direct child")
    if action not in {"inspect", "recover"}:
        raise ValueError("action must be inspect or recover")
    if child.meta.tier == "task":
        from cascade.feature.recovery import recovery_status, recover_task

        operation = recovery_status if action == "inspect" else recover_task
        return operation(child_id, feature_id=parent_id, root=root)
    if child.meta.tier != "feature":
        raise PermissionError("unsupported child tier")
    if repair_request is not None:
        if action != "recover":
            raise ValueError("a review repair request requires recover")
        request = dict(repair_request)
        request_id = request.pop("request_id", None)
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("a stable review repair request_id is required")
        if {"requesting_parent_id", "authenticated_human"} & request.keys():
            raise PermissionError("repair request cannot supply its own authority")
        if extras := request.keys() - _REVIEW_REPAIR_REQUEST_FIELDS:
            raise ValueError(
                f"unsupported review repair request fields: {', '.join(sorted(extras))}"
            )
        result = request_feature_review_repair(
            child_id,
            request_id,
            root=root,
            requesting_parent_id=parent_id if authenticated_human is None else None,
            authenticated_human=authenticated_human,
            **request,
        )
        return {
            **result,
            "child_id": child_id,
            "status": "active" if result.get("admitted") else child.meta.status,
            "incidents": [],
            "action": action,
        }
    if action == "recover":
        from cascade.workspace.kickoff import graph_turn_owner_is_live

        if graph_turn_owner_is_live(child_id):
            return {
                "child_id": child_id,
                "status": child.meta.status,
                "incidents": [],
                "action": action,
                "outcome": "already_running",
                "selected_operation": "feature_repair.inspect",
                "accountable_owner": f"feature_team:{child_id}",
                "admitted_or_requested": False,
                "acknowledged": False,
                "executed": False,
                "verified": False,
                "refusal": None,
                "next_prerequisite": "live Feature owner must finish its turn",
            }
    from cascade.task.action_recovery import recovery_actions

    incidents = [
        a
        for a in recovery_actions(root=root)
        if (a.get("recovery", {}).get("owning_team") or {}).get("work_id") == child_id
    ]
    mismatch = _recover_feature_lifecycle_mismatch(
        child_id,
        incidents=incidents,
        root=root,
        recover=action == "recover",
    )
    if mismatch is not None:
        return {
            **mismatch,
            "child_id": child_id,
            "status": child.meta.status,
            "incidents": incidents,
            "action": action,
        }
    if action == "recover":
        from hashlib import sha256
        import json
        from cascade.workspace.kickoff import kickoff_graph_queue_event

        generation = sha256(
            json.dumps(incidents, sort_keys=True, default=str).encode()
        ).hexdigest()[:16]
        message_team(
            child_id,
            "Inspect and recover your owned delivery/review; report the outcome to your parent.",
            f"supervise:{child_id}:{generation}",
            epic_id=epic_id,
            feature_id=feature_id,
            root=root,
        )
        kickoff_graph_queue_event(child_id, root=root)
    return {
        "child_id": child_id,
        "status": child.meta.status,
        "incidents": incidents,
        "action": action,
    }


def request_feature_review_repair(
    feature_id: str,
    request_id: str,
    *,
    root: Path,
    requesting_parent_id: str | None = None,
    authenticated_human: AuthenticatedHuman | None = None,
    **request: Any,
) -> dict[str, Any]:
    """Admit and durably wake one exact open-review repair request.

    This is the narrow mutation boundary shared by an Epic parent and the
    later human-facing UI. The Feature repair ledger owns request identity and
    mutable gate checks; this adapter only proves caller scope, schedules the
    already-persisted queue event, and projects acknowledgement separately from
    execution and verification.
    """

    from cascade.feature.repair import (
        admit_open_review_repair,
        inspect_open_review_repair,
    )
    from cascade.workspace.integration_worktree import locate_trunk, merged_board
    from cascade.workspace.kickoff import (
        graph_turn_owner_is_live,
        kickoff_graph_queue_event,
    )

    trunk = locate_trunk(Path(root).resolve())
    board = merged_board(trunk)
    feature = board.by_id.get(feature_id)
    if feature is None or feature.tier != "feature":
        raise PermissionError("review repair is scoped to a Feature")
    if authenticated_human is not None and not isinstance(
        authenticated_human, AuthenticatedHuman
    ):
        raise PermissionError("review repair requires an authenticated human")
    if requesting_parent_id is not None and feature.parent != requesting_parent_id:
        raise PermissionError("review repair is scoped to the direct Epic parent")
    if bool(requesting_parent_id) == bool(authenticated_human):
        raise PermissionError(
            "review repair requires exactly one direct parent or authenticated human"
        )
    if extras := request.keys() - _REVIEW_REPAIR_REQUEST_FIELDS:
        raise ValueError(
            f"unsupported review repair request fields: {', '.join(sorted(extras))}"
        )

    owner_live = graph_turn_owner_is_live(feature_id)
    if owner_live:
        inspected = inspect_open_review_repair(
            feature_id,
            request_id,
            root=trunk,
            requesting_parent_id=requesting_parent_id,
            authenticated_human=authenticated_human,
            **request,
        )
        refused = bool(inspected.get("refused"))
        return {
            **inspected,
            "feature_id": feature_id,
            "selected_operation": "feature_repair.inspect",
            "accountable_owner": f"feature_team:{feature_id}",
            "requested": True,
            "admitted": bool(inspected.get("admitted")),
            "admitted_or_requested": True,
            "acknowledged": bool(inspected.get("acknowledged")),
            "wakeup_acknowledged": False,
            "owner_live": True,
            "executing": bool(inspected.get("executing")),
            "executed": bool(inspected.get("executed")),
            "waiting": bool(inspected.get("waiting")) if refused else True,
            "refused": refused,
            "verification_pending": bool(inspected.get("verification_pending")),
            "verified": bool(inspected.get("verified")),
            "next_prerequisite": inspected.get("next_prerequisite")
            if refused
            else "join_live_feature_owner",
        }

    admitted = admit_open_review_repair(
        feature_id,
        request_id,
        root=trunk,
        requesting_parent_id=requesting_parent_id,
        authenticated_human=authenticated_human,
        **request,
    )
    owner_live = graph_turn_owner_is_live(feature_id)
    wakeup_acknowledged = False
    if admitted.get("admitted") and not owner_live:
        # Admission and FeatureRepairAuthorized are durable before this call.
        # A crash here is replayed from the same action and queue event.
        wakeup_acknowledged = kickoff_graph_queue_event(feature_id, root=trunk)

    next_prerequisite = admitted.get("next_prerequisite")
    if admitted.get("admitted") and owner_live:
        next_prerequisite = "join_live_feature_owner"
    elif admitted.get("admitted") and wakeup_acknowledged:
        next_prerequisite = "feature_queue_checkpoint"
    return {
        **admitted,
        "feature_id": feature_id,
        "selected_operation": "feature_repair.admit",
        "accountable_owner": f"feature_team:{feature_id}",
        "admitted_or_requested": bool(
            admitted.get("requested") or admitted.get("admitted")
        ),
        "acknowledged": bool(admitted.get("acknowledged")),
        "wakeup_acknowledged": wakeup_acknowledged,
        "owner_live": owner_live,
        "waiting": bool(admitted.get("waiting")) or owner_live,
        "next_prerequisite": next_prerequisite,
    }


def _recover_feature_lifecycle_mismatch(
    feature_id: str,
    *,
    incidents: list[dict],
    root: Path,
    recover: bool,
) -> dict | None:
    """Route an exact owned Task mismatch without turning a wakeup into repair."""

    from cascade.board.errors import NotFound
    from cascade.feature.recovery import recover_task, recovery_status
    from cascade.task_rollup import _parent_lifecycle_mismatch

    candidates: list[tuple[str, str]] = []
    expected_owner = f"feature_team:{feature_id}"
    for incident in incidents:
        if incident.get("failure_classification") != "parent_lifecycle_mismatch":
            continue
        metadata = incident.get("metadata")
        mismatch = (
            metadata.get("parent_lifecycle_mismatch")
            if isinstance(metadata, dict)
            else None
        )
        task_id = metadata.get("task_id") if isinstance(metadata, dict) else None
        generation = (
            mismatch.get("authoritative_generation")
            if isinstance(mismatch, dict)
            else None
        )
        if (
            not isinstance(task_id, str)
            or not isinstance(generation, str)
            or mismatch.get("accountable_owner") != expected_owner
        ):
            continue
        try:
            task = read_doc(task_id, root=root)
        except NotFound:
            continue
        if task.meta.tier != "task" or task.meta.parent != feature_id:
            continue
        current = _parent_lifecycle_mismatch(task_id, root)
        if (
            current is not None
            and current.get("authoritative_generation") == generation
            and current.get("accountable_owner") == expected_owner
        ):
            candidates.append((task_id, generation))
    if not candidates:
        return None
    task_id, generation = sorted(candidates)[0]
    if recover:
        return recover_task(
            task_id,
            feature_id=feature_id,
            root=root,
            expected_generation=generation,
        )
    status = recovery_status(task_id, feature_id=feature_id, root=root)
    projected = status.get("parent_lifecycle_mismatch")
    return projected if isinstance(projected, dict) else None
