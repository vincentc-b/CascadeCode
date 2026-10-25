"""Task graph SWE role-turn wiring (task_048)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.agent.types import RoleResult
from cascade.board.store import read_doc, write_doc
from cascade.task.graph import (
    clear_task_graph_sessions,
    invoke_tool,
    invoke_role_turn,
    seed_task_role_models,
    set_task_run_role_fn,
)
from cascade.watchdog.model_resolve import resolve_backend
from cascade.task.wiring import clear_task_wiring_state, install_task_wiring
from cascade.task.registry import register_task_tool
from cascade.task.worktree import clear_task_runs, create_task_worktree, get_task_run
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.watchdog.events import read_events
from tests.support import TEST_MODEL_ID, approve_board_feature
from tests.support import add_doc, commit_board, make_repo


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_task_runs()
    clear_task_graph_sessions()
    clear_task_wiring_state()
    yield
    clear_task_runs()
    clear_task_graph_sessions()
    clear_task_wiring_state()


def _board_plain(tmp_path: Path, *, models: bool = True) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False, models=models)
    task_id = "task_048"
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id=task_id,
        title="Graph wiring",
        tier="task",
        status="active",
        parent="feat_001",
    )
    install_task_wiring(root)
    return root, task_id


def _board_with_worktree(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, models=True)
    (root / "README.md").write_text("init\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    task_id = "task_048"
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
    )
    add_doc(
        root,
        id=task_id,
        title="Graph wiring",
        tier="task",
        parent="feat_001",
    )
    install_task_wiring(root)
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task(task_id, "human", root=root).ok
    if get_task_run(task_id) is None:
        create_task_worktree(
            task_id,
            root=root,
            parent_rev=read_doc(task_id, root=root).meta.parent_rev,
            skills=[],
            base_ref="feat/feat_001",
        )
    task = read_doc(task_id, root=root)
    if task.meta.status == "blocked":
        task.meta.status = "active"
        write_doc(task, root=root)
    return root, task_id


def test_missing_model_id_skips_run_role(tmp_path: Path) -> None:
    root, task_id = _board_plain(tmp_path, models=False)
    called = False

    async def fake(_turn: object) -> RoleResult:
        nonlocal called
        called = True
        return RoleResult(text="nope", status="finished")

    set_task_run_role_fn(fake)
    state = invoke_role_turn(
        task_id,
        {"role": "human", "content": "implement"},
        root=root,
        feature_id="feat_001",
    )
    assert called is False
    assert not [m for m in state["messages"] if m.get("role") == "task_swe"]
    assert any(m.get("role") == "human" for m in state["messages"])


def test_seeded_swe_model_and_source_reach_run_role(tmp_path: Path) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    meta = read_doc(task_id, root=root).meta
    swe = resolve_backend("swe", meta, root=root)
    seed_task_role_models(task_id, swe=swe, root=root, feature_id="feat_001")

    captured: dict[str, str] = {}

    async def fake(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        captured["model_id"] = turn.model_id
        captured["prompt"] = turn.prompt
        return RoleResult(text="adapter-reply", status="finished")

    set_task_run_role_fn(fake)
    state = invoke_role_turn(
        task_id,
        {"role": "human", "content": "implement"},
        root=root,
        feature_id="feat_001",
    )
    swe_msg = next(m for m in state["messages"] if m.get("role") == "task_swe")
    assert swe_msg["content"] == "adapter-reply"
    assert captured["model_id"] == "proj-task"
    assert "source: project-tier" in captured["prompt"]


def test_adapter_text_becomes_swe_message(tmp_path: Path) -> None:
    root, task_id = _board_with_worktree(tmp_path)

    async def fake(_turn: object) -> RoleResult:
        return RoleResult(text="adapter-reply", status="finished")

    set_task_run_role_fn(fake)
    state = invoke_role_turn(
        task_id,
        {"role": "human", "content": "implement"},
        root=root,
        feature_id="feat_001",
        model_id=TEST_MODEL_ID,
    )
    swe = next(m for m in state["messages"] if m.get("role") == "task_swe")
    assert swe["content"] == "adapter-reply"


def test_automation_blocks_finished_turn_without_deliverable_commit(tmp_path: Path) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    with (root / "cascade.toml").open("a", encoding="utf-8") as handle:
        handle.write("\n[automation]\nenabled = true\n")

    async def fake(_turn: object) -> RoleResult:
        return RoleResult(text="done", status="finished")

    set_task_run_role_fn(fake)
    invoke_role_turn(
        task_id,
        {"role": "human", "content": "implement"},
        root=root,
        feature_id="feat_001",
        model_id=TEST_MODEL_ID,
    )

    assert read_doc(task_id, root=root).meta.status == "blocked"
    events, _ = read_events("feat_001", 0, root=root)
    failures = [event for event in events if event.type == "TaskFailed"]
    assert failures[-1].payload["reason"] == "no_task_changes"


def test_finished_provider_does_not_merge_task_already_blocked_by_red_tests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    with (root / "cascade.toml").open("a", encoding="utf-8") as handle:
        handle.write("\n[automation]\nenabled = true\n")
    run = get_task_run(task_id)
    assert run is not None
    from cascade.task.failure import fail_task

    fail_task(task_id, "tests_red", root=root)
    run.state = "awaiting_merge"

    queued: list[str] = []
    monkeypatch.setattr("cascade.task_rollup.queue_task_merge", lambda task_id, **_kw: queued.append(task_id))
    monkeypatch.setattr("cascade.task.swe_turn.has_deliverable_commit", lambda _run: True)

    from cascade.task.graph import _auto_merge_finished_task

    _auto_merge_finished_task(task_id, root)
    assert queued == []


def test_red_then_green_tests_allow_finished_provider_to_queue_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    with (root / "cascade.toml").open("a", encoding="utf-8") as handle:
        handle.write("\n[automation]\nenabled = true\n")
    from cascade.task.wiring import on_tests_finished

    on_tests_finished(task_id, {"exit_code": 1}, root=root)
    assert read_doc(task_id, root=root).meta.status == "active"
    from cascade.task.graph import _auto_merge_finished_task
    from cascade.task.swe_turn import has_deliverable_commit

    monkeypatch.setattr("cascade.task.swe_turn.has_deliverable_commit", lambda _run: True)
    _auto_merge_finished_task(task_id, root)
    retry_events, _ = read_events(task_id, 0, root=root)
    assert retry_events[-1].type == "TaskValidationRetryRequested"
    assert retry_events[-1].payload["validation_failure"] == 1

    on_tests_finished(task_id, {"exit_code": 0}, root=root)

    # An MCP subprocess records the test result durably; the supervisor's
    # process-local TaskRun has not seen its state change.
    run = get_task_run(task_id)
    assert run is not None
    run.state = "coding"

    queued: list[str] = []
    monkeypatch.setattr("cascade.task_rollup.queue_task_merge", lambda value, **_kw: queued.append(value))
    monkeypatch.setattr("cascade.task_rollup.retry_pending_task_merges", lambda _root: [])
    _auto_merge_finished_task(task_id, root)
    assert queued == [task_id]


def test_final_red_tests_retry_twice_then_block_without_queueing_merge(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    with (root / "cascade.toml").open("a", encoding="utf-8") as handle:
        handle.write("\n[automation]\nenabled = true\n")
    from cascade.task.wiring import on_tests_finished

    queued: list[str] = []
    monkeypatch.setattr("cascade.task_rollup.queue_task_merge", lambda value, **_kw: queued.append(value))
    monkeypatch.setattr("cascade.task.swe_turn.has_deliverable_commit", lambda _run: True)
    from cascade.task.graph import _auto_merge_finished_task

    from cascade.task.wiring import begin_validation_turn

    for failure in range(1, 4):
        begin_validation_turn(task_id)
        on_tests_finished(task_id, {"exit_code": 1}, root=root)
        _auto_merge_finished_task(task_id, root)
        if failure < 3:
            assert read_doc(task_id, root=root).meta.status == "active"
    assert queued == []
    assert read_doc(task_id, root=root).meta.status == "blocked"
    events, _ = read_events("feat_001", 0, root=root)
    assert [event for event in events if event.type == "TaskFailed"][-1].payload["reason"] == "tests_red"
    retry_events, _ = read_events(task_id, 0, root=root)
    corrective = [event for event in retry_events if event.type == "TaskValidationRetryRequested"]
    assert [event.payload["validation_failure"] for event in corrective] == [1, 2]


def test_recoverable_tool_error_does_not_block_task(tmp_path: Path) -> None:
    root, task_id = _board_with_worktree(tmp_path)
    _before, offset = read_events("feat_001", 0, root=root)

    def missing_file(**_kwargs: object) -> None:
        raise FileNotFoundError("agent probed the wrong path")

    register_task_tool("probe", missing_file)
    with pytest.raises(FileNotFoundError, match="wrong path"):
        invoke_tool(task_id, "probe", {}, root=root, feature_id="feat_001")

    assert read_doc(task_id, root=root).meta.status == "active"
    events, _ = read_events("feat_001", offset, root=root)
    assert not [event for event in events if event.type == "TaskFailed"]


def test_forbidden_doc_path_surfaces_failure_not_adapter_text(tmp_path: Path) -> None:
    from tests.agent import test_swe_turn as swe_turn_tests

    swe_turn_tests.test_forbidden_doc_path_fails_closed_without_commit(tmp_path, "feat_001")
