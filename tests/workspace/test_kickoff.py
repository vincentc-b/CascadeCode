"""Kickoff turn authorization gates (task_066)."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cascade.agent import run_role
from cascade.agent.types import RoleResult
from cascade.comments.store import comment
from cascade.epic.graph import clear_epic_graph_sessions, ensure_epic_graph, ingest_queue
from cascade.epic.mint import mint_feature
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.feature.mint import mint_task
from cascade.watchdog import (
    activate_epic,
    append_event,
    dispatch_feature,
    dispatch_task,
    register_boot_hook,
)
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory, run_watchdog
from cascade.watchdog.types import Event
from cascade.workspace.kickoff import kickoff_turn, resume_inflight_graphs
from cascade.workspace.types import KickoffReason
from cascade.workspace.up import resume_legally_active_graphs
from tests.support import TEST_MODEL_ID, add_doc, make_repo, approve_board_feature


@pytest.fixture(autouse=True)
def _isolate_graphs() -> None:
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()
    yield
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _commit_all(root: Path, message: str = "docs") -> None:
    _git(root, "add", "-A")
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            result.stdout,
            result.stderr,
        )


def _seed_epic_chain(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="ready_to_plan",
        parent="epic_001",
    )
    _commit_all(root)


def _patch_run_role(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    mock = AsyncMock(
        return_value=RoleResult(text="model-output", status="finished"),
    )

    async def _wrapped(turn):  # type: ignore[no-untyped-def]
        return await mock(turn)

    monkeypatch.setattr("cascade.agent.adapter.run_role", _wrapped)
    monkeypatch.setattr("cascade.agent.planning_turn.run_role", _wrapped)
    monkeypatch.setattr("cascade.task.swe_turn.run_role", _wrapped)
    return mock


@pytest.mark.parametrize(
    "action",
    [
        "mint_feature",
        "mint_task",
        "backlog_ready",
        "watchdog_idle",
        "boss_view",
        "attach",
        "view_plan",
    ],
)
def test_forbidden_paths_do_not_call_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.task.boot import install_task_boot_hook
    from cascade.task.wiring import install_task_wiring
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    install_task_boot_hook(root)
    install_task_wiring(root)
    install_kickoff(root)

    _seed_epic_chain(root)
    add_doc(
        root,
        id="feat_002",
        title="Backlog ready",
        tier="feature",
        status="ready_to_plan",
        parent="epic_001",
    )
    _commit_all(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    if action == "mint_feature":
        from cascade.workspace.integration_worktree import get_integration_worktree

        epic_wt = get_integration_worktree(root, "epic", "epic_001")
        assert epic_wt is not None
        mint_feature("Child", epic_id="epic_001", root=epic_wt.path)
    elif action == "mint_task":
        approve_board_feature(root, "feat_001")
        assert dispatch_feature("feat_001", "human", root=root).ok
        run_role_mock.reset_mock()
        from cascade.workspace.integration_worktree import get_integration_worktree

        feat_wt = get_integration_worktree(root, "feature", "feat_001")
        assert feat_wt is not None
        mint_task("Child task", feature_id="feat_001", root=feat_wt.path)
    elif action == "backlog_ready":
        pass
    elif action == "watchdog_idle":
        run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)
    elif action == "boss_view":
        from cascade.boss.view import compute_boss_view

        compute_boss_view(root=root)
    elif action == "attach":
        from cascade.war_room.attachment import AttachmentState

        AttachmentState().attach("epic_001")
    elif action == "view_plan":
        from cascade.board.store import read_doc

        read_doc("epic_001", root=root)

    assert run_role_mock.await_count == 0


def test_activate_epic_kickoff_one_planning_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)

    assert activate_epic("epic_001", "human", root=root).ok

    assert run_role_mock.await_count >= 2


def test_dispatch_feature_kickoff_one_planning_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert run_role_mock.await_count >= 1


def test_dispatch_feature_turn_is_told_to_mint_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    prompts = [call.args[0].prompt for call in run_role_mock.await_args_list]
    assert prompts
    for prompt in prompts:
        assert "team for `feat_001`" in prompt
        assert "call mint_task once for each task" in prompt


def test_deferred_kickoff_returns_before_the_turn_runs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    from cascade.workspace.kickoff import deferred_kickoffs, wait_for_background_kickoffs

    root = make_repo(tmp_path)
    release = threading.Event()
    ran: list[str] = []

    def _slow_turn(reason, repo):  # type: ignore[no-untyped-def]
        release.wait(5)
        ran.append(reason.work_id)

    monkeypatch.setattr("cascade.workspace.kickoff._kickoff_turn", _slow_turn)
    reason = KickoffReason(kind="dispatch", work_id="feat_001", by="human", root=root)
    with deferred_kickoffs():
        kickoff_turn(reason)
        kickoff_turn(reason)
    assert ran == []
    release.set()
    assert wait_for_background_kickoffs(timeout=5)
    assert ran == ["feat_001", "feat_001"]


def test_background_task_crash_is_failed_instead_of_only_logged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cascade.workspace.kickoff import _report_background_failure

    root = make_repo(tmp_path)
    failures: list[tuple[str, str]] = []
    monkeypatch.setattr(
        "cascade.task.failure.fail_task",
        lambda task_id, reason, **_kwargs: failures.append((task_id, reason)),
    )

    _report_background_failure("task_001", RuntimeError("boom"), root)

    assert failures == [("task_001", "background_error")]


def test_dispatch_task_kickoff_swe_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.task.boot import install_task_boot_hook
    from cascade.task.wiring import install_task_wiring
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    install_task_boot_hook(root)
    install_task_wiring(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="ready_to_plan",
        parent="feat_001",
    )
    _commit_all(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    run_role_mock.reset_mock()

    assert dispatch_task("task_001", "human", root=root).ok
    assert run_role_mock.await_count >= 1


def test_human_chat_on_epic_kickoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.epic.wiring import accept_human_chat
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    accept_human_chat(
        "epic_001",
        {"body": "hello", "id": "m1"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    assert run_role_mock.await_count >= 1


def test_comment_on_task_does_not_call_model(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    _seed_epic_chain(root)
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    _commit_all(root)

    from cascade.comments.store import CommentStoreError

    with pytest.raises(CommentStoreError):
        comment(
            "task_001",
            "Acceptance criteria",
            "fix this",
            author="human",
            root=root,
            is_attached=lambda _doc: True,
        )
    assert run_role_mock.await_count == 0


def test_resume_idle_epic_does_not_kickoff(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    resume_legally_active_graphs(root)
    assert run_role_mock.await_count == 0


def test_generic_inflight_recovery_leaves_active_tasks_to_lease_watchdog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    _seed_epic_chain(root)
    add_doc(
        root,
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    invoked: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._graph_has_inflight_turn",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_turn",
        lambda reason: invoked.append(reason.work_id),
    )

    resume_inflight_graphs(root)
    assert "task_001" not in invoked


def test_opening_turn_cannot_dispatch_feature(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cascade.agent.mcp_wrappers import dispatch_planning_tool, ToolEffectCollector

    root = make_repo(tmp_path)
    collector = ToolEffectCollector()
    with pytest.raises(ValueError, match="not available"):
        dispatch_planning_tool(
            "epic",
            "dispatch_feature",
            {"work_id": "feat_001"},
            scope_id="epic_001",
            repo_root=root,
            collector=collector,
        )


def test_model_resolution_failure_does_not_call_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=False, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)

    assert activate_epic("epic_001", "human", root=root).ok
    assert run_role_mock.await_count == 0
    war_events, _ = read_events("war_room", 0, root=root)
    assert any(e.type == "Toast" and e.payload.get("id") == "epic_001" for e in war_events)


def test_human_message_model_resolution_failure_does_not_call_adapter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=False, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)

    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()
    war_events_before, _ = read_events("war_room", 0, root=root)
    toast_count_before = sum(
        1 for e in war_events_before if e.type == "Toast" and e.payload.get("id") == "epic_001"
    )

    kickoff_turn(
        KickoffReason(
            kind="human_message",
            work_id="epic_001",
            by="human",
            root=root,
            message={"role": "human", "content": "hello"},
        )
    )

    assert run_role_mock.await_count == 0
    war_events, _ = read_events("war_room", 0, root=root)
    toast_count_after = sum(
        1 for e in war_events if e.type == "Toast" and e.payload.get("id") == "epic_001"
    )
    assert toast_count_after > toast_count_before


def test_queue_event_kickoff_via_watchdog(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    run_role_mock = _patch_run_role(monkeypatch)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.workspace.kickoff import install_kickoff

    install_epic_boot_hook(root)
    install_kickoff(root)
    _seed_epic_chain(root)
    assert activate_epic("epic_001", "human", root=root).ok
    run_role_mock.reset_mock()

    append_event(
        "epic_001",
        Event(
            type="DecisionRecorded",
            ts=datetime.now(timezone.utc),
            payload={"section": "Decision log", "entry": "dec_001"},
            dest="epic_001",
        ),
        root=root,
    )
    ingest_queue("epic_001", root=root)
    kickoff_turn(
        KickoffReason(
            kind="queue_event",
            work_id="epic_001",
            by="watchdog",
            root=root,
        )
    )
    assert run_role_mock.await_count >= 1
