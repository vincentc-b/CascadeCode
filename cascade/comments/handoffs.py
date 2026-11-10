"""Durable, idempotent ownership handoffs for feature comments."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from cascade.board.context import resolve_root
from cascade.comments.types import Comment
from cascade.watchdog.events import append_event, read_events
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event
from cascade.workspace.integration_worktree import locate_trunk, merged_board

HandoffPurpose = Literal["initial_delivery", "epic_impact_triage"]
HandoffStatus = Literal["pending", "delivered"]

_LEDGER = Path("docs") / "_comments" / "_change_request_handoffs.jsonl"


class CommentHandoffError(Exception):
    """A requested comment ownership handoff is not valid."""


@dataclass(frozen=True)
class ChangeRequestHandoff:
    """One accountable delivery of an originating feature-comment thread."""

    id: str
    root_comment_id: str
    thread_id: str
    source_feature_id: str
    affected_work_ids: tuple[str, ...]
    receiving_owner: str
    receiving_team: Literal["feature", "epic"]
    purpose: HandoffPurpose
    status: HandoffStatus
    event_identity: str
    turn_id: str | None
    source_context: dict[str, Any]
    created_at: datetime
    delivered_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "root_comment_id": self.root_comment_id,
            "thread_id": self.thread_id,
            "source_feature_id": self.source_feature_id,
            "affected_work_ids": list(self.affected_work_ids),
            "receiving_owner": self.receiving_owner,
            "receiving_team": self.receiving_team,
            "purpose": self.purpose,
            "status": self.status,
            "event_identity": self.event_identity,
            "turn_id": self.turn_id,
            "source_context": self.source_context,
            "created_at": _stamp(self.created_at),
            "delivered_at": _stamp(self.delivered_at) if self.delivered_at else None,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "ChangeRequestHandoff":
        return cls(
            id=str(raw["id"]),
            root_comment_id=str(raw["root_comment_id"]),
            thread_id=str(raw.get("thread_id", raw["root_comment_id"])),
            source_feature_id=str(raw["source_feature_id"]),
            affected_work_ids=tuple(
                str(item) for item in raw.get("affected_work_ids", [])
            ),
            receiving_owner=str(raw["receiving_owner"]),
            receiving_team=str(raw["receiving_team"]),  # type: ignore[arg-type]
            purpose=str(raw["purpose"]),  # type: ignore[arg-type]
            status=str(raw["status"]),  # type: ignore[arg-type]
            event_identity=str(raw["event_identity"]),
            turn_id=str(raw["turn_id"]) if raw.get("turn_id") else None,
            source_context=dict(raw.get("source_context", {})),
            created_at=_parse_stamp(raw["created_at"]),
            delivered_at=_parse_stamp(raw["delivered_at"])
            if raw.get("delivered_at")
            else None,
        )


def route_feature_comment(
    record: Comment, *, root: Path
) -> ChangeRequestHandoff | None:
    """Route a feature root comment to its live accountable planning team.

    Active-column features retain their Feature Team owner.  A feature without
    a live team is delivered to its active parent Epic Team.  If neither team
    is live, the legacy feature queue event is retained for later activation.
    Replaying this function returns the same handoff and never appends another
    team event.
    """

    if record.parent is not None:
        raise CommentHandoffError("feature-comment routing requires a root comment")

    repo = locate_trunk(resolve_root(root))
    board = merged_board(repo)
    feature = board.by_id.get(record.doc_id)
    if feature is None or feature.tier != "feature":
        raise CommentHandoffError(f"{record.doc_id} is not a feature")

    # Classification belongs to posting time.  If a replay happens after the
    # feature moves columns, retain the owner that already accepted it.
    existing = _find_handoff(
        repo,
        root_comment_id=record.id,
        source_feature_id=feature.id,
        purpose="initial_delivery",
    )
    if existing is not None:
        return _deliver(
            record,
            source_feature_id=feature.id,
            affected_work_ids=existing.affected_work_ids,
            receiving_owner=existing.receiving_owner,
            receiving_team=existing.receiving_team,
            purpose="initial_delivery",
            root=repo,
            source_thread=existing.source_context.get("source_thread"),
        )

    if feature.path.parent.name == "2_active":
        owner, team = feature.id, "feature"
    else:
        parent = board.by_id.get(feature.parent or "")
        if (
            parent is None
            or parent.tier != "epic"
            or parent.path.parent.name != "2_active"
        ):
            return None
        owner, team = parent.id, "epic"

    affected = _affected_ids(feature.id, record.blocks)
    return _deliver(
        record,
        source_feature_id=feature.id,
        affected_work_ids=affected,
        receiving_owner=owner,
        receiving_team=team,  # type: ignore[arg-type]
        purpose="initial_delivery",
        root=repo,
        source_thread=[record.to_dict()],
    )


def escalate_feature_comment(
    feature_id: str,
    root_comment_id: str,
    *,
    affected_work_ids: list[str] | tuple[str, ...] | None = None,
    reason: str,
    root: Path,
) -> ChangeRequestHandoff:
    """Create the single explicit Feature Team -> Epic impact-triage handoff."""

    from cascade.comments.store import read_comments

    repo = locate_trunk(resolve_root(root))
    board = merged_board(repo)
    feature = board.by_id.get(feature_id)
    if feature is None or feature.tier != "feature":
        raise CommentHandoffError(f"{feature_id} is not a feature")
    if feature.path.parent.name != "2_active":
        raise CommentHandoffError(f"feature {feature_id} has no live Feature Team")
    epic = board.by_id.get(feature.parent or "")
    if epic is None or epic.tier != "epic" or epic.path.parent.name != "2_active":
        raise CommentHandoffError(
            f"feature {feature_id} has no active parent Epic Team"
        )
    comments = read_comments(feature_id, root=repo)
    record = next(
        (row for row in comments if row.id == root_comment_id and row.parent is None),
        None,
    )
    if record is None:
        raise CommentHandoffError(f"unknown root comment {root_comment_id}")
    explanation = reason.strip()
    if not explanation:
        raise CommentHandoffError("escalation reason is required")

    affected = _affected_ids(feature_id, affected_work_ids or record.blocks)
    return _deliver(
        record,
        source_feature_id=feature_id,
        affected_work_ids=affected,
        receiving_owner=epic.id,
        receiving_team="epic",
        purpose="epic_impact_triage",
        root=repo,
        escalation_reason=explanation,
        source_thread=[
            row.to_dict() for row in _thread_rows(comments, root_comment_id)
        ],
    )


def read_change_request_handoffs(
    *, root: Path, source_feature_id: str | None = None
) -> list[ChangeRequestHandoff]:
    repo = locate_trunk(resolve_root(root))
    with process_lock:
        rows = _read_ledger(repo)
    if source_feature_id is not None:
        rows = [row for row in rows if row.source_feature_id == source_feature_id]
    return rows


def _deliver(
    record: Comment,
    *,
    source_feature_id: str,
    affected_work_ids: tuple[str, ...],
    receiving_owner: str,
    receiving_team: Literal["feature", "epic"],
    purpose: HandoffPurpose,
    root: Path,
    escalation_reason: str | None = None,
    source_thread: object = None,
) -> ChangeRequestHandoff:
    with process_lock:
        rows = _read_ledger(root)
        # Purpose is unique per originating thread.  In particular, a Feature
        # Team cannot fan out a second Epic escalation by changing the affected
        # set on a retry.  The affected set still participates in the durable
        # identity created for the first accepted handoff.
        existing = next(
            (
                row
                for row in rows
                if row.root_comment_id == record.id
                and row.source_feature_id == source_feature_id
                and row.purpose == purpose
            ),
            None,
        )
        if existing is None:
            handoff_id = _handoff_id(
                record.id,
                source_feature_id,
                affected_work_ids,
                receiving_owner,
                purpose,
            )
            event_identity = f"CommentPosted:{handoff_id}"
            context = _source_context(record)
            context["source_thread"] = (
                source_thread if isinstance(source_thread, list) else [record.to_dict()]
            )
            if escalation_reason is not None:
                context["escalation_reason"] = escalation_reason
            existing = ChangeRequestHandoff(
                id=handoff_id,
                root_comment_id=record.id,
                thread_id=record.id,
                source_feature_id=source_feature_id,
                affected_work_ids=affected_work_ids,
                receiving_owner=receiving_owner,
                receiving_team=receiving_team,
                purpose=purpose,
                status="pending",
                event_identity=event_identity,
                turn_id=None,
                source_context=context,
                created_at=datetime.now(timezone.utc),
            )
            rows.append(existing)
            _write_ledger(root, rows)

        handoff_id = existing.id
        event_identity = existing.event_identity
        source_feature_id = existing.source_feature_id
        receiving_owner = existing.receiving_owner
        purpose = existing.purpose

        # A delivered marker is written only after the event append.  It is
        # therefore sufficient replay evidence even if a completed queue was
        # subsequently pruned.
        if existing.status == "delivered":
            return existing

        if not _event_exists(receiving_owner, event_identity, root):
            append_event(
                receiving_owner,
                Event(
                    type="CommentPosted",
                    ts=datetime.now(timezone.utc),
                    payload={
                        **existing.source_context,
                        "doc_id": source_feature_id,
                        "feature_id": source_feature_id,
                        "comment_id": record.id,
                        "root_comment_id": record.id,
                        "thread_id": record.id,
                        "affected_work_ids": list(existing.affected_work_ids),
                        "receiving_owner": receiving_owner,
                        "delivery_purpose": purpose,
                        "handoff_id": handoff_id,
                        "event_identity": event_identity,
                    },
                    dest=receiving_owner,
                ),
                root=root,
            )

        if existing.status != "delivered":
            delivered = replace(
                existing,
                status="delivered",
                delivered_at=datetime.now(timezone.utc),
            )
            rows = [delivered if row.id == handoff_id else row for row in rows]
            _write_ledger(root, rows)
            existing = delivered
        return existing


def _source_context(record: Comment) -> dict[str, Any]:
    return {
        "section": record.section,
        "anchor": record.anchor,
        "line_start": record.line_start,
        "line_end": record.line_end,
        "doc_sha": record.doc_sha,
        "blocks": list(record.blocks),
        "semantic_anchor": record.semantic_anchor,
        "author": record.author,
        "body": record.body,
        "created": _stamp(record.created),
    }


def _find_handoff(
    root: Path,
    *,
    root_comment_id: str,
    source_feature_id: str,
    purpose: HandoffPurpose,
) -> ChangeRequestHandoff | None:
    with process_lock:
        return next(
            (
                row
                for row in _read_ledger(root)
                if row.root_comment_id == root_comment_id
                and row.source_feature_id == source_feature_id
                and row.purpose == purpose
            ),
            None,
        )


def _affected_ids(feature_id: str, requested: Any) -> tuple[str, ...]:
    values = [feature_id]
    if requested:
        values.extend(str(item) for item in requested)
    return tuple(dict.fromkeys(values))


def _thread_rows(comments: list[Comment], root_id: str) -> list[Comment]:
    included = {root_id}
    result: list[Comment] = []
    for row in comments:
        if row.id in included or row.parent in included:
            included.add(row.id)
            result.append(row)
    return result


def _handoff_id(
    comment_id: str,
    feature_id: str,
    affected_work_ids: tuple[str, ...],
    owner: str,
    purpose: str,
) -> str:
    identity = "\0".join(
        (comment_id, feature_id, *affected_work_ids, owner, purpose)
    )
    return "crh_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]


def _event_exists(owner: str, identity: str, root: Path) -> bool:
    events, _ = read_events(owner, 0, root=root)
    return any(event.payload.get("event_identity") == identity for event in events)


def _read_ledger(root: Path) -> list[ChangeRequestHandoff]:
    path = root / _LEDGER
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except json.JSONDecodeError as exc:
        raise CommentHandoffError("change-request handoff ledger is malformed") from exc
    if not isinstance(raw, list):
        raise CommentHandoffError("change-request handoff ledger must be a list")
    rows: list[ChangeRequestHandoff] = []
    for item in raw:
        if not isinstance(item, dict):
            raise CommentHandoffError("change-request handoff ledger has an invalid row")
        try:
            row = ChangeRequestHandoff.from_dict(item)
        except (KeyError, TypeError, ValueError) as exc:
            raise CommentHandoffError(
                "change-request handoff ledger has an invalid row"
            ) from exc
        if (
            row.receiving_team not in ("feature", "epic")
            or row.purpose not in ("initial_delivery", "epic_impact_triage")
            or row.status not in ("pending", "delivered")
        ):
            raise CommentHandoffError(
                "change-request handoff ledger has an invalid row"
            )
        rows.append(row)
    return rows


def _write_ledger(root: Path, rows: list[ChangeRequestHandoff]) -> None:
    path = root / _LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps([row.to_dict() for row in rows], indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp must be a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return parsed
