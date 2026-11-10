"""Durable, scoped material-change holds for lifecycle boundaries."""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Literal

from cascade.board.context import resolve_root
from cascade.task.lifecycle_lock import task_lifecycle_lock, task_lifecycle_read_lock
from cascade.workspace.integration_worktree import locate_trunk, merged_board

if TYPE_CHECKING:
    from cascade.workspace.types import ProjectContext

HoldBoundary = Literal["mint", "dispatch", "integration", "merge", "closeout"]
HoldStatus = Literal["active", "released"]

_BOUNDARIES = {"mint", "dispatch", "integration", "merge", "closeout"}
_BOUNDARY_ORDER = {
    name: index
    for index, name in enumerate(
        ("mint", "dispatch", "integration", "merge", "closeout")
    )
}
_BOUNDARY_ALIASES = {
    "minting": "mint",
    "task_integration": "integration",
    "feature_merge": "merge",
    "closure": "closeout",
}
_STORE = Path(".cascade") / "scoped-change-holds.json"
_DIGEST = re.compile(r"(?:sha256:)?[0-9a-f]{64}\Z")


class ScopedChangeHoldError(Exception):
    """A hold mutation or lifecycle transition is not authorized."""

    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class HoldReleaseEvidence:
    """The exact decision and refreshed review/approval that released a hold."""

    decision_ref: str
    review_unit_id: str | None
    reviewed_tuple_digest: str | None
    approval_ref: str | None
    released_by: str
    released_at: datetime

    def __post_init__(self) -> None:
        _nonblank(self.decision_ref, "decision reference")
        _nonblank(self.released_by, "release owner")
        supplied = (
            self.review_unit_id,
            self.reviewed_tuple_digest,
            self.approval_ref,
        )
        if any(value is not None for value in supplied) and not all(
            isinstance(value, str) and value.strip() for value in supplied
        ):
            raise ScopedChangeHoldError(
                "invalid_release_evidence",
                "review unit, reviewed tuple digest, and approval reference must be recorded together",
            )
        if self.reviewed_tuple_digest is not None and not _DIGEST.fullmatch(
            self.reviewed_tuple_digest
        ):
            raise ScopedChangeHoldError(
                "invalid_release_evidence", "reviewed tuple digest is invalid"
            )
        if self.released_at.tzinfo is None or self.released_at.utcoffset() is None:
            raise ScopedChangeHoldError(
                "invalid_release_evidence", "release time must be timezone-aware"
            )

    @property
    def has_revised_approval(self) -> bool:
        return self.review_unit_id is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "decision_ref": self.decision_ref,
            "review_unit_id": self.review_unit_id,
            "reviewed_tuple_digest": self.reviewed_tuple_digest,
            "approval_ref": self.approval_ref,
            "released_by": self.released_by,
            "released_at": _stamp(self.released_at),
        }

    @classmethod
    def from_dict(cls, value: object) -> "HoldReleaseEvidence":
        if not isinstance(value, dict):
            raise ScopedChangeHoldError(
                "invalid_hold_store", "release evidence must be an object"
            )
        return cls(
            decision_ref=_string(value.get("decision_ref")),
            review_unit_id=_optional_string(value.get("review_unit_id")),
            reviewed_tuple_digest=_optional_string(value.get("reviewed_tuple_digest")),
            approval_ref=_optional_string(value.get("approval_ref")),
            released_by=_string(value.get("released_by")),
            released_at=_parse_stamp(value.get("released_at")),
        )


