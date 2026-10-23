"""Epic Team tools: resolve pending amendments (feat_006)."""

from __future__ import annotations

import subprocess
from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path

from cascade.amendments import (
    AmendmentNotFound,
    AmendmentStoreError,
    read_amendment,
    update_amendment,
)
from cascade.amendments.log import append_to_amendment_log
from cascade.amendments.section import replace_section_body
from cascade.board.errors import NotFound
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc
from cascade.epic.guard import EpicToolDenied
from cascade.epic.registry import register_epic_tool
from cascade.epic.scoped_docs import epic_read_doc, epic_write_doc
from cascade.feature.decisions import record_decision
from cascade.watchdog import append_event
from cascade.watchdog.types import Event

_RESOLVABLE = frozenset({"pending"})
_TERMINAL = frozenset({"accepted", "rejected"})
_DEFAULT_REJECT_REASON = "Amendment rejected by the Epic Architect."


class ResolveAmendmentError(AmendmentStoreError):
    """Invalid resolve_amendment request or state transition."""


def resolve_amendment(
    amd_id: str,
    decision: str,
    note: str | None = None,
    revised_text: str | None = None,
    *,
    epic_id: str,
    root: Path,
) -> str | None:
    """Accept, reject, or revise a pending amendment. Returns epic commit SHA on accept."""

    repo = Path(root).resolve()
    _require_active_epic(epic_id, repo)

    choice = decision.strip().lower()
    if choice not in ("accept", "reject", "revise"):
        raise ResolveAmendmentError(f"invalid decision {decision!r}; use accept, reject, or revise")

    try:
        record = read_amendment(amd_id, root=repo)
    except AmendmentNotFound as exc:
        raise ResolveAmendmentError(str(exc)) from exc

    if record.epic_id != epic_id:
        raise ResolveAmendmentError(
            f"amendment {amd_id} belongs to {record.epic_id}, not {epic_id}"
        )

    if record.state in _TERMINAL:
        feature = read_doc(record.feature_id, root=repo)
        if feature.meta.status != "blocked":
            if record.state == "accepted":
                if choice != "accept":
                    raise ResolveAmendmentError(f"amendment {record.id} is already accepted")
                sha = _epic_head_sha(epic_id, root=repo) or feature.meta.parent_rev
                return sha
            if record.state == "rejected":
                if choice != "reject":
                    raise ResolveAmendmentError(f"amendment {record.id} is already rejected")
                return None
            raise ResolveAmendmentError(f"amendment {record.id} is already {record.state}")
        return _finish_terminal_retry(record, choice=choice, epic_id=epic_id, root=repo)
    if record.state == "revise_pending":
        raise ResolveAmendmentError(
            f"amendment {amd_id} awaits feature ack before Epic resolution"
        )
    if record.state not in _RESOLVABLE:
        raise ResolveAmendmentError(f"amendment {amd_id} cannot be resolved from {record.state!r}")

    if choice == "accept":
        return _accept(record, note=note, epic_id=epic_id, root=repo)
    if choice == "reject":
        _reject(record, note=note, epic_id=epic_id, root=repo)
        return None
    return _revise(record, revised_text=revised_text, root=repo)


def _finish_terminal_retry(
    record,
    *,
    choice: str,
    epic_id: str,
    root: Path,
) -> str | None:
    feature = read_doc(record.feature_id, root=root)
    if feature.meta.status != "blocked":
        raise ResolveAmendmentError(f"amendment {record.id} is already {record.state}")

    if record.state == "accepted":
        if choice != "accept":
            raise ResolveAmendmentError(f"amendment {record.id} is already accepted")
        sha = _epic_head_sha(epic_id, root=root) or feature.meta.parent_rev
        if sha is None:
            raise ResolveAmendmentError(
                f"amendment {record.id} is accepted but epic commit SHA is unavailable"
            )
        _unblock_feature(record.feature_id, parent_rev=sha, root=root)
        return sha

    if record.state == "rejected":
        if choice != "reject":
            raise ResolveAmendmentError(f"amendment {record.id} is already rejected")
        _unblock_feature(record.feature_id, parent_rev=None, root=root)
        return None

    raise ResolveAmendmentError(f"amendment {record.id} is already {record.state}")


