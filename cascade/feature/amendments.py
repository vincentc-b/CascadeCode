"""Feature Team tools: propose epic amendments (feat_006)."""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

from cascade.amendments import (
    Amendment,
    AmendmentNotFound,
    AmendmentStoreError,
    allocate_amd_id,
    find_open_for_section,
    read_amendment,
    update_amendment,
    write_sidecar,
)
from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.registry import register_feature_tool
from cascade.feature.scoped_docs import feature_read_doc, feature_write_doc
from cascade.watchdog import append_event
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event


class AmendmentConflict(AmendmentStoreError):
    """An open amendment already exists for this epic section."""


def propose_epic_amendment(
    target_file: str,
    section: str,
    proposed_text: str,
    rationale: str,
    *,
    feature_id: str,
    root: Path,
) -> str:
    """Block the feature, write a sidecar diff, and notify Epic / War Room queues."""

    repo = Path(root).resolve()
    feature = feature_read_doc(feature_id, feature_id=feature_id, root=repo)
    if feature.meta.status == "blocked":
        raise FeatureToolDenied(f"feature {feature_id} is already blocked")

    epic_id = feature.meta.parent
    if epic_id is None:
        raise FeatureToolDenied(f"feature {feature_id} has no parent epic")

    _validate_target_file(target_file, epic_id=epic_id, root=repo)

    epic_at_rev = feature_read_doc(epic_id, feature_id=feature_id, root=repo)
    with process_lock:
        existing = find_open_for_section(epic_id, section, root=repo)
        if existing is not None:
            raise AmendmentConflict(
                f"open amendment {existing.id} already pending for {epic_id} section {section!r}"
            )

        blocked = deepcopy(feature)
        blocked.meta.status = "blocked"
        blocked.meta.updated = date.today()
        feature_write_doc(blocked, feature_id=feature_id, root=repo)

        draft = Amendment(
            id=allocate_amd_id(root=repo),
            feature_id=feature_id,
            epic_id=epic_id,
            section=section,
            diff_path=Path("."),
            proposed_text=proposed_text,
            rationale=rationale,
            state="pending",
            created=datetime.now(timezone.utc),
        )
        try:
            record = write_sidecar(draft, epic_at_rev.body, root=repo)
        except Exception:
            restore = deepcopy(feature)
            restore.meta.updated = date.today()
            feature_write_doc(restore, feature_id=feature_id, root=repo)
            raise

    diff_path = record.diff_path.as_posix()
    append_event(
        epic_id,
        Event(
            type="AmendmentProposed",
            ts=datetime.now(timezone.utc),
            payload={
                "feature_id": feature_id,
                "epic_id": epic_id,
                "section": section,
                "diff_path": diff_path,
                "amd_id": record.id,
            },
            dest=epic_id,
        ),
        root=repo,
    )
    _enqueue_amendment_toast(
        feature_id=feature_id,
        epic_id=epic_id,
        section=section,
        diff_path=diff_path,
        root=repo,
    )
    return record.id


def _validate_target_file(target_file: str, *, epic_id: str, root: Path) -> None:
    try:
        parent = read_doc(epic_id, root=root)
    except NotFound:
        raise FeatureToolDenied(f"unknown parent epic {epic_id}") from None
    if parent.meta.tier != "epic":
        raise FeatureToolDenied(f"{epic_id} is not an epic")

    epic_path = parent.meta.path.resolve()
    raw = target_file.strip()
    if not raw:
        raise FeatureToolDenied("target_file is required")

    if raw == epic_id or raw == parent.meta.id:
        return

    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = (root / candidate).resolve()
    else:
        candidate = candidate.resolve()

    if candidate == epic_path:
        return

    raise FeatureToolDenied(
        f"target_file {target_file!r} does not resolve to parent epic {epic_id}"
    )


def _enqueue_amendment_toast(
    *,
    feature_id: str,
    epic_id: str,
    section: str,
    diff_path: str,
    root: Path,
) -> None:
    message = (
        f"{feature_id} requests an amendment to the {section!r} section on {epic_id}. "
        f"Review diff at {diff_path}."
    )
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "amendment",
                "id": epic_id,
                "message": message,
                "body": message,
            },
            dest="war_room",
        ),
        root=root,
    )


class AckAmendmentError(AmendmentStoreError):
    """Invalid ack_amendment request."""


def ack_amendment(amd_id: str, *, feature_id: str, root: Path) -> None:
    """Acknowledge Epic counter-proposal; return record to pending for re-resolution."""

    repo = Path(root).resolve()
    try:
        record = read_amendment(amd_id, root=repo)
    except AmendmentNotFound as exc:
        raise AckAmendmentError(str(exc)) from exc

    if record.feature_id != feature_id:
        raise AckAmendmentError(
            f"amendment {amd_id} belongs to {record.feature_id}, not {feature_id}"
        )
    if record.state != "revise_pending":
        raise AckAmendmentError(
            f"ack_amendment requires state revise_pending, got {record.state!r}"
        )
    if record.revised_text is None or not record.revised_text.strip():
        raise AckAmendmentError(f"amendment {amd_id} has no revised_text to acknowledge")

    acknowledged = Amendment(
        id=record.id,
        feature_id=record.feature_id,
        epic_id=record.epic_id,
        section=record.section,
        diff_path=record.diff_path,
        proposed_text=record.revised_text,
        rationale=record.rationale,
        state="pending",
        created=record.created,
        revised_text=record.revised_text,
        reject_reason=record.reject_reason,
    )
    epic = feature_read_doc(record.epic_id, feature_id=feature_id, root=repo)
    write_sidecar(acknowledged, epic.body, root=repo)
    update_amendment(acknowledged, root=repo)

    feature = feature_read_doc(feature_id, feature_id=feature_id, root=repo)
    if feature.meta.status != "blocked":
        raise AckAmendmentError(f"feature {feature_id} must remain blocked until resolve")


register_feature_tool("propose_epic_amendment", propose_epic_amendment)
register_feature_tool("ack_amendment", ack_amendment)