@dataclass(frozen=True)
class ScopedChangeHold:
    """One material request held at a precise set of lifecycle boundaries."""

    request_id: str
    affected_work_ids: tuple[str, ...]
    boundaries: tuple[HoldBoundary, ...]
    reason: str
    owner: str
    status: HoldStatus
    requires_revised_approval: bool
    created_at: datetime
    release_evidence: HoldReleaseEvidence | None = None

    def __post_init__(self) -> None:
        _nonblank(self.request_id, "request ID")
        _nonblank(self.reason, "hold reason")
        _nonblank(self.owner, "hold owner")
        if not self.affected_work_ids or any(
            not isinstance(item, str) or not item.strip()
            for item in self.affected_work_ids
        ):
            raise ScopedChangeHoldError(
                "invalid_hold", "at least one affected work ID is required"
            )
        if len(set(self.affected_work_ids)) != len(self.affected_work_ids):
            raise ScopedChangeHoldError(
                "invalid_hold", "affected work IDs must be unique"
            )
        if not self.boundaries or any(
            item not in _BOUNDARIES for item in self.boundaries
        ):
            raise ScopedChangeHoldError(
                "invalid_hold", "at least one valid lifecycle boundary is required"
            )
        if len(set(self.boundaries)) != len(self.boundaries):
            raise ScopedChangeHoldError("invalid_hold", "boundaries must be unique")
        if self.status not in {"active", "released"}:
            raise ScopedChangeHoldError("invalid_hold", "hold status is invalid")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ScopedChangeHoldError(
                "invalid_hold", "creation time must be timezone-aware"
            )
        if (self.status == "released") != (self.release_evidence is not None):
            raise ScopedChangeHoldError(
                "invalid_hold", "released status and release evidence must agree"
            )
        if (
            self.status == "released"
            and self.requires_revised_approval
            and not self.release_evidence.has_revised_approval  # type: ignore[union-attr]
        ):
            raise ScopedChangeHoldError(
                "invalid_hold", "a changed-work hold requires revised approval evidence"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "request_id": self.request_id,
            "affected_work_ids": list(self.affected_work_ids),
            "boundaries": list(self.boundaries),
            "reason": self.reason,
            "owner": self.owner,
            "status": self.status,
            "requires_revised_approval": self.requires_revised_approval,
            "created_at": _stamp(self.created_at),
            "release_evidence": (
                self.release_evidence.to_dict() if self.release_evidence else None
            ),
        }

    @classmethod
    def from_dict(cls, value: object) -> "ScopedChangeHold":
        if not isinstance(value, dict):
            raise ScopedChangeHoldError(
                "invalid_hold_store", "hold row must be an object"
            )
        affected = value.get("affected_work_ids")
        boundaries = value.get("boundaries")
        if not isinstance(affected, list) or not isinstance(boundaries, list):
            raise ScopedChangeHoldError(
                "invalid_hold_store", "hold scope and boundaries must be lists"
            )
        evidence = value.get("release_evidence")
        requires_revised_approval = value.get("requires_revised_approval")
        if not isinstance(requires_revised_approval, bool):
            raise ScopedChangeHoldError(
                "invalid_hold_store", "revised approval requirement must be boolean"
            )
        return cls(
            request_id=_string(value.get("request_id")),
            affected_work_ids=tuple(_string(item) for item in affected),
            boundaries=tuple(_boundary(item) for item in boundaries),
            reason=_string(value.get("reason")),
            owner=_string(value.get("owner")),
            status=_status(value.get("status")),
            requires_revised_approval=requires_revised_approval,
            created_at=_parse_stamp(value.get("created_at")),
            release_evidence=(
                HoldReleaseEvidence.from_dict(evidence)
                if evidence is not None
                else None
            ),
        )

    def refusal(self, work_id: str, boundary: HoldBoundary) -> str:
        release_action = "recording the impact decision"
        if self.requires_revised_approval:
            release_action += " and the required revised review/approval tuple"
        return (
            f"request={self.request_id} affected_work={work_id} boundary={boundary} "
            f"owner={self.owner} reason={self.reason}; release by {release_action}"
        )


