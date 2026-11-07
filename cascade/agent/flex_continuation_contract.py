"""Inert contract declarations for human-authorized continuation without Flex.

This module names the identity, scope, replay, audit, and durable receipt
vocabulary shared by the later implementation tasks.  It deliberately performs
no discovery, lifecycle mutation, waiver persistence, or replay.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal, Mapping

from cascade.agent.capability_contract import SelectionRole, WorkTier, role_scope

ActionKind = Literal[
    "epic_activation",
    "feature_dispatch",
    "approval_dispatch",
    "task_retry",
]
ReceiptState = Literal[
    "authorized",
    "handoff_pending",
    "completed",
    "blocked",
    "ambiguous",
]

CONTINUATION_RECEIPT_SCHEMA = "flex-continuation-v1"


@dataclass(frozen=True)
class ReplayContract:
    """One supported original action and its ordinary replay boundary."""

    target_tiers: tuple[WorkTier, ...]
    entry_point: str


REPLAY_CONTRACTS: Mapping[ActionKind, ReplayContract] = {
    "epic_activation": ReplayContract(
        ("epic",), "cascade.watchdog.dispatch.activate_epic"
    ),
    "feature_dispatch": ReplayContract(
        ("feature",), "cascade.watchdog.dispatch.dispatch_feature"
    ),
    "approval_dispatch": ReplayContract(
        ("feature", "task"), "cascade.automation.reconcile_approval_dispatch"
    ),
    "task_retry": ReplayContract(("task",), "cascade.feature.recovery.retry_task"),
}


@dataclass(frozen=True)
class OriginalActionIdentity:
    """Identity minted by the failed ordinary gate, never by the retry click."""

    action_id: str
    action_kind: ActionKind
    work_id: str
    target_tier: WorkTier
    document_revision: str
    selection_fingerprint: str
    trigger_id: str | None = None

    def __post_init__(self) -> None:
        contract = REPLAY_CONTRACTS[self.action_kind]
        if self.target_tier not in contract.target_tiers:
            raise ValueError(
                f"{self.action_kind} cannot target tier {self.target_tier}"
            )
        for name in (
            "action_id",
            "work_id",
            "document_revision",
            "selection_fingerprint",
        ):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a nonempty stable string")

    @property
    def receipt_id(self) -> str:
        """Bind idempotency to action, revision, and the shared selection."""

        payload = {
            "schema": CONTINUATION_RECEIPT_SCHEMA,
            "original_action": {
                "action_id": self.action_id,
                "action_kind": self.action_kind,
                "work_id": self.work_id,
                "target_tier": self.target_tier,
                "trigger_id": self.trigger_id,
            },
            "document_revision": self.document_revision,
            "selection_fingerprint": self.selection_fingerprint,
        }
        encoded = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @property
    def roles(self) -> tuple[SelectionRole, ...]:
        """Return the complete ordered selection scope for this target."""

        return role_scope(self.target_tier)


@dataclass(frozen=True)
class WaiverScopeMember:
    """One exact role member authorized by the original whole-scope check."""

    work_id: str
    role: SelectionRole
    document_revision: str
    selection_member_fingerprint: str


@dataclass(frozen=True)
class DescendantWaiverStamp:
    """Proven normal parent-to-child inheritance of one authorized member."""

    waiver_id: str
    source_work_id: str
    source_role: SelectionRole
    source_document_revision: str
    source_member_fingerprint: str
    descendant_work_id: str
    descendant_role: SelectionRole
    descendant_document_revision: str
    descendant_member_fingerprint: str


@dataclass(frozen=True)
class WaiverCandidate:
    """Current selection facts used to apply the runtime-only override."""

    waiver_id: str
    work_id: str
    role: SelectionRole
    document_revision: str
    selection_member_fingerprint: str
    explicit_child_override: bool = False
    stamp: DescendantWaiverStamp | None = None


@dataclass(frozen=True)
class InventoryFreshnessAudit:
    """Portable, non-secret evidence used by the authorization check."""

    fetched_at: float | None
    expires_at: float | None
    age_seconds: float | None
    stale: bool
    source_version: str | None = None


@dataclass(frozen=True)
class FlexWaiver:
    """Runtime-only service-tier override; reviewed selection stays unchanged."""

    waiver_id: str
    receipt_id: str
    scope: tuple[WaiverScopeMember, ...]
    authorized_subject: str
    authorized_at: str
    inventory_freshness: InventoryFreshnessAudit
    requested_flex: bool = True
    effective_flex: bool = False

    def __post_init__(self) -> None:
        if not self.scope:
            raise ValueError("a Flex waiver requires an evaluated role scope")
        if not self.requested_flex or self.effective_flex:
            raise ValueError("a Flex waiver must change requested true to effective false")


@dataclass(frozen=True)
class ContinuationReceipt:
    """Durable non-secret authorization, handoff, and outcome projection."""

    identity: OriginalActionIdentity
    waiver: FlexWaiver
    state: ReceiptState
    state_changed_at: str
    handoff_id: str | None = None
    reason_code: str | None = None
    classification: Literal["deterministic", "transient"] | None = None
    retry_outcome: Literal[
        "succeeded", "already_completed", "failed_after_handoff"
    ] | None = None

    def __post_init__(self) -> None:
        if self.waiver.receipt_id != self.identity.receipt_id:
            raise ValueError("waiver and original action must name the same receipt")
        if self.state == "completed" and not self.handoff_id:
            raise ValueError(f"{self.state} receipt requires a durable handoff_id")


def waiver_applies(
    authorized: tuple[WaiverScopeMember, ...], candidate: WaiverCandidate
) -> bool:
    """Express exact-member and stamped-descendant precedence fail closed.

    Explicit child configuration always wins.  Direct members require the same
    revision and selection member.  Descendants additionally require a stamp
    that binds both the authorized source and the descendant's current revision
    and member fingerprint; a later edit therefore invalidates the stamp.
    """

    if candidate.explicit_child_override:
        return False
    for member in authorized:
        if (
            candidate.work_id == member.work_id
            and candidate.role == member.role
            and candidate.document_revision == member.document_revision
            and candidate.selection_member_fingerprint
            == member.selection_member_fingerprint
        ):
            return True
        stamp = candidate.stamp
        if stamp is None or stamp.waiver_id != candidate.waiver_id:
            continue
        if (
            stamp.source_work_id == member.work_id
            and stamp.source_role == member.role
            and stamp.source_document_revision == member.document_revision
            and stamp.source_member_fingerprint
            == member.selection_member_fingerprint
            and stamp.descendant_work_id == candidate.work_id
            and stamp.descendant_role == candidate.role
            and stamp.descendant_document_revision == candidate.document_revision
            and stamp.descendant_member_fingerprint
            == candidate.selection_member_fingerprint
        ):
            return True
    return False


RECEIPT_TRANSITIONS: Mapping[ReceiptState, tuple[ReceiptState, ...]] = {
    "authorized": ("handoff_pending", "blocked"),
    "handoff_pending": ("completed", "blocked", "ambiguous"),
    # Reconciliation may resolve uncertainty from durable ordinary-action
    # evidence, but it may never return the receipt to a replayable state.
    "ambiguous": ("completed",),
    "completed": (),
    "blocked": (),
}


def receipt_transition_allowed(
    current: ReceiptState,
    target: ReceiptState,
    *,
    no_acceptance_proven: bool = False,
    durable_handoff_proven: bool = False,
) -> bool:
    """Return whether a compare-and-set receipt transition is evidenced.

    Once an adapter call may have started, absence of a handoff row is not
    proof that no lifecycle effect occurred.  Such a receipt must become
    ambiguous unless the ordinary gate proves non-acceptance.  Conversely,
    completing a receipt requires durable evidence of the ordinary handoff.
    """

    if target not in RECEIPT_TRANSITIONS[current]:
        return False
    if current == "handoff_pending" and target == "blocked":
        return no_acceptance_proven
    if target == "completed":
        return durable_handoff_proven
    return True


SAFE_AUDIT_FIELDS = frozenset(
    {
        "receipt_id",
        "waiver_id",
        "action_id",
        "action_kind",
        "work_id",
        "trigger_id",
        "document_path",
        "document_revision",
        "selection_fingerprint",
        "scope",
        "source_lineage",
        "authorized_subject",
        "authorized_at",
        "state",
        "state_changed_at",
        "requested_flex",
        "effective_flex",
        "inventory_freshness",
        "reason_code",
        "classification",
        "handoff_id",
        "retry_outcome",
        "blocker",
    }
)

FORBIDDEN_AUDIT_FIELDS = frozenset(
    {
        "credential",
        "token",
        "environment",
        "provider_payload",
        "raw_exception",
        "prompt",
        "model_output",
        "checkpoint",
    }
)


def contract_projection(value: object) -> dict[str, object]:
    """Return deterministic JSON-safe data for the inert declarations."""

    projected = asdict(value)  # type: ignore[arg-type]
    return json.loads(json.dumps(projected, sort_keys=True))


__all__ = [
    "ActionKind",
    "CONTINUATION_RECEIPT_SCHEMA",
    "ContinuationReceipt",
    "DescendantWaiverStamp",
    "FlexWaiver",
    "FORBIDDEN_AUDIT_FIELDS",
    "InventoryFreshnessAudit",
    "OriginalActionIdentity",
    "RECEIPT_TRANSITIONS",
    "REPLAY_CONTRACTS",
    "ReceiptState",
    "SAFE_AUDIT_FIELDS",
    "WaiverCandidate",
    "WaiverScopeMember",
    "contract_projection",
    "receipt_transition_allowed",
    "waiver_applies",
]
