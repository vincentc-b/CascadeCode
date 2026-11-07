"""Focused checks for the Flex continuation contract declarations."""

from __future__ import annotations

import json
from dataclasses import replace

from cascade.agent.flex_continuation_contract import (
    ContinuationReceipt,
    FORBIDDEN_AUDIT_FIELDS,
    FlexWaiver,
    InventoryFreshnessAudit,
    OriginalActionIdentity,
    RECEIPT_TRANSITIONS,
    REPLAY_CONTRACTS,
    SAFE_AUDIT_FIELDS,
    DescendantWaiverStamp,
    WaiverCandidate,
    WaiverScopeMember,
    contract_projection,
    receipt_transition_allowed,
    waiver_applies,
)


def test_actions_identity_and_receipt_states_are_stable_and_safe() -> None:
    assert tuple(REPLAY_CONTRACTS) == (
        "epic_activation",
        "feature_dispatch",
        "approval_dispatch",
        "task_retry",
    )
    action = OriginalActionIdentity(
        action_id="dispatch:feat_037_003:7",
        action_kind="feature_dispatch",
        work_id="feat_037_003",
        target_tier="feature",
        document_revision="doc-rev-7",
        selection_fingerprint="a" * 64,
    )
    same = OriginalActionIdentity(**contract_projection(action))
    changed = OriginalActionIdentity(
        **{**contract_projection(action), "document_revision": "doc-rev-8"}
    )

    assert action.roles == ("feature_lead", "feature_architect", "swe")
    assert action.receipt_id == same.receipt_id
    assert action.receipt_id != changed.receipt_id
    assert receipt_transition_allowed("authorized", "handoff_pending")
    assert receipt_transition_allowed("handoff_pending", "ambiguous")
    assert not receipt_transition_allowed("handoff_pending", "blocked")
    assert receipt_transition_allowed(
        "handoff_pending", "blocked", no_acceptance_proven=True
    )
    assert receipt_transition_allowed(
        "ambiguous", "completed", durable_handoff_proven=True
    )
    assert not receipt_transition_allowed("ambiguous", "completed")
    assert not receipt_transition_allowed("ambiguous", "handoff_pending")
    assert not receipt_transition_allowed("completed", "handoff_pending")
    assert set(RECEIPT_TRANSITIONS) == {
        "authorized",
        "handoff_pending",
        "completed",
        "blocked",
        "ambiguous",
    }
    assert SAFE_AUDIT_FIELDS.isdisjoint(FORBIDDEN_AUDIT_FIELDS)
    assert json.loads(json.dumps(contract_projection(action))) == contract_projection(
        action
    )

    member = WaiverScopeMember(
        work_id=action.work_id,
        role="swe",
        document_revision=action.document_revision,
        selection_member_fingerprint="member-a",
    )
    waiver = FlexWaiver(
        waiver_id="waiver-1",
        receipt_id=action.receipt_id,
        scope=(member,),
        authorized_subject="human:operator-7",
        authorized_at="2026-11-07T02:00:00+00:00",
        inventory_freshness=InventoryFreshnessAudit(
            fetched_at=1.0,
            expires_at=61.0,
            age_seconds=2.0,
            stale=False,
            source_version="inventory-v1",
        ),
    )
    receipt = ContinuationReceipt(
        identity=action,
        waiver=waiver,
        state="authorized",
        state_changed_at="2026-11-07T02:00:00+00:00",
    )
    encoded = json.dumps(contract_projection(receipt), sort_keys=True)
    assert "human:operator-7" in encoded
    assert not any(forbidden in encoded for forbidden in FORBIDDEN_AUDIT_FIELDS)


def test_waiver_is_exact_stamp_only_and_child_override_wins() -> None:
    source = WaiverScopeMember(
        work_id="feat_037_003",
        role="swe",
        document_revision="feature-rev-1",
        selection_member_fingerprint="member-a",
    )
    stamp = DescendantWaiverStamp(
        waiver_id="waiver-1",
        source_work_id=source.work_id,
        source_role=source.role,
        source_document_revision=source.document_revision,
        source_member_fingerprint=source.selection_member_fingerprint,
        descendant_work_id="task_037_003_001",
        descendant_role="swe",
        descendant_document_revision="task-rev-1",
        descendant_member_fingerprint="member-b",
    )
    inherited = WaiverCandidate(
        waiver_id="waiver-1",
        work_id="task_037_003_001",
        role="swe",
        document_revision="task-rev-1",
        selection_member_fingerprint="member-b",
        stamp=stamp,
    )

    assert waiver_applies((source,), inherited)
    assert not waiver_applies(
        (source,), replace(inherited, explicit_child_override=True)
    )
    assert not waiver_applies(
        (source,), replace(inherited, document_revision="task-rev-2")
    )
    assert not waiver_applies(
        (source,), replace(inherited, work_id="task_037_003_002")
    )
    assert not waiver_applies(
        (source,), replace(inherited, role="feature_lead")
    )