def create_scoped_change_hold(
    request_id: str,
    affected_work_ids: Iterable[str],
    boundaries: Iterable[str],
    *,
    reason: str,
    owner: str,
    root: Path,
    requires_revised_approval: bool = True,
) -> ScopedChangeHold:
    """Persist a material-request hold, including the current affected subtrees."""

    repo = locate_trunk(resolve_root(root))
    requested = _unique_nonblank(affected_work_ids, "affected work ID")
    canonical = tuple(
        sorted(
            dict.fromkeys(_boundary(item) for item in boundaries),
            key=_BOUNDARY_ORDER.__getitem__,
        )
    )
    with task_lifecycle_lock(root=repo):
        rows = _read(repo)
        existing = next((row for row in rows if row.request_id == request_id), None)
        if existing is not None:
            if (
                all(item in existing.affected_work_ids for item in requested)
                and existing.boundaries == canonical
                and existing.reason == reason
                and existing.owner == owner
                and existing.requires_revised_approval == requires_revised_approval
            ):
                return existing
            raise ScopedChangeHoldError(
                "hold_conflict",
                f"request {request_id} already has different hold scope",
            )
        board = merged_board(repo)
        scope: set[str] = set()
        for work_id in requested:
            scope.update(_subtree(work_id, board))
            if work_id not in board.by_id:
                scope.add(work_id)
        candidate = ScopedChangeHold(
            request_id=request_id,
            affected_work_ids=tuple(sorted(scope)),
            boundaries=canonical,
            reason=reason,
            owner=owner,
            status="active",
            requires_revised_approval=requires_revised_approval,
            created_at=datetime.now(timezone.utc),
        )
        rows.append(candidate)
        _write(repo, rows)
    return candidate


def release_scoped_change_hold(
    request_id: str,
    *,
    decision_ref: str,
    released_by: str,
    root: Path,
    review_unit_id: str | None = None,
    reviewed_tuple_digest: str | None = None,
    approval_ref: str | None = None,
) -> ScopedChangeHold:
    """Release one hold only with its decision and required refreshed tuple."""

    repo = locate_trunk(resolve_root(root))
    evidence = HoldReleaseEvidence(
        decision_ref=decision_ref,
        review_unit_id=review_unit_id,
        reviewed_tuple_digest=reviewed_tuple_digest,
        approval_ref=approval_ref,
        released_by=released_by,
        released_at=datetime.now(timezone.utc),
    )
    with task_lifecycle_lock(root=repo):
        rows = _read(repo)
        index = next(
            (index for index, row in enumerate(rows) if row.request_id == request_id),
            None,
        )
        if index is None:
            raise ScopedChangeHoldError(
                "hold_not_found", f"unknown request {request_id}"
            )
        current = rows[index]
        if current.status == "released":
            assert current.release_evidence is not None
            if _same_release_identity(current.release_evidence, evidence):
                return current
            raise ScopedChangeHoldError(
                "release_conflict",
                f"request {request_id} was released with different evidence",
            )
        if current.requires_revised_approval and not evidence.has_revised_approval:
            raise ScopedChangeHoldError(
                "revised_approval_required",
                f"request {request_id} requires the exact revised review and approval tuple",
            )
        released = replace(current, status="released", release_evidence=evidence)
        rows[index] = released
        _write(repo, rows)
        return released


