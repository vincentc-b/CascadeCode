"""Fail-closed eligibility contract for returning an Epic graph to backlog.

This module deliberately has no filesystem, Git, scheduler, or HTTP dependency.
Callers assemble its snapshot from authoritative stores, so the board and the
mutation command can make the same decision before the latter re-checks it
under its lifecycle locks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class ReturnEligibilityReasonCode(StrEnum):
    """Stable refusal codes shared by presentation and command clients."""

    EPIC_NOT_ACTIVE = "epic_not_active"
    EPIC_TRANSITION_IN_PROGRESS = "epic_transition_in_progress"
    GRAPH_UNAVAILABLE = "graph_unavailable"
    GRAPH_INCOMPLETE = "graph_incomplete"
    GRAPH_MEMBER_INVALID = "graph_member_invalid"
    TURN_NOT_QUIESCED = "turn_not_quiesced"
    MEMBER_TRANSITION_IN_PROGRESS = "member_transition_in_progress"
    HISTORY_NOT_PRESERVABLE = "history_not_preservable"
    GIT_STATE_NOT_PRESERVABLE = "git_state_not_preservable"
    SOURCE_BRIEF_MISSING = "source_brief_missing"
    ACTIVATION_PROVENANCE_MISSING = "activation_provenance_missing"
    LIFECYCLE_LOCK_ORDER_UNAVAILABLE = "lifecycle_lock_order_unavailable"
    CONFLICTING_LIFECYCLE_OPERATION = "conflicting_lifecycle_operation"


@dataclass(frozen=True, slots=True)
class ReturnGraphMember:
    """Authoritative preservation and lifecycle facts for one graph member.

    ``None`` means the fact could not be established.  The evaluator treats it
    exactly like an unsafe value; absence must never authorize a transition.
    """

    id: str | None
    tier: str | None
    parent_id: str | None
    source_revision: str | None
    activation_provenance: str | None
    turn_quiesced: bool | None
    transition_in_progress: bool | None
    history_preservable: bool | None
    git_state_preservable: bool | None


@dataclass(frozen=True, slots=True)
class ReturnEligibilityInput:
    """Complete, read-only snapshot required to prove a safe return.

    A failed provider/startup attempt is intentionally not represented as a
    blocker: if it made no substantive change, the normal preservation facts
    remain true and this input remains eligible.
    """

    epic_id: str | None
    epic_tier: str | None
    epic_status: str | None
    epic_transition_in_progress: bool | None
    graph: tuple[ReturnGraphMember, ...] | None
    graph_complete: bool | None
    source_brief_revision: str | None
    lock_order: tuple[str, ...] | None
    conflicting_lifecycle_operation: bool | None


@dataclass(frozen=True, slots=True)
class ReturnEligibilityRefusal:
    """A stable machine code plus safe, operator-readable context."""

    code: ReturnEligibilityReasonCode
    message: str
    member_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReturnEligibility:
    eligible: bool
    refusals: tuple[ReturnEligibilityRefusal, ...] = field(default_factory=tuple)

    @property
    def reason_codes(self) -> tuple[str, ...]:
        """JSON-friendly stable codes, in deterministic display order."""

        return tuple(refusal.code.value for refusal in self.refusals)

    def to_dict(self) -> dict[str, object]:
        """Shared API/board serialization shape."""

        return {
            "eligible": self.eligible,
            "reason_codes": list(self.reason_codes),
            "refusals": [
                {
                    "code": refusal.code.value,
                    "message": refusal.message,
                    "member_ids": list(refusal.member_ids),
                }
                for refusal in self.refusals
            ],
        }


def evaluate_return_eligibility(snapshot: ReturnEligibilityInput) -> ReturnEligibility:
    """Evaluate all return predicates without side effects.

    This is intentionally exhaustive rather than first-failure: an operator
    receives every independently provable blocker and a command can return the
    exact same result after its locked re-read.
    """

    refusals: list[ReturnEligibilityRefusal] = []
    if snapshot.epic_tier != "epic" or snapshot.epic_status != "active" or not snapshot.epic_id:
        refusals.append(_refusal(ReturnEligibilityReasonCode.EPIC_NOT_ACTIVE))
    if snapshot.epic_transition_in_progress is not False:
        refusals.append(_refusal(ReturnEligibilityReasonCode.EPIC_TRANSITION_IN_PROGRESS))
    if snapshot.conflicting_lifecycle_operation is not False:
        refusals.append(_refusal(ReturnEligibilityReasonCode.CONFLICTING_LIFECYCLE_OPERATION))
    if not snapshot.source_brief_revision:
        refusals.append(_refusal(ReturnEligibilityReasonCode.SOURCE_BRIEF_MISSING))

    members = snapshot.graph
    if members is None:
        refusals.append(_refusal(ReturnEligibilityReasonCode.GRAPH_UNAVAILABLE))
        return ReturnEligibility(eligible=False, refusals=tuple(refusals))
    if snapshot.graph_complete is not True:
        refusals.append(_refusal(ReturnEligibilityReasonCode.GRAPH_INCOMPLETE))

    member_ids = tuple(member.id for member in members if member.id)
    if not _valid_graph(snapshot.epic_id, members):
        refusals.append(_refusal(ReturnEligibilityReasonCode.GRAPH_MEMBER_INVALID))
    if missing := _members_where(members, "turn_quiesced", expected=True):
        refusals.append(_refusal(ReturnEligibilityReasonCode.TURN_NOT_QUIESCED, missing))
    if transitioning := _members_where(members, "transition_in_progress", expected=False):
        refusals.append(
            _refusal(ReturnEligibilityReasonCode.MEMBER_TRANSITION_IN_PROGRESS, transitioning)
        )
    if unpreservable := _members_where(members, "history_preservable", expected=True):
        refusals.append(_refusal(ReturnEligibilityReasonCode.HISTORY_NOT_PRESERVABLE, unpreservable))
    if unpreservable := _members_where(members, "git_state_preservable", expected=True):
        refusals.append(_refusal(ReturnEligibilityReasonCode.GIT_STATE_NOT_PRESERVABLE, unpreservable))
    if missing := tuple(member.id for member in members if not member.activation_provenance and member.id):
        refusals.append(_refusal(ReturnEligibilityReasonCode.ACTIVATION_PROVENANCE_MISSING, missing))
    if not _valid_lock_order(snapshot.lock_order, member_ids):
        refusals.append(_refusal(ReturnEligibilityReasonCode.LIFECYCLE_LOCK_ORDER_UNAVAILABLE))

    return ReturnEligibility(eligible=not refusals, refusals=tuple(refusals))


def _valid_graph(epic_id: str | None, members: tuple[ReturnGraphMember, ...]) -> bool:
    if not epic_id or not members:
        return False
    ids = [member.id for member in members]
    if any(not item for item in ids) or len(set(ids)) != len(ids) or epic_id not in ids:
        return False
    by_id = {member.id: member for member in members}
    epic = by_id[epic_id]
    if epic.tier != "epic" or epic.parent_id is not None or not epic.source_revision:
        return False
    return all(
        member.tier in {"epic", "feature", "task"}
        and member.source_revision
        and (member.id == epic_id or member.parent_id in by_id)
        for member in members
    )


def _members_where(
    members: tuple[ReturnGraphMember, ...], attribute: str, *, expected: bool
) -> tuple[str, ...]:
    return tuple(member.id for member in members if getattr(member, attribute) is not expected and member.id)


def _valid_lock_order(lock_order: tuple[str, ...] | None, member_ids: tuple[str, ...]) -> bool:
    """Require a complete, duplicate-free canonical order, never caller ordering."""

    return lock_order is not None and lock_order == tuple(sorted(member_ids))


def _refusal(
    code: ReturnEligibilityReasonCode, member_ids: tuple[str, ...] = ()
) -> ReturnEligibilityRefusal:
    messages = {
        ReturnEligibilityReasonCode.EPIC_NOT_ACTIVE: "The item is not an active Epic.",
        ReturnEligibilityReasonCode.EPIC_TRANSITION_IN_PROGRESS: "The Epic lifecycle state is unknown or already transitioning.",
        ReturnEligibilityReasonCode.GRAPH_UNAVAILABLE: "The complete descendant graph could not be loaded.",
        ReturnEligibilityReasonCode.GRAPH_INCOMPLETE: "The descendant graph could not be proven complete.",
        ReturnEligibilityReasonCode.GRAPH_MEMBER_INVALID: "Graph identities, parent links, or source revisions are incomplete.",
        ReturnEligibilityReasonCode.TURN_NOT_QUIESCED: "One or more graph members still have an unquiesced or unknown turn.",
        ReturnEligibilityReasonCode.MEMBER_TRANSITION_IN_PROGRESS: "One or more graph members are transitioning or have unknown lifecycle state.",
        ReturnEligibilityReasonCode.HISTORY_NOT_PRESERVABLE: "One or more graph members have history that cannot be preserved.",
        ReturnEligibilityReasonCode.GIT_STATE_NOT_PRESERVABLE: "One or more graph members have Git state that cannot be preserved.",
        ReturnEligibilityReasonCode.SOURCE_BRIEF_MISSING: "The Epic source brief revision is unavailable.",
        ReturnEligibilityReasonCode.ACTIVATION_PROVENANCE_MISSING: "One or more graph members lack activation provenance.",
        ReturnEligibilityReasonCode.LIFECYCLE_LOCK_ORDER_UNAVAILABLE: "A deterministic lifecycle-lock order is unavailable.",
        ReturnEligibilityReasonCode.CONFLICTING_LIFECYCLE_OPERATION: "A lifecycle operation is in progress or could not be ruled out.",
    }
    return ReturnEligibilityRefusal(code=code, message=messages[code], member_ids=member_ids)