def _accept(
    record,
    *,
    note: str | None,
    epic_id: str,
    root: Path,
) -> str:
    approved = (
        record.revised_text
        if record.revised_text is not None and record.revised_text.strip()
        else record.proposed_text
    )
    epic = epic_read_doc(epic_id, epic_id=epic_id, root=root)
    prior_body = epic.body

    if _amendment_logged(epic.body, record.id):
        sha = _epic_head_sha(epic_id, root=root)
        if sha is None:
            raise ResolveAmendmentError(
                "accept found amendment log entry but epic commit SHA is unavailable"
            )
    else:
        new_body = replace_section_body(epic.body, record.section, approved)
        log_note = note.strip() if note and note.strip() else record.rationale
        new_body = append_to_amendment_log(
            new_body,
            amd_id=record.id,
            feature_id=record.feature_id,
            section=record.section,
            outcome="accepted",
            note=log_note,
        )
        updated = WorkDoc(meta=epic.meta, body=new_body, sha=epic.sha)
        sha = epic_write_doc(updated, epic_id=epic_id, root=root)
        if sha is None:
            reverted = WorkDoc(meta=epic.meta, body=prior_body, sha=epic.sha)
            write_doc(reverted, root=root)
            raise ResolveAmendmentError(
                "accept requires a git repository to commit the epic; epic body reverted"
            )

    update_amendment(
        _replace_state(record, state="accepted"),
        root=root,
    )

    append_event(
        record.feature_id,
        Event(
            type="AmendmentApproved",
            ts=datetime.now(timezone.utc),
            payload={
                "feature_id": record.feature_id,
                "epic_id": epic_id,
                "epic_rev": sha,
            },
            dest=record.feature_id,
        ),
        root=root,
    )
    _unblock_feature(record.feature_id, parent_rev=sha, root=root)
    return sha


def _reject(record, *, note: str | None, epic_id: str, root: Path) -> None:
    reason = note.strip() if note and note.strip() else _DEFAULT_REJECT_REASON
    update_amendment(
        _replace_state(record, state="rejected", reject_reason=reason),
        root=root,
    )
    append_event(
        record.feature_id,
        Event(
            type="AmendmentRejected",
            ts=datetime.now(timezone.utc),
            payload={
                "feature_id": record.feature_id,
                "epic_id": epic_id,
                "reason": reason,
            },
            dest=record.feature_id,
        ),
        root=root,
    )
    _unblock_feature(record.feature_id, parent_rev=None, root=root)
    record_decision(
        "Amendment rejected",
        "redesign within current Epic constraints",
        (
            f"Epic rejected amendment {record.id} for section {record.section!r}. "
            "Previously minted Tasks that assumed the proposed amendment text are "
            "NOT auto-unblocked for dispatch; the Feature Team must revise or replace "
            "those Task specs before dispatch."
        ),
        f"feat_006 dec_005; amendment {record.id}",
        feature_id=record.feature_id,
        root=root,
        author="feature_architect",
    )


def _revise(record, *, revised_text: str | None, root: Path) -> None:
    if revised_text is None or not str(revised_text).strip():
        raise ResolveAmendmentError("revise requires non-empty revised_text")
    update_amendment(
        _replace_state(record, state="revise_pending", revised_text=str(revised_text)),
        root=root,
    )


def _unblock_feature(
    feature_id: str,
    *,
    parent_rev: str | None,
    root: Path,
) -> None:
    feature = read_doc(feature_id, root=root)
    if feature.meta.tier != "feature":
        raise ResolveAmendmentError(f"{feature_id} is not a feature")
    updated = deepcopy(feature)
    updated.meta.status = "active"
    updated.meta.updated = date.today()
    if parent_rev is not None:
        updated.meta.parent_rev = parent_rev
    write_doc(updated, root=root)


def _amendment_logged(epic_body: str, amd_id: str) -> bool:
    return f"`{amd_id}`" in epic_body


def _epic_head_sha(epic_id: str, *, root: Path) -> str | None:
    epic = read_doc(epic_id, root=root)
    rel = epic.meta.path.relative_to(root).as_posix()
    result = subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", rel],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def _replace_state(record, **changes):
    from cascade.amendments.types import Amendment

    data = {
        "id": record.id,
        "feature_id": record.feature_id,
        "epic_id": record.epic_id,
        "section": record.section,
        "diff_path": record.diff_path,
        "proposed_text": record.proposed_text,
        "rationale": record.rationale,
        "state": record.state,
        "created": record.created,
        "revised_text": record.revised_text,
        "reject_reason": record.reject_reason,
    }
    data.update(changes)
    return Amendment(**data)


def _require_active_epic(epic_id: str, root: Path) -> None:
    try:
        epic = read_doc(epic_id, root=root)
    except NotFound:
        raise EpicToolDenied(f"unknown work id {epic_id}") from None
    if epic.meta.tier != "epic":
        raise EpicToolDenied(f"{epic_id} is not an epic")
    if epic.meta.status != "active":
        raise EpicToolDenied(f"epic {epic_id} is not active")


register_epic_tool("resolve_amendment", resolve_amendment)
