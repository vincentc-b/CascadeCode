"""Verify disposable lifecycle scenario seeding (task_009)."""

from __future__ import annotations

import json
import urllib.request

import pytest

from cascade.approvals import feature_approved
from cascade.board.store import read_doc
from cascade.watchdog import dispatch_feature
from tests.lifecycle.scenario import (
    complete_scenario_gate_feature,
    follow_feature_blocked_in_backlog,
    gate_feature_active,
    quiet_lifecycle_dispatch,
    ready_to_plan_event_count,
    seed_lifecycle_scenario,
    teardown_lifecycle_scenario,
    write_scenario_open_review,
)


def test_seed_leaves_gate_active_and_follow_blocked(lifecycle_scenario) -> None:
    assert feature_approved(lifecycle_scenario.ids.feature_gate, root=lifecycle_scenario.root)
    assert feature_approved(lifecycle_scenario.ids.feature_follow, root=lifecycle_scenario.root)
    assert gate_feature_active(lifecycle_scenario)
    assert follow_feature_blocked_in_backlog(lifecycle_scenario)
    assert ready_to_plan_event_count(
        lifecycle_scenario.ids.feature_follow,
        root=lifecycle_scenario.root,
    ) == 0


def test_manual_dispatch_refuses_blocked_follow_feature(lifecycle_scenario) -> None:
    result = dispatch_feature(
        lifecycle_scenario.ids.feature_follow,
        "human",
        root=lifecycle_scenario.root,
    )
    assert result.ok is False
    assert result.reason == "unmet_deps"
    assert follow_feature_blocked_in_backlog(lifecycle_scenario)


def test_completing_gate_releases_follow_for_dispatch(lifecycle_scenario) -> None:
    released = complete_scenario_gate_feature(lifecycle_scenario)
    assert lifecycle_scenario.ids.feature_follow in released
    follow = read_doc(lifecycle_scenario.ids.feature_follow, root=lifecycle_scenario.root)
    assert follow.meta.path.parent.name == "2_active"
    assert ready_to_plan_event_count(
        lifecycle_scenario.ids.feature_follow,
        root=lifecycle_scenario.root,
    ) == 1


def test_repeated_seed_after_teardown_is_safe(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    quiet_lifecycle_dispatch(monkeypatch)
    first = seed_lifecycle_scenario(tmp_path / "a")
    assert follow_feature_blocked_in_backlog(first)
    teardown_lifecycle_scenario(first.root)

    second = seed_lifecycle_scenario(tmp_path / "b")
    assert follow_feature_blocked_in_backlog(second)
    assert gate_feature_active(second)


def test_war_room_reads_seeded_board(lifecycle_war_room) -> None:
    url = f"{lifecycle_war_room.base_url}/api/board"
    with urllib.request.urlopen(url) as resp:
        payload = json.loads(resp.read().decode())
    feature_ids = {
        row["id"]
        for column in payload["features"].values()
        for row in column
    }
    scenario = lifecycle_war_room.scenario
    assert scenario.ids.feature_gate in feature_ids
    assert scenario.ids.feature_follow in feature_ids
    assert payload["epics"]["2_active"][0]["id"] == scenario.ids.epic


def test_review_registry_helper_is_idempotent(lifecycle_scenario) -> None:
    write_scenario_open_review(lifecycle_scenario, lifecycle_scenario.ids.feature_gate)
    write_scenario_open_review(
        lifecycle_scenario,
        lifecycle_scenario.ids.feature_gate,
        closed=True,
    )
    state = json.loads(
        (lifecycle_scenario.root / ".cascade" / "reviews.json").read_text(encoding="utf-8")
    )
    assert state[lifecycle_scenario.ids.feature_gate]["closed"] is True
