import json
import multiprocessing
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.task.action_recovery import (
    create_or_load_action,
    load_action,
    update_recovery_record,
)
from cascade.task.incident_budget import (
    IncidentBudgetAuthorityError,
    IncidentBudgetError,
    bind_incident_budget,
    extend_incident_budget,
    read_incident_budget,
    record_incident_budget_exhaustion,
    reserve_incident_operation,
    settle_incident_operation,
)
from tests.support import make_repo


def _reserve_in_process(
    root: str,
    operation_id: str,
    claim_id: str,
    start: object,
    release: object,
    results: object,
) -> None:
    start.wait()  # type: ignore[attr-defined]
    decision = reserve_incident_operation(
        "task_001:concurrent",
        operation_id,
        "validator",
        {"tool_attempts": 1, "process_seconds": 300},
        claim_id,
        1,
        root=Path(root),
    )
    results.put((decision.state, decision.reason))  # type: ignore[attr-defined]
    release.wait()  # type: ignore[attr-defined]


def _action(
    root: Path,
    action_id: str,
    *,
    parent_action_id: str | None = None,
) -> dict:
    evidence = {"affected_work_id": "task_001"}
    if parent_action_id is not None:
        evidence["parent_action_id"] = parent_action_id
    return create_or_load_action(
        action_id,
        "review_publication",
        root=root,
        attempt_bound=3,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence=evidence,
    )