def release_revised_change_hold(
    request_id: str,
    *,
    decision_ref: str,
    review_unit_id: str,
    approval_ref: str,
    released_by: str,
    project: "ProjectContext",
) -> ScopedChangeHold:
    """Release changed work after checking its decision and fresh approved tuple.

    ``release_scoped_change_hold`` remains the persistence primitive.  This is
    the policy entry point for living revisions: it proves that the Epic
    disposition exists, the replacement tuple covers that disposition's scope,
    and review happened after the hold was created on the latest accepted
    lineage.
    """

    from cascade.epic.impact_decisions import read_epic_impact_decisions
    from cascade.workspace.architecture_review import ArchitectureReviewStore

    repo = locate_trunk(resolve_root(project.target.root))
    hold = next(
        (row for row in read_scoped_change_holds(root=repo) if row.request_id == request_id),
        None,
    )
    if hold is None:
        raise ScopedChangeHoldError("hold_not_found", f"unknown request {request_id}")
    if not hold.requires_revised_approval:
        raise ScopedChangeHoldError(
            "invalid_release_evidence", "changed-work release requires a revised-approval hold"
        )

    decisions = read_epic_impact_decisions(root=repo)
    decision = next(
        (
            row
            for row in decisions
            if decision_ref in {row.id, row.decision_log_reference}
            and request_id in {row.id, row.handoff_id}
        ),
        None,
    )
    if decision is None:
        raise ScopedChangeHoldError(
            "decision_required", "release does not match a recorded Epic impact decision"
        )
    if decision.materiality != "material" or decision.disposition not in {
        "open_work_amendment",
        "contract_amendment",
    }:
        raise ScopedChangeHoldError(
            "decision_required", "release decision is not a material work amendment"
        )
    if decision.disposition == "contract_amendment":
        from cascade.amendments import AmendmentNotFound, read_amendment

        prefix = "amendment:"
        if not approval_ref.startswith(prefix) or not approval_ref[len(prefix) :].strip():
            raise ScopedChangeHoldError(
                "revised_approval_required",
                "contract changes require an accepted feature-to-Epic amendment reference",
            )
        try:
            amendment = read_amendment(approval_ref[len(prefix) :], root=repo)
        except AmendmentNotFound as exc:
            raise ScopedChangeHoldError(
                "revised_approval_required", "referenced contract amendment does not exist"
            ) from exc
        if (
            amendment.state != "accepted"
            or amendment.feature_id != decision.source_feature_id
        ):
            raise ScopedChangeHoldError(
                "revised_approval_required",
                "contract amendment is not accepted for the changed feature",
            )

    store = ArchitectureReviewStore(project)
    unit = store.get(review_unit_id)
    review = store.get_review(review_unit_id)
    if unit is None or review is None or unit.status != "approved":
        raise ScopedChangeHoldError(
            "revised_approval_required", "replacement proposal is not freshly reviewed and approved"
        )
    if review.decision != "reviewed" or review.tuple_digest != unit.reviewed_tuple_digest:
        raise ScopedChangeHoldError(
            "revised_approval_required", "replacement review does not match the approved tuple"
        )
    try:
        reviewed_at = datetime.fromisoformat(review.reviewed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopedChangeHoldError(
            "invalid_release_evidence", "replacement review time is invalid"
        ) from exc
    if reviewed_at.tzinfo is None or reviewed_at <= hold.created_at:
        raise ScopedChangeHoldError(
            "revised_approval_required", "replacement review predates the scoped change hold"
        )
    if store.baseline_status(unit).stale:
        raise ScopedChangeHoldError(
            "stale_baseline", "replacement proposal is not based on the latest accepted lineage"
        )
    missing = set(decision.affected_work_ids).difference(unit.affected_work_ids)
    if missing:
        raise ScopedChangeHoldError(
            "invalid_release_evidence",
            "replacement proposal omits affected work: " + ", ".join(sorted(missing)),
        )

    return release_scoped_change_hold(
        request_id,
        decision_ref=decision_ref,
        review_unit_id=unit.review_unit_id,
        reviewed_tuple_digest=unit.reviewed_tuple_digest,
        approval_ref=approval_ref,
        released_by=released_by,
        root=repo,
    )


def read_scoped_change_holds(
    *, root: Path, active_only: bool = False
) -> tuple[ScopedChangeHold, ...]:
    repo = locate_trunk(resolve_root(root))
    with task_lifecycle_read_lock(root=repo):
        rows = _read(repo)
    if active_only:
        rows = [row for row in rows if row.status == "active"]
    return tuple(rows)


def holds_affecting(
    work_id: str, boundary: str, *, root: Path
) -> tuple[ScopedChangeHold, ...]:
    """Return active holds for current scope, including descendants added later."""

    repo = locate_trunk(resolve_root(root))
    canonical = _boundary(boundary)
    with task_lifecycle_read_lock(root=repo):
        rows = _read(repo)
        board = merged_board(repo)
    matches: list[ScopedChangeHold] = []
    for row in rows:
        if row.status != "active" or canonical not in row.boundaries:
            continue
        scope: set[str] = set()
        for affected in row.affected_work_ids:
            scope.update(_subtree(affected, board))
            scope.add(affected)
        if work_id in scope:
            matches.append(row)
    return tuple(sorted(matches, key=lambda item: item.request_id))


def require_no_scoped_change_hold(work_id: str, boundary: str, *, root: Path) -> None:
    canonical = _boundary(boundary)
    matches = holds_affecting(work_id, canonical, root=root)
    if matches:
        raise ScopedChangeHoldError(
            "scoped_change_hold", matches[0].refusal(work_id, canonical)
        )


def _subtree(work_id: str, board) -> set[str]:
    result: set[str] = set()
    pending = [work_id]
    while pending:
        current = pending.pop()
        if current in result or current not in board.by_id:
            continue
        result.add(current)
        pending.extend(board.by_id[current].children)
    return result


def _same_release_identity(
    left: HoldReleaseEvidence, right: HoldReleaseEvidence
) -> bool:
    return (
        left.decision_ref == right.decision_ref
        and left.review_unit_id == right.review_unit_id
        and left.reviewed_tuple_digest == right.reviewed_tuple_digest
        and left.approval_ref == right.approval_ref
        and left.released_by == right.released_by
    )


def _read(root: Path) -> list[ScopedChangeHold]:
    path = root / _STORE
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise ScopedChangeHoldError(
            "invalid_hold_store", f"scoped change hold store is malformed: {path}"
        ) from exc
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ScopedChangeHoldError(
            "invalid_hold_store", f"scoped change hold store is unsupported: {path}"
        )
    rows = value.get("holds")
    if not isinstance(rows, list):
        raise ScopedChangeHoldError(
            "invalid_hold_store", "scoped change hold rows must be a list"
        )
    parsed = [ScopedChangeHold.from_dict(row) for row in rows]
    if len({row.request_id for row in parsed}) != len(parsed):
        raise ScopedChangeHoldError(
            "invalid_hold_store", "scoped change hold request IDs must be unique"
        )
    return parsed


def _write(root: Path, rows: list[ScopedChangeHold]) -> None:
    path = root / _STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    {"version": 1, "holds": [row.to_dict() for row in rows]},
                    indent=2,
                    sort_keys=True,
                )
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _boundary(value: object) -> HoldBoundary:
    if not isinstance(value, str):
        raise ScopedChangeHoldError("invalid_boundary", "hold boundary must be text")
    canonical = _BOUNDARY_ALIASES.get(value, value)
    if canonical not in _BOUNDARIES:
        raise ScopedChangeHoldError(
            "invalid_boundary", f"unknown lifecycle hold boundary {value}"
        )
    return canonical  # type: ignore[return-value]


