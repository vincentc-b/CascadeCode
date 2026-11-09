"""Durable communication and recovery limited to an immediate family of teams."""

from datetime import datetime, timezone
from pathlib import Path

from cascade.board.lock import process_lock
from cascade.board.store import read_doc
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.types import Event


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
    if action == "recover":
        from cascade.workspace.kickoff import graph_turn_owner_is_live

        if graph_turn_owner_is_live(child_id):
            return {
                "child_id": child_id,
                "status": child.meta.status,
                "incidents": [],
                "action": action,
                "outcome": "already_running",
            }
    from cascade.task.action_recovery import recovery_actions

    incidents = [
        a
        for a in recovery_actions(root=root)
        if (a.get("recovery", {}).get("owning_team") or {}).get("work_id") == child_id
    ]
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