def test_original_lineage_survives_restart_and_linked_actions_cannot_mint(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    original = _action(root, "task_001:publication")
    generation = original["incident"]["authoritative_generation"]

    bound = bind_incident_budget(
        "task_001:publication",
        "task_001:publication",
        generation,
        {},
        root=root,
    )
    assert bound["original_action_id"] == "task_001:publication"
    assert bound["bindings"][0]["generations"] == [generation]
    assert bound["policy"]["limits"]["known_tokens"] == 200_000
    assert bound["policy"]["retry"] == {
        "deterministic_attempts": 1,
        "transient_attempts": 3,
        "backoff_seconds": [5, 10],
        "jitter_fraction": 0.2,
        "validator_seconds": {"default": 300, "maximum": 3_600},
        "model_turn_seconds": {"default": 300, "maximum": 900},
    }
    assert (
        load_action("task_001:publication", root=root)["incident"][
            "original_incident_id"
        ]
        == "task_001:publication"
    )
    assert read_incident_budget("task_001:publication", root=root) == bound
    refreshed = update_recovery_record(
        "task_001:publication",
        root=root,
        evidence={"affected_work_id": "task_001", "revision": "material-change"},
    )
    assert refreshed["incident"]["authoritative_generation"] != generation
    assert refreshed["incident"]["original_incident_id"] == "task_001:publication"
    rebound = bind_incident_budget(
        "task_001:publication",
        "task_001:publication",
        refreshed["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    assert rebound["bindings"][0]["generations"] == [
        generation,
        refreshed["incident"]["authoritative_generation"],
    ]

    child = _action(
        root,
        "task_001:publication:replacement",
        parent_action_id="task_001:publication",
    )
    child_generation = child["incident"]["authoritative_generation"]
    with pytest.raises(IncidentBudgetError, match="cannot mint"):
        bind_incident_budget(
            "task_001:publication:replacement",
            "task_001:publication:replacement",
            child_generation,
            {"parent_action_id": "task_001:publication"},
            root=root,
        )

    linked = bind_incident_budget(
        "task_001:publication",
        "task_001:publication:replacement",
        child_generation,
        {
            "original_incident_id": "task_001:publication",
            "parent_action_id": "task_001:publication",
        },
        root=root,
    )
    assert [item["action_id"] for item in linked["bindings"]] == [
        "task_001:publication",
        "task_001:publication:replacement",
    ]

    unrelated = _action(root, "task_001:unrelated")
    with pytest.raises(IncidentBudgetError, match="no canonical parent"):
        bind_incident_budget(
            "task_001:publication",
            "task_001:unrelated",
            unrelated["incident"]["authoritative_generation"],
            {
                "original_incident_id": "task_001:publication",
                "parent_action_id": "task_001:publication",
            },
            root=root,
        )


def test_legacy_unknown_usage_waits_for_owner_decision(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:legacy")
    path = root / ".cascade" / "executions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"]["task_001:legacy"]["attempts"] = [
        {"attempt_number": 1, "outcome": "failed"}
    ]
    path.write_text(json.dumps(payload), encoding="utf-8")

    budget = bind_incident_budget(
        "task_001:legacy",
        "task_001:legacy",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    assert budget["status"] == "awaiting_owner_decision"
    assert budget["wait_reason"] == "legacy_usage_unknown"
    assert budget["consumption_quality"] == "unavailable"
    extended = extend_incident_budget(
        "task_001:legacy",
        AuthenticatedHuman("human:operator"),
        "additional allowance does not repair missing accounting",
        {},
        {"tool_attempts": 1},
        root=root,
    )
    assert extended["status"] == "awaiting_owner_decision"
    assert extended["wait_reason"] == "legacy_usage_unknown"


def test_legacy_missing_lineage_waits_and_known_exhaustion_needs_extension(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    ambiguous = _action(root, "task_001:ambiguous")
    generation = ambiguous["incident"]["authoritative_generation"]
    path = root / ".cascade" / "executions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    del payload["actions"]["task_001:ambiguous"]["incident"]
    path.write_text(json.dumps(payload), encoding="utf-8")

    waiting = bind_incident_budget(
        "task_001:ambiguous",
        "task_001:ambiguous",
        generation,
        {},
        root=root,
    )
    assert waiting["status"] == "awaiting_owner_decision"
    assert waiting["wait_reason"] == "legacy_lineage_ambiguous"
    assert waiting["bindings"][0]["generations"] == []

    exhausted_action = _action(root, "task_001:known-exhausted")
    exhausted = bind_incident_budget(
        "task_001:known-exhausted",
        "task_001:known-exhausted",
        exhausted_action["incident"]["authoritative_generation"],
        {"legacy_usage": {"tool_attempts": 6}},
        root=root,
    )
    assert exhausted["status"] == "awaiting_owner_decision"
    assert exhausted["wait_reason"] == "legacy_usage_unverified"
    assert exhausted["charged"]["tool_attempts"] == 0


def test_only_independent_authenticated_bounded_extension_is_retained(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:budget")
    bind_incident_budget(
        "task_001:budget",
        "task_001:budget",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )

    with pytest.raises(IncidentBudgetAuthorityError):
        extend_incident_budget(
            "task_001:budget",
            "operator",  # type: ignore[arg-type]
            "policy correction",
            {},
            {"tool_attempts": 1},
            root=root,
        )
    with pytest.raises(IncidentBudgetAuthorityError, match="cannot extend"):
        extend_incident_budget(
            "task_001:budget",
            AuthenticatedHuman("feat_001"),
            "self retry",
            {},
            {"tool_attempts": 1},
            root=root,
        )
    with pytest.raises(IncidentBudgetError, match="trusted maximum"):
        extend_incident_budget(
            "task_001:budget",
            AuthenticatedHuman("human:operator"),
            "unbounded",
            {},
            {"tool_attempts": 15},
            root=root,
        )
    with pytest.raises(IncidentBudgetError, match="policy version"):
        bind_incident_budget(
            "task_001:budget",
            "task_001:budget",
            action["incident"]["authoritative_generation"],
            {"policy_version": True},
            root=root,
        )

    extended = extend_incident_budget(
        "task_001:budget",
        AuthenticatedHuman("human:operator"),
        "approved correction",
        {"ticket": "operator-approval"},
        {"tool_attempts": 2, "process_seconds": 300},
        root=root,
    )
    replayed = extend_incident_budget(
        "task_001:budget",
        AuthenticatedHuman("human:operator"),
        "approved correction",
        {"ticket": "operator-approval"},
        {"tool_attempts": 2, "process_seconds": 300},
        root=root,
    )
    assert extended == replayed
    assert extended["policy"]["limits"]["tool_attempts"] == 8
    assert len(extended["extensions"]) == 1

    maximum = extend_incident_budget(
        "task_001:budget",
        AuthenticatedHuman("human:operator"),
        "approved maximum",
        {"ticket": "operator-maximum"},
        {"tool_attempts": 12},
        root=root,
    )
    maximum_replay = extend_incident_budget(
        "task_001:budget",
        AuthenticatedHuman("human:operator"),
        "approved maximum",
        {"ticket": "operator-maximum"},
        {"tool_attempts": 12},
        root=root,
    )
    assert maximum_replay == maximum
    assert maximum["policy"]["limits"]["tool_attempts"] == 20


def test_exhaustion_creates_one_escalation_and_extension_preserves_it(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:exhausted")
    bind_incident_budget(
        "task_001:exhausted",
        "task_001:exhausted",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = record_incident_budget_exhaustion(
        "task_001:exhausted", "attempt allowance consumed", root=root, now=now
    )
    replay = record_incident_budget_exhaustion(
        "task_001:exhausted", "different replay text", root=root
    )
    assert replay["escalation_id"] == first["escalation_id"]
    assert replay["exhaustion_reason"] == "attempt allowance consumed"
    assert replay["status"] == "exhausted"

    extended = extend_incident_budget(
        "task_001:exhausted",
        AuthenticatedHuman("human:operator"),
        "reviewed transient outage",
        {"escalation_id": first["escalation_id"]},
        {"tool_attempts": 1},
        root=root,
    )
    assert extended["status"] == "active"
    assert extended["escalation_id"] == first["escalation_id"]
    assert extended["original_admitted_at"] == first["original_admitted_at"]


def test_original_elapsed_origin_survives_late_bind_and_restart(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    action = create_or_load_action(
        "task_001:elapsed",
        "review_publication",
        root=root,
        attempt_bound=3,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
        now=origin,
    )
    bound = bind_incident_budget(
        "task_001:elapsed",
        "task_001:elapsed",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
        now=datetime(2026, 1, 1, 0, 30, tzinfo=timezone.utc),
    )
    assert bound["original_admitted_at"] == origin.isoformat()
    assert bound["original_admission_quality"] == "known"

    after_restart = reserve_incident_operation(
        "task_001:elapsed",
        "validator:late",
        "validator",
        {"tool_attempts": 1, "process_seconds": 10},
        "claim:late",
        1,
        root=root,
        now=datetime(2026, 1, 1, 1, 0, tzinfo=timezone.utc),
    )
    assert after_restart.state == "exhausted"
    assert after_restart.reason == "elapsed_deadline_exhausted"


def test_reserve_settle_nested_charge_and_replay_are_exactly_once(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:operations")
    bind_incident_budget(
        "task_001:operations",
        "task_001:operations",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    first = reserve_incident_operation(
        "task_001:operations",
        "provider:1",
        "provider_turn",
        {"paid_turns": 1, "model_seconds": 300, "known_tokens": 10_000},
        "claim:owner",
        1,
        root=root,
    )
    assert first.state == "admitted"
    assert first.permit is not None
    competing_operation = reserve_incident_operation(
        "task_001:operations",
        "validator:too-early",
        "validator",
        {"tool_attempts": 1, "process_seconds": 300},
        "claim:owner",
        1,
        root=root,
    )
    assert competing_operation.reason == "serialized_operation_in_flight"

    settled = settle_incident_operation(
        "task_001:operations",
        "provider:1",
        {
            "outcome": "success",
            "quality": "known",
            "usage": {"paid_turns": 1, "model_seconds": 12, "known_tokens": 800},
        },
        root=root,
    )
    replay = settle_incident_operation(
        "task_001:operations",
        "provider:1",
        {"outcome": "unknown", "usage": {}},
        root=root,
    )
    assert settled.state == replay.state == "admitted"
    nested = reserve_incident_operation(
        "task_001:operations",
        "validator:1",
        "validator",
        {"tool_attempts": 1, "process_seconds": 300},
        "claim:owner",
        1,
        root=root,
    )
    assert nested.state == "admitted"
    nested_settled = settle_incident_operation(
        "task_001:operations",
        "validator:1",
        {
            "outcome": "success",
            "quality": "estimated",
            "usage": {"tool_attempts": 1, "process_seconds": 4},
            "claim_complete": True,
        },
        root=root,
    )
    assert nested_settled.state == "admitted"
    budget = read_incident_budget("task_001:operations", root=root)
    assert budget is not None
    assert budget["charged"]["paid_turns"] == 1
    assert budget["charged"]["known_tokens"] == 800
    assert budget["charged"]["tool_attempts"] == 1
    assert budget["charged"]["process_seconds"] == 4
    assert budget["reserved"]["process_seconds"] == 0
    assert budget["consumption_quality"] == "estimated"
    assert budget["live_claim"] is None


def test_two_processes_cannot_overspend_or_reclaim_live_owner(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:concurrent")
    bind_incident_budget(
        "task_001:concurrent",
        "task_001:concurrent",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    context = multiprocessing.get_context("fork")
    start = context.Event()
    release = context.Event()
    results = context.Queue()
    processes = [
        context.Process(
            target=_reserve_in_process,
            args=(str(root), f"validator:{index}", f"claim:{index}", start, release, results),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    start.set()
    outcomes = [results.get(timeout=10) for _ in processes]
    release.set()
    for process in processes:
        process.join(timeout=10)
        assert process.exitcode == 0
    assert sorted(state for state, _ in outcomes) == ["admitted", "pending"]
    assert any(reason == "live_incident_claim" for _, reason in outcomes)
    budget = read_incident_budget("task_001:concurrent", root=root)
    assert budget is not None
    assert budget["reserved"]["tool_attempts"] == 1
    assert budget["reserved"]["process_seconds"] == 300


def test_interrupted_operation_retains_conservative_charge_and_claim(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:crash")
    bind_incident_budget(
        "task_001:crash",
        "task_001:crash",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    reserve_incident_operation(
        "task_001:crash",
        "validator:crash",
        "validator",
        {"tool_attempts": 1, "process_seconds": 300},
        "claim:crash",
        1,
        root=root,
    )
    result = settle_incident_operation(
        "task_001:crash",
        "validator:crash",
        {"outcome": "interrupted", "quality": "unavailable", "usage": {}},
        root=root,
    )
    assert result.state == "owner_decision"
    budget = read_incident_budget("task_001:crash", root=root)
    assert budget is not None
    assert budget["charged"]["tool_attempts"] == 1
    assert budget["charged"]["process_seconds"] == 300
    assert budget["consumption_quality"] == "unavailable"
    assert budget["live_claim"]["claim_id"] == "claim:crash"
    assert budget["wait_reason"] == "in_flight_usage_reconciliation_required"


def test_transient_backoff_is_persisted_and_exhaustion_coalesces(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    origin = datetime(2026, 1, 1, tzinfo=timezone.utc)
    action = create_or_load_action(
        "task_001:transient",
        "review_publication",
        root=root,
        attempt_bound=3,
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        evidence={"affected_work_id": "task_001"},
        now=origin,
    )
    bind_incident_budget(
        "task_001:transient",
        "task_001:transient",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )

    for attempt, offset in enumerate((0, 8, 22), start=1):
        operation_id = f"validator:{attempt}"
        admitted = reserve_incident_operation(
            "task_001:transient",
            operation_id,
            "validator",
            {"tool_attempts": 1, "process_seconds": 10},
            "claim:transient",
            1,
            root=root,
            now=origin.replace(second=offset),
        )
        assert admitted.state == "admitted"
        settled = settle_incident_operation(
            "task_001:transient",
            operation_id,
            {
                "outcome": "error",
                "failure_class": "transient",
                "usage": {"tool_attempts": 1, "process_seconds": 1},
            },
            root=root,
            now=origin.replace(second=offset + 1),
        )
        if attempt < 3:
            assert settled.state == "admitted"
            too_soon = reserve_incident_operation(
                "task_001:transient",
                f"validator:{attempt}:early",
                "validator",
                {"tool_attempts": 1, "process_seconds": 10},
                "claim:transient",
                1,
                root=root,
                now=origin.replace(second=offset + 2),
            )
            assert too_soon.reason == "transient_backoff"
        else:
            assert settled.state == "exhausted"

    budget = read_incident_budget("task_001:transient", root=root)
    assert budget is not None
    assert budget["charged"]["tool_attempts"] == 3
    assert budget["charged"]["process_seconds"] == 3
    assert budget["escalation_id"]
    first_escalation = budget["escalation_id"]
    replay = record_incident_budget_exhaustion(
        "task_001:transient", "replayed exhaustion", root=root
    )
    assert replay["escalation_id"] == first_escalation


def test_deterministic_failure_generation_and_policy_cycles_preserve_history(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:deterministic")
    original_generation = action["incident"]["authoritative_generation"]
    bound = bind_incident_budget(
        "task_001:deterministic",
        "task_001:deterministic",
        original_generation,
        {},
        root=root,
    )
    admitted = reserve_incident_operation(
        "task_001:deterministic",
        "validator:unchanged-failure",
        "validator",
        {"tool_attempts": 1, "process_seconds": 300},
        "claim:deterministic",
        1,
        root=root,
    )
    assert (admitted.state, admitted.reason) == (
        "admitted",
        "bounded_permit_reserved",
    )
    assert admitted.permit is not None
    assert admitted.permit.incident_id == bound["incident_id"]
    assert admitted.permit.operation_id == "validator:unchanged-failure"
    assert admitted.permit.claim_id == "claim:deterministic"
    assert admitted.permit.policy_version == bound["policy"]["version"]
    failed = settle_incident_operation(
        "task_001:deterministic",
        "validator:unchanged-failure",
        {
            "outcome": "error",
            "failure_class": "deterministic",
            "quality": "known",
            "usage": {"tool_attempts": 1, "process_seconds": 7},
            "claim_complete": True,
        },
        root=root,
    )
    assert failed.state == "exhausted"
    assert failed.receipt is not None
    assert failed.receipt["claim_id"] == admitted.permit.claim_id
    assert failed.receipt["policy_version"] == admitted.permit.policy_version

    refreshed = update_recovery_record(
        "task_001:deterministic",
        root=root,
        evidence={"affected_work_id": "task_001", "revision": "cosmetic-only"},
    )
    rebound = bind_incident_budget(
        "task_001:deterministic",
        "task_001:deterministic",
        refreshed["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    assert rebound["bindings"][0]["generations"] == [
        original_generation,
        refreshed["incident"]["authoritative_generation"],
    ]
    assert rebound["charged"]["tool_attempts"] == 1
    assert rebound["charged"]["process_seconds"] == 7
    assert set(rebound["operations"]) == {"validator:unchanged-failure"}

    stale_policy = reserve_incident_operation(
        "task_001:deterministic",
        "validator:wrong-policy",
        "validator",
        {"tool_attempts": 1},
        "claim:deterministic",
        2,
        root=root,
    )
    assert (stale_policy.state, stale_policy.reason) == (
        "owner_decision",
        "policy_version_mismatch",
    )
    exhausted = reserve_incident_operation(
        "task_001:deterministic",
        "validator:still-exhausted",
        "validator",
        {"tool_attempts": 1},
        "claim:deterministic",
        1,
        root=root,
    )
    assert (exhausted.state, exhausted.reason) == (
        "exhausted",
        "bounded_extension_required",
    )
    after_refusals = read_incident_budget("task_001:deterministic", root=root)
    assert after_refusals is not None
    assert after_refusals["charged"] == rebound["charged"]
    assert after_refusals["operations"] == rebound["operations"]

    extended = extend_incident_budget(
        "task_001:deterministic",
        AuthenticatedHuman("human:operator"),
        "independently reviewed deterministic correction",
        {"ticket": "operator-002"},
        {"tool_attempts": 1, "process_seconds": 30},
        root=root,
    )
    assert extended["status"] == "active"
    assert extended["charged"] == rebound["charged"]
    assert extended["operations"] == rebound["operations"]
    assert len(extended["extensions"]) == 1


def test_corrupt_policy_and_in_flight_overrun_fail_closed_without_minting(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action = _action(root, "task_001:corrupt-policy")
    bind_incident_budget(
        "task_001:corrupt-policy",
        "task_001:corrupt-policy",
        action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    ledger = root / ".cascade" / "executions.json"
    payload = json.loads(ledger.read_text(encoding="utf-8"))
    payload["incident_budgets"]["task_001:corrupt-policy"]["policy"]["retry"][
        "deterministic_attempts"
    ] = 2
    ledger.write_text(json.dumps(payload), encoding="utf-8")
    corrupt = reserve_incident_operation(
        "task_001:corrupt-policy",
        "validator:must-not-exist",
        "validator",
        {"tool_attempts": 1},
        "claim:corrupt",
        1,
        root=root,
    )
    assert (corrupt.state, corrupt.reason) == (
        "owner_decision",
        "incident_accounting_corrupt",
    )
    corrupt_payload = json.loads(ledger.read_text(encoding="utf-8"))
    corrupt_budget = corrupt_payload["incident_budgets"]["task_001:corrupt-policy"]
    assert corrupt_budget["operations"] == {}
    assert corrupt_budget["charged"]["tool_attempts"] == 0

    overrun_action = _action(root, "task_001:overrun")
    bind_incident_budget(
        "task_001:overrun",
        "task_001:overrun",
        overrun_action["incident"]["authoritative_generation"],
        {},
        root=root,
    )
    assert reserve_incident_operation(
        "task_001:overrun",
        "validator:overrun",
        "validator",
        {"tool_attempts": 1, "process_seconds": 10},
        "claim:overrun",
        1,
        root=root,
    ).admitted
    overrun = settle_incident_operation(
        "task_001:overrun",
        "validator:overrun",
        {
            "outcome": "timeout",
            "failure_class": "transient",
            "quality": "estimated",
            "usage": {"tool_attempts": 1, "process_seconds": 1_801},
        },
        root=root,
    )
    assert overrun.state == "exhausted"
    overrun_budget = read_incident_budget("task_001:overrun", root=root)
    assert overrun_budget is not None
    assert overrun_budget["charged"]["process_seconds"] == 1_801
    assert overrun_budget["consumption_quality"] == "estimated"
    refused = reserve_incident_operation(
        "task_001:overrun",
        "validator:after-overrun",
        "validator",
        {"tool_attempts": 1},
        "claim:overrun",
        1,
        root=root,
    )
    assert (refused.state, refused.reason) == (
        "exhausted",
        "bounded_extension_required",
    )
    after_refusal = read_incident_budget("task_001:overrun", root=root)
    assert after_refusal is not None
    assert set(after_refusal["operations"]) == {"validator:overrun"}
