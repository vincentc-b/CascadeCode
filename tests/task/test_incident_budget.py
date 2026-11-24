import json
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
)
from tests.support import make_repo


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
    assert exhausted["status"] == "exhausted"
    assert exhausted["escalation_id"]
    extended = extend_incident_budget(
        "task_001:known-exhausted",
        AuthenticatedHuman("human:operator"),
        "bounded retry approved",
        {"escalation_id": exhausted["escalation_id"]},
        {"tool_attempts": 1},
        root=root,
    )
    assert extended["status"] == "active"
    assert extended["charged"]["tool_attempts"] == 6


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