def _status(value: object) -> HoldStatus:
    if value not in {"active", "released"}:
        raise ScopedChangeHoldError("invalid_hold_store", "hold status is invalid")
    return value  # type: ignore[return-value]


def _unique_nonblank(values: Iterable[str], field: str) -> tuple[str, ...]:
    result: list[str] = []
    for value in values:
        _nonblank(value, field)
        if value not in result:
            result.append(value)
    if not result:
        raise ScopedChangeHoldError("invalid_hold", f"{field} is required")
    return tuple(result)


def _nonblank(value: object, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ScopedChangeHoldError("invalid_hold", f"{field} must be nonblank")


def _string(value: object) -> str:
    if not isinstance(value, str):
        raise ScopedChangeHoldError("invalid_hold_store", "expected text")
    return value


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    return _string(value)


def _stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_stamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ScopedChangeHoldError("invalid_hold_store", "timestamp must be text")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ScopedChangeHoldError(
            "invalid_hold_store", "timestamp is invalid"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ScopedChangeHoldError(
            "invalid_hold_store", "timestamp must be timezone-aware"
        )
    return parsed


__all__ = [
    "HoldBoundary",
    "HoldReleaseEvidence",
    "ScopedChangeHold",
    "ScopedChangeHoldError",
    "create_scoped_change_hold",
    "holds_affecting",
    "read_scoped_change_holds",
    "release_revised_change_hold",
    "release_scoped_change_hold",
    "require_no_scoped_change_hold",
]
