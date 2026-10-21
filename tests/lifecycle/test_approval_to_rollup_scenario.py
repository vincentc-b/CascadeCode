"""End-to-end lifecycle scenario: approval through feature and epic rollup (task_010)."""

from __future__ import annotations

import json
import urllib.request

import pytest

from cascade.automation import advance_work, reconcile_approval_dispatch, reset_automation_memory
from cascade.board.store import read_doc
from cascade.boss.merge import merge_task_branch
from cascade.boss.epic_complete import reset_epic_close_prompt_surfaces
from cascade.completion_reconcile import reconcile_completion_with_prompts
from cascade.review import feature_review_pending
from cascade.task.worktree import get_task_run
from tests.lifecycle.scenario import (
    commit_task_run,
    epic_ready_to_close_toast_count,
    feature_completed_count,
    follow_feature_blocked_in_backlog,
    gate_feature_active,
    install_scenario_review_recording,
    ready_to_plan_event_count,
    task_dispatched_count,
    write_scenario_open_review,
)


def _close_feature_review_and_rollup(scenario, feature_id: str) -> dict[str, list[str]]:
    write_scenario_open_review(scenario, feature_id, closed=True)
    return reconcile_completion_with_prompts(root=scenario.root)


def _merge_scenario_task(scenario, task_id: str, *, rel: str) -> None:
    commit_task_run(task_id, rel=rel, content=f"{task_id}\n")
    result = merge_task_branch(task_id, root=scenario.root)
    assert result.ok, result.reason


def test_lifecycle_approval_to_rollup_system_scenario(
    lifecycle_scenario,
    lifecycle_war_room,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = lifecycle_scenario
    ids = scenario.ids
    root = scenario.root
    install_scenario_review_recording(monkeypatch, scenario)
    reset_epic_close_prompt_surfaces()

    # Seeded approvals: gate feature is active; dependency-gated follow stays undispatched.
    assert gate_feature_active(scenario)
    assert follow_feature_blocked_in_backlog(scenario)
    assert ready_to_plan_event_count(ids.feature_follow, root=root) == 0
    assert task_dispatched_count(ids.task_gate, root=root) == 1
    assert task_dispatched_count(ids.task_follow, root=root) == 0
    assert get_task_run(ids.task_gate) is not None

    with urllib.request.urlopen(f"{lifecycle_war_room.base_url}/api/board") as resp:
        board_payload = json.loads(resp.read().decode())
    active_feature_ids = {
        row["id"] for row in board_payload["features"].get("2_active", [])
    }
    backlog_feature_ids = {
        row["id"] for row in board_payload["features"].get("1_backlog", [])
    }
    assert ids.feature_gate in active_feature_ids
    assert ids.feature_follow in backlog_feature_ids

    # Task merge opens review; terminal feature rollup stays blocked on the open MR.
    _merge_scenario_task(scenario, ids.task_gate, rel="gate.txt")
    reconcile_completion_with_prompts(root=root)
    gate = read_doc(ids.feature_gate, root=root)
    assert gate.meta.status == "completed"
    assert gate.meta.path.parent.name == "3_completed"
    assert feature_review_pending(ids.feature_gate, root=root)
    assert feature_completed_count(ids.epic, ids.feature_gate, root=root) == 0
    assert follow_feature_blocked_in_backlog(scenario)
    assert ready_to_plan_event_count(ids.feature_follow, root=root) == 0

    gate_rollup = _close_feature_review_and_rollup(scenario, ids.feature_gate)
    assert gate_rollup["features"] == [ids.feature_gate]
    assert feature_completed_count(ids.epic, ids.feature_gate, root=root) == 1

    released = reconcile_approval_dispatch(root)
    assert ids.feature_follow in released["features"]
    assert ids.task_follow in released["tasks"]
    assert ready_to_plan_event_count(ids.feature_follow, root=root) == 1
    assert task_dispatched_count(ids.task_follow, root=root) == 1

    reset_automation_memory()
    assert reconcile_approval_dispatch(root) == {"features": [], "tasks": []}
    assert ready_to_plan_event_count(ids.feature_follow, root=root) == 1
    assert task_dispatched_count(ids.task_follow, root=root) == 1

    # Follow feature: same task-then-review ordering and merge-gated rollup.
    _merge_scenario_task(scenario, ids.task_follow, rel="follow.txt")
    reconcile_completion_with_prompts(root=root)
    assert feature_review_pending(ids.feature_follow, root=root)
    assert feature_completed_count(ids.epic, ids.feature_follow, root=root) == 0

    follow_rollup = _close_feature_review_and_rollup(scenario, ids.feature_follow)
    assert follow_rollup["features"] == [ids.feature_follow]
    assert follow_rollup["epics"] == [ids.epic]
    assert feature_completed_count(ids.epic, ids.feature_follow, root=root) == 1
    epic = read_doc(ids.epic, root=root)
    assert epic.meta.status == "completed"
    assert epic.meta.path.parent.name == "3_completed"
    assert epic_ready_to_close_toast_count(ids.epic, root=root) == 0

    # Simulated restart: reconciliation stays idempotent.
    reset_automation_memory()
    assert advance_work(root) == {"features": [], "tasks": []}
    assert reconcile_completion_with_prompts(root=root) == {"features": [], "epics": []}
    assert feature_completed_count(ids.epic, ids.feature_gate, root=root) == 1
    assert feature_completed_count(ids.epic, ids.feature_follow, root=root) == 1
    assert ready_to_plan_event_count(ids.feature_follow, root=root) == 1
    assert epic_ready_to_close_toast_count(ids.epic, root=root) == 0
