"""Batch classification and single turn per delivery (task_017_001_004)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.comments import comment, reply_comment, resolve_comment
from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory
from cascade.workspace.kickoff import deliver_queue_kickoffs, wait_for_background_kickoffs
from tests.harness.queue_delivery import (
    CountingBlockedTurnRunner,
    append_lifecycle_event,
    boot_feature_graph,
    feature_graph_values,
    install_queue_delivery_test_isolation,
    seed_active_feature_board,
)
from tests.support import make_repo

_FEATURE_PLANNING_ROLES_PER_INVOKE = 2


@pytest.fixture
def runner(monkeypatch: pytest.MonkeyPatch) -> CountingBlockedTurnRunner:
    installed = install_queue_delivery_test_isolation(monkeypatch)
    yield installed
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def _boot(tmp_path: Path, runner: CountingBlockedTurnRunner):
    root = make_repo(tmp_path, models=True, role_skills=True)
    feature_id = seed_active_feature_board(root)
    boot_feature_graph(root, feature_id)
    return root, feature_id


def test_one_human_comment_yields_exactly_one_turn(
    tmp_path: Path,
    runner: CountingBlockedTurnRunner,
) -> None:
    root, feature_id = _boot(tmp_path, runner)

    comment(
        feature_id,
        "Intent",
        "please review scope",
        author="human",
        root=root,
        blocking=False,
    )
    turns_before = runner.turn_count
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)

    assert runner.turn_count == turns_before + _FEATURE_PLANNING_ROLES_PER_INVOKE


def test_agent_reply_and_comment_resolved_yield_zero_turns(
    tmp_path: Path,
    runner: CountingBlockedTurnRunner,
) -> None:
    root, feature_id = _boot(tmp_path, runner)

    root_id = comment(
        feature_id,
        "Intent",
        "needs follow-up",
        author="human",
        root=root,
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    turns_after_human = runner.turn_count

    reply_comment(
        feature_id,
        root_id,
        "agent follow-up",
        author="feature_lead",
        root=root,
    )
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert runner.turn_count == turns_after_human

    resolve_comment(feature_id, root_id, author="human", root=root)
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert runner.turn_count == turns_after_human


def test_staged_message_order_matches_queue_order(
    tmp_path: Path,
    runner: CountingBlockedTurnRunner,
) -> None:
    root, feature_id = _boot(tmp_path, runner)

    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_first",
    )
    comment(
        feature_id,
        "Intent",
        "human note between decisions",
        author="human",
        root=root,
    )
    append_lifecycle_event(
        feature_id,
        "DecisionRecorded",
        root=root,
        section="Decision log",
        entry="dec_second",
    )

    turns_before = runner.turn_count
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)
    assert runner.turn_count == turns_before + _FEATURE_PLANNING_ROLES_PER_INVOKE

    values = feature_graph_values(feature_id, root=root)
    batch = [
        m
        for m in values.get("messages") or []
        if m.get("role") in ("human", "event")
        and (
            "dec_first" in str(m.get("content", ""))
            or "human note between decisions" in str(m.get("content", ""))
            or "dec_second" in str(m.get("content", ""))
        )
    ]
    assert [m.get("role") for m in batch] == ["event", "human", "event"]


def test_two_human_comments_in_one_batch_run_at_most_one_turn(
    tmp_path: Path,
    runner: CountingBlockedTurnRunner,
) -> None:
    root, feature_id = _boot(tmp_path, runner)

    comment(feature_id, "Intent", "first note", author="human", root=root)
    comment(feature_id, "Scope", "second note", author="human", root=root)

    turns_before = runner.turn_count
    deliver_queue_kickoffs(root)
    assert wait_for_background_kickoffs(timeout=15)

    assert runner.turn_count == turns_before + _FEATURE_PLANNING_ROLES_PER_INVOKE
    values = feature_graph_values(feature_id, root=root)
    human_messages = [m for m in values.get("messages") or [] if m.get("role") == "human"]
    assert len(human_messages) == 2
