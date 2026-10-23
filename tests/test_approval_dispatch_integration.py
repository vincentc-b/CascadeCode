"""End-to-end approval, dependency, merge-gate, and restart reconciliation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cascade.approvals import approve_epic_plan, approve_feature, feature_approved
from cascade.automation import advance_work, reconcile_approval_dispatch, reset_automation_memory
from cascade.board.store import move_doc, read_doc
from cascade.boss.view import compute_boss_view
from cascade.watchdog import activate_epic, dispatch_feature, read_events
from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, commit_board, make_repo


def _enable_automation(root: Path, *, enabled: bool = True) -> None:
    root.joinpath("cascade.toml").write_text(
        f"[automation]\nenabled = {str(enabled).lower()}\n",
        encoding="utf-8",
    )


def _quiet_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)


def _active_epic(root: Path, feature_ids: list[str] | None = None) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    for feature_id in feature_ids or ["feat_001"]:
        add_doc(
            root,
            id=feature_id,
            title=f"Feature {feature_id}",
            tier="feature",
            parent="epic_001",
        )
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok


def _ready_to_plan_events(feature_id: str, *, root: Path) -> list[object]:
    events, _ = read_events(feature_id, 0, root=root)
    return [event for event in events if event.type == "FeatureReadyToPlan"]


def test_reconcile_dispatches_explicitly_approved_feature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root)
    _active_epic(root)
    _quiet_dispatch(monkeypatch)

    approve_feature("feat_001", root=root)

    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"
    assert _ready_to_plan_events("feat_001", root=root)


def test_epic_approval_dispatches_current_children(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Two", tier="feature", parent="epic_001")
    _quiet_dispatch(monkeypatch)

    approve_epic_plan("epic_001", root=root)

    assert feature_approved("feat_001", root=root)
    assert feature_approved("feat_002", root=root)
    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"
    assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"


def test_git_worktree_copies_cannot_hide_epic_child_approvals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Next",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    _quiet_dispatch(monkeypatch)

    approve_epic_plan("epic_001", root=root)

    board = merged_board(root)
    assert board.by_id["feat_001"].path.parent.name == "2_active"
    assert board.by_id["feat_001"].approved_at is not None
    assert board.by_id["feat_002"].approved_at is not None
    assert feature_approved("feat_001", root=root)
    assert feature_approved("feat_002", root=root)
    assert "feat_002" not in compute_boss_view(root=root).dispatchable_features
    rows = board_view_from_index(board, root=root)["features"]
    waiting = next(row for row in rows["1_backlog"] if row["id"] == "feat_002")
    assert waiting["approved"] is True
    assert waiting["readiness"]["approved"] is True
    assert any(code.startswith("unmet_deps") for code in waiting["readiness"]["blockers"])
    assert "not_approved" not in waiting["readiness"]["blockers"]


def test_epic_approval_dispatch_does_not_wait_for_completion_maintenance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Ready", tier="feature", parent="epic_001")
    _quiet_dispatch(monkeypatch)

    def slow_maintenance(*_args, **_kwargs):
        raise AssertionError("approval must not run completion maintenance")

    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", slow_maintenance)
    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        slow_maintenance,
    )

    approve_epic_plan("epic_001", root=root)

    assert feature_approved("feat_001", root=root)
    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"


def test_epic_approval_reports_pending_when_dispatch_fails_then_retries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Ready", tier="feature", parent="epic_001")
    _quiet_dispatch(monkeypatch)

    def fail_dispatch(_root: Path) -> None:
        raise RuntimeError("temporary dispatch failure")

    with monkeypatch.context() as patch:
        patch.setattr(
            "cascade.automation.reconcile_approval_dispatch",
            fail_dispatch,
        )
        result = approve_epic_plan("epic_001", root=root)

    assert result["ok"] is True
    assert result["dispatch_pending"] is True
    assert result["dispatch_error"] == "temporary dispatch failure"
    assert feature_approved("feat_001", root=root)
    assert read_doc("feat_001", root=root).meta.path.parent.name == "1_backlog"

    assert reconcile_approval_dispatch(root)["features"] == ["feat_001"]
    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"


def test_advance_dispatches_before_maintenance_and_after_dependency_release(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    calls: list[str] = []

    def dispatch(_root: Path) -> dict[str, list[str]]:
        calls.append("dispatch")
        return {"features": ["feat_001"] if len(calls) == 1 else ["feat_002"], "tasks": []}

    monkeypatch.setattr("cascade.automation.reconcile_approval_dispatch", dispatch)
    monkeypatch.setattr(
        "cascade.task_rollup.retry_pending_task_merges",
        lambda _root: calls.append("merges"),
    )
    monkeypatch.setattr(
        "cascade.completion_reconcile.reconcile_completion_with_prompts",
        lambda *, root: calls.append("completion"),
    )

    result = advance_work(root)

    assert calls == ["dispatch", "merges", "completion", "dispatch"]
    assert result == {"features": ["feat_001", "feat_002"], "tasks": []}


def test_dependency_blocks_dispatch_until_completed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="First", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Second",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_001"],
    )
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    _quiet_dispatch(monkeypatch)

    approve_feature("feat_001", root=root)
    approve_feature("feat_002", root=root)

    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"
    assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"

    move_doc("feat_001", "completed", root=root)
    released = reconcile_approval_dispatch(root)

    assert released["features"] == ["feat_002"]
    assert read_doc("feat_002", root=root).meta.path.parent.name == "2_active"


def test_merge_gate_blocks_sibling_until_review_clears(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Under review",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(root, id="feat_002", title="Next", tier="feature", parent="epic_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/pull/1",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    _quiet_dispatch(monkeypatch)

    approve_feature("feat_002", root=root)

    assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"

    state.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.example/pull/1",
                    "closed": True,
                }
            }
        ),
        encoding="utf-8",
    )
    released = reconcile_approval_dispatch(root)

    assert released["features"] == ["feat_002"]
    assert read_doc("feat_002", root=root).meta.path.parent.name == "2_active"


def test_restart_reconcile_neither_loses_nor_duplicates_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root, enabled=False)
    _active_epic(root)
    _quiet_dispatch(monkeypatch)

    approve_feature("feat_001", root=root)
    assert read_doc("feat_001", root=root).meta.path.parent.name == "1_backlog"
    approved_at = read_doc("feat_001", root=root).meta.approved_at

    _enable_automation(root)
    reset_automation_memory()
    first = reconcile_approval_dispatch(root)
    assert first["features"] == ["feat_001"]
    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"
    assert len(_ready_to_plan_events("feat_001", root=root)) == 1

    reset_automation_memory()
    second = reconcile_approval_dispatch(root)
    assert second["features"] == []
    assert len(_ready_to_plan_events("feat_001", root=root)) == 1
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at


def test_idempotent_reapprove_triggers_reconcile_without_duplicate_approval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _enable_automation(root, enabled=False)
    _active_epic(root)
    _quiet_dispatch(monkeypatch)

    approve_feature("feat_001", root=root)
    approved_at = read_doc("feat_001", root=root).meta.approved_at

    _enable_automation(root)
    again = approve_feature("feat_001", root=root)
    assert again["newly_approved"] is False
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at
    assert read_doc("feat_001", root=root).meta.path.parent.name == "2_active"
    assert len(_ready_to_plan_events("feat_001", root=root)) == 1


def test_child_added_after_epic_approval_stays_unapproved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _enable_automation(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    _quiet_dispatch(monkeypatch)

    approve_epic_plan("epic_001", root=root)
    add_doc(root, id="feat_002", title="Later", tier="feature", parent="epic_001")

    reset_automation_memory()
    result = reconcile_approval_dispatch(root)

    assert result["features"] == []
    assert feature_approved("feat_001", root=root)
    assert not feature_approved("feat_002", root=root)
    assert dispatch_feature("feat_002", "human", root=root).reason == "not_approved"
