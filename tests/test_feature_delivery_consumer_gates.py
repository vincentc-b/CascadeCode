"""Real-Git coverage for execution consumers of Feature delivery evidence."""

from __future__ import annotations

import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade import review
from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.board.store import read_doc, write_doc
from cascade.boss.view import compute_boss_view
from cascade.dependency_evaluation import evaluate_dependencies
from cascade.feature.recovery import retry_task
from cascade.task.execution import mark_terminal
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task, read_events
from cascade.watchdog.events import append_event
from cascade.watchdog.types import Event
from cascade.war_room.room_settings import write_stacked_pr_enabled
from cascade.workspace.integration_worktree import merged_board
from cascade.workspace.integration_worktree import get_integration_worktree
from tests.support import add_doc as _add_doc
from tests.support import approve_board_feature, commit_board, make_repo


@pytest.fixture(autouse=True)
def configured_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    now = time.time()
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, now, now + 300, 300),
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)


def add_doc(root: Path, **kwargs: object):
    doc = _add_doc(root, **kwargs)
    roles = {
        "epic": (
            "epic_manager",
            "epic_architect",
            "feature_lead",
            "feature_architect",
            "swe",
        ),
        "feature": ("feature_lead", "feature_architect", "swe"),
        "task": ("swe",),
    }[doc.meta.tier]
    doc.meta.provider = "codex"
    doc.meta.models = {role: "offered" for role in roles}
    write_doc(doc, root=root)
    return doc


def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def _consumer_board(tmp_path: Path, *, blocked_task: bool = False) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = get_integration_worktree(root, "epic", "epic_001")
    assert epic_wt is not None
    add_doc(
        epic_wt.path,
        id="feat_002",
        title="Consumer owner",
        tier="feature",
        parent="epic_001",
    )
    commit_board(epic_wt.path)
    approve_board_feature(root, "feat_002")
    assert dispatch_feature("feat_002", "human", root=root).ok
    feature_wt = get_integration_worktree(root, "feature", "feat_002")
    assert feature_wt is not None
    add_doc(
        feature_wt.path,
        id="feat_001",
        title="Delivered dependency",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        feature_wt.path,
        id="task_001",
        title="Consumer",
        tier="task",
        status="blocked" if blocked_task else "backlog",
        parent="feat_002",
        depends_on=["feat_001"],
    )
    if blocked_task:
        mark_terminal("task_001", "failed", root=root, error="forge connection timeout")
    commit_board(feature_wt.path)
    head = _git(root, "rev-parse", "epic/epic_001")
    subprocess.run(["git", "branch", "feat/feat_001", head], cwd=root, check=True)
    return root


def _closed_projection(
    root: Path, *, generation: int = 1, source_head: str | None = None
) -> str:
    head = source_head or _git(root, "rev-parse", "epic/epic_001")
    target_head = _git(root, "rev-parse", "epic/epic_001")
    review._store_review_generation(
        root,
        "feat_001",
        {
            "url": "https://example.test/pulls/1",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": head,
            "target_head": target_head,
            "closed": True,
        },
        generation=generation,
        action_id=f"repair:{generation}",
    )
    return head


@pytest.mark.parametrize("evidence", ["missing", "closed", "stale", "wrong_target"])
def test_integration_consumers_wait_for_current_target_evidence(
    tmp_path: Path, evidence: str
) -> None:
    root = _consumer_board(tmp_path)
    if evidence != "missing":
        integrated_head = _git(root, "rev-parse", "epic/epic_001")
        source_head = integrated_head
        if evidence == "wrong_target":
            source_head = _git(
                root,
                "commit-tree",
                f"{integrated_head}^{{tree}}",
                "-p",
                integrated_head,
                "-m",
                "accepted outside intended target",
            )
            subprocess.run(
                ["git", "branch", "-f", "feat/feat_001", source_head],
                cwd=root,
                check=True,
            )
        head = _closed_projection(root, source_head=source_head)
        if evidence in {"stale", "wrong_target"}:
            review._update_record(
                root,
                "feat_001",
                {
                    "accepted_merge_sha": head,
                    "accepted_source_head": head,
                    "accepted_target_head": integrated_head,
                    "reconciliation_status": "accepted",
                },
            )
        if evidence == "stale":
            _closed_projection(root, generation=2, source_head=head)

    board = merged_board(root)
    task = board.by_id["task_001"]
    delivery = review.feature_delivery_view("feat_001", root=root)

    assert evaluate_dependencies(task, root=root, board=board).satisfied is True
    assert delivery["phase"] != "verified_integrated"
    if evidence == "closed":
        assert delivery["phase"] == "merge_verification_pending"
        assert delivery["blocker"] == "accepted_current_generation_missing"
        assert review.feature_review_pending("feat_001", root=root) is False
    if evidence == "wrong_target":
        assert delivery["evidence_status"] == "accepted_current_generation"
        assert delivery["blocker"] == "intended_target_not_verified"
    if evidence == "stale":
        assert delivery["generation"] == 2
        assert delivery["blocker"] == "accepted_current_generation_missing"
    assert "task_001" not in compute_boss_view(root=root).dispatchable_tasks
    refused = dispatch_task("task_001", "boss", root=root)
    assert refused.ok is False
    assert refused.reason == "feature_awaiting_merge"


def test_verified_current_target_releases_once_through_ordinary_gates(
    tmp_path: Path,
) -> None:
    root = _consumer_board(tmp_path)
    head = _closed_projection(root)
    review._update_record(
        root,
        "feat_001",
        {
            "accepted_merge_sha": head,
            "accepted_source_head": head,
            "accepted_target_head": head,
            "reconciliation_status": "accepted",
        },
    )
    append_event(
        "epic_001",
        Event(
            type="FeatureCompleted",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": "feat_001"},
            dest="epic_001",
        ),
        root=root,
    )

    assert review.feature_delivery_view("feat_001", root=root)["phase"] == (
        "verified_integrated"
    )
    assert compute_boss_view(root=root).dispatchable_tasks == ["task_001"]
    assert dispatch_task("task_001", "boss", root=root).ok is True
    second = dispatch_task("task_001", "boss", root=root)
    assert second.ok is False
    assert second.reason == "bad_state"
    events, _ = read_events("task_001", 0, root=root)
    assert [event.type for event in events].count("TaskDispatched") == 1


def test_recovery_dispatch_reuses_current_delivery_gate(tmp_path: Path) -> None:
    root = _consumer_board(tmp_path, blocked_task=True)
    _closed_projection(root)

    result = retry_task("task_001", feature_id="feat_002", root=root)

    assert result["ok"] is False
    assert result["reason"] == "feature_awaiting_merge"
    assert read_doc("task_001", root=root).meta.status == "blocked"


def test_stacked_feature_dispatch_keeps_open_predecessor_exception(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = get_integration_worktree(root, "epic", "epic_001")
    assert epic_wt is not None
    add_doc(
        epic_wt.path,
        id="feat_001",
        title="Open predecessor",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        epic_wt.path,
        id="feat_002",
        title="Stacked consumer",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    commit_board(epic_wt.path)
    write_stacked_pr_enabled("epic_001", True, root=root)
    approve_board_feature(root, "feat_002")
    head = _git(root, "rev-parse", "HEAD")
    review._store_review_generation(
        root,
        "feat_001",
        {
            "url": "https://example.test/pulls/1",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": head,
            "target_head": head,
            "closed": False,
        },
        generation=1,
        action_id="publication:1",
    )
    subprocess.run(["git", "branch", "feat/feat_001", head], cwd=root, check=True)

    result = dispatch_feature("feat_002", "human", root=root)

    assert result.ok is True
