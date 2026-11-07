"""Human authorization and durable one-handoff receipt integration."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import (
    DiscoveredModel,
    ProviderCompatibilityEvidence,
)
from cascade.agent.execution_preflight import provider_blocker
from cascade.board.store import read_doc, write_doc
from cascade.provider_recovery_command import (
    AuthenticatedHumanPrincipal,
    authorize_continue_without_flex_command,
    replay_authorized_continuation_command,
)
from cascade.provider_recovery_receipt import (
    claim_continuation_handoff,
    read_continuation_receipt,
)
from cascade.watchdog import activate_epic
from cascade.watchdog.model_resolve import resolve_effective_selections
from tests.support import add_doc, make_repo


def _inventory(*, stale: bool = False) -> ProviderInventoryResult:
    now = time.time()
    return ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(
                    DiscoveredModel(
                        id="offered",
                        display_name="Offered",
                        supports_flex_mode=False,
                    ),
                ),
                supports_flex_mode=False,
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(
            stale, now - 1.0, now - 0.5 if stale else now + 300.0, 300.0
        ),
    )


def _failed_epic(tmp_path: Path, monkeypatch):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    doc = read_doc("epic_001", root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {
        role: "offered"
        for role in (
            "epic_manager",
            "epic_architect",
            "feature_lead",
            "feature_architect",
            "swe",
        )
    }
    doc.meta.flex_mode = True
    write_doc(doc, root=root)
    inventory = _inventory()
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr(
        "cascade.agent.selection_preflight.probe_provider_compatibility",
        lambda _provider: ProviderCompatibilityEvidence(True, True, True),
    )
    assert activate_epic("epic_001", "human", root=root).reason == "provider_preflight_blocked"
    blocker = provider_blocker("epic_001", root=root)
    assert blocker is not None
    return root, inventory, blocker


def _authorize(root: Path, inventory, blocker, **overrides):
    action = blocker["failed_action"]
    arguments = {
        "work_id": "epic_001",
        "failed_action_id": action["action_id"],
        "expected_document_revision": action["document_revision"],
        "expected_selection_fingerprint": action["selection_fingerprint"],
        "principal": AuthenticatedHumanPrincipal("human:operator-7"),
        "actor": "human",
        "root": root,
        "inventory": inventory,
    }
    arguments.update(overrides)
    return authorize_continue_without_flex_command(**arguments)


def test_authorization_is_human_only_exact_and_atomic(tmp_path: Path, monkeypatch) -> None:
    root, inventory, blocker = _failed_epic(tmp_path, monkeypatch)
    document = read_doc("epic_001", root=root).meta.path
    reviewed_bytes = document.read_bytes()

    refused = _authorize(root, inventory, blocker, actor="scheduler")
    assert not refused.ok
    assert refused.error_code == "unauthorized"

    stale = _authorize(
        root, inventory, blocker, expected_selection_fingerprint="wrong-fingerprint"
    )
    assert not stale.ok
    assert stale.error_code == "selection_changed"

    authorized = _authorize(root, inventory, blocker)
    duplicate = _authorize(root, inventory, blocker)
    assert authorized.ok and authorized.state == "authorized"
    assert duplicate.ok and duplicate.idempotent
    assert duplicate.receipt_id == authorized.receipt_id
    assert document.read_bytes() == reviewed_bytes

    ledger = json.loads(
        (root / ".cascade" / "provider_recoveries.json").read_text(encoding="utf-8")
    )
    assert set(ledger) >= {"failed_actions", "flex_waivers", "continuation_receipts"}
    receipt = ledger["continuation_receipts"][authorized.receipt_id]
    assert receipt["authorized_subject"] == "human:operator-7"
    assert receipt["state"] == "authorized"
    assert receipt["selection_fingerprint"] == blocker["selection_fingerprint"]
    raw = json.dumps(ledger)
    assert not any(secret in raw for secret in ("credential", "provider_payload", "token"))


def test_stale_inventory_refuses_before_authorization(tmp_path: Path, monkeypatch) -> None:
    root, _inventory_result, blocker = _failed_epic(tmp_path, monkeypatch)

    refused = _authorize(root, _inventory(stale=True), blocker)

    assert not refused.ok
    assert refused.error_code == "inventory_not_fresh"
    ledger = json.loads(
        (root / ".cascade" / "provider_recoveries.json").read_text(encoding="utf-8")
    )
    assert "continuation_receipts" not in ledger
    assert "flex_waivers" not in ledger


def test_distinct_attempts_survive_mutable_blocker_replacement(
    tmp_path: Path, monkeypatch
) -> None:
    root, inventory, first = _failed_epic(tmp_path, monkeypatch)
    assert activate_epic("epic_001", "human", root=root).reason == "provider_preflight_blocked"
    second = provider_blocker("epic_001", root=root)
    assert second is not None
    first_id = first["failed_action"]["action_id"]
    second_id = second["failed_action"]["action_id"]
    assert first_id != second_id

    attempts = json.loads(
        (root / ".cascade" / "provider_recoveries.json").read_text(encoding="utf-8")
    )["failed_actions"]
    assert {first_id, second_id} <= set(attempts)
    assert attempts[first_id]["original_actor"] == "human"
    assert attempts[first_id]["replay_arguments"] == {"by": "human"}
    assert _authorize(root, inventory, first).ok


def test_concurrent_and_restarted_pending_claim_is_single_use(
    tmp_path: Path, monkeypatch
) -> None:
    root, inventory, blocker = _failed_epic(tmp_path, monkeypatch)
    authorized = _authorize(root, inventory, blocker)
    assert authorized.receipt_id is not None

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(
            pool.map(
                lambda _index: claim_continuation_handoff(
                    authorized.receipt_id, root=root
                ),
                range(16),
            )
        )
    assert sum(claim.claimed for claim in claims) == 1
    handoff_ids = {claim.handoff_id for claim in claims if claim.handoff_id}
    assert len(handoff_ids) == 1

    # Reading from disk and claiming again models a new process after restart:
    # pending is durable and can never return to a replayable state.
    receipt = read_continuation_receipt(authorized.receipt_id, root=root)
    assert receipt is not None and receipt["state"] == "handoff_pending"
    restarted = claim_continuation_handoff(authorized.receipt_id, root=root)
    assert not restarted.claimed
    assert restarted.state == "handoff_pending"
    assert restarted.handoff_id in handoff_ids


def test_epic_replay_records_lineage_and_completes_on_durable_turn(
    tmp_path: Path, monkeypatch
) -> None:
    root, inventory, blocker = _failed_epic(tmp_path, monkeypatch)
    authorized = _authorize(root, inventory, blocker)
    monkeypatch.setattr("cascade.workspace.kickoff._kickoff_turn", lambda *_args: True)

    replayed = replay_authorized_continuation_command(
        authorized.receipt_id, root=root
    )
    duplicate = replay_authorized_continuation_command(
        authorized.receipt_id, root=root
    )

    assert replayed.ok and replayed.state == "completed"
    assert duplicate.state == "completed" and duplicate.idempotent
    ledger = json.loads(
        (root / ".cascade" / "provider_recoveries.json").read_text(encoding="utf-8")
    )
    receipt = ledger["continuation_receipts"][authorized.receipt_id]
    assert receipt["lifecycle_effect"]["event_type"] == "EpicActivated"
    assert receipt["turn_handoff"]["work_id"] == "epic_001"
    lineage = next(iter(ledger["flex_waiver_lineage"].values()))
    assert lineage["before"]["document_path"] != lineage["after"]["document_path"]
    active = read_doc("epic_001", root=root)
    assert all(
        not item.effective_flex_mode
        for item in resolve_effective_selections(active, root=root).selections
    )

    active.body += "\nLater unrelated edit.\n"
    write_doc(active, root=root)
    edited = read_doc("epic_001", root=root)
    assert all(
        item.effective_flex_mode
        for item in resolve_effective_selections(edited, root=root).selections
    )


def test_event_without_turn_evidence_stays_ambiguous_and_never_replays(
    tmp_path: Path, monkeypatch
) -> None:
    root, inventory, blocker = _failed_epic(tmp_path, monkeypatch)
    authorized = _authorize(root, inventory, blocker)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    first = replay_authorized_continuation_command(authorized.receipt_id, root=root)
    duplicate = replay_authorized_continuation_command(
        authorized.receipt_id, root=root
    )

    assert first.state == "ambiguous"
    assert duplicate.state == "ambiguous" and duplicate.idempotent
    events = (root / "docs" / "_queue" / "epic_001.jsonl").read_text().splitlines()
    assert len(events) == 1
