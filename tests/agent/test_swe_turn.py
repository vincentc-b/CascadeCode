"""SWE worktree turn: cwd, path gate, commit, and failure routing (task_047)."""

from __future__ import annotations

import subprocess
from pathlib import Path
import pytest

from cascade.agent import CursorAgentError, RoleResult
from cascade.board.store import read_doc, write_doc
from cascade.task.registry import clear_task_tools
from cascade.task.swe_mcp import MCP_SERVER_NAME, build_swe_mcp_servers
from cascade.task.swe_turn import (
    build_swe_role_turn,
    run_swe_turn_sync,
    worktree_diff_committable,
)
import sys
from cascade.task.wiring import clear_task_wiring_state, get_infra_attempt, install_task_wiring
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _swe_turn_isolation() -> None:
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()
    yield
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _board_with_worktree(tmp_path: Path) -> tuple[Path, str, object]:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    task_id = "task_047"
    add_doc(
        root,
        id=task_id,
        title="SWE turn task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    task = read_doc(task_id, root=root)
    task.meta.parent_rev = read_doc("feat_001", root=root).sha
    write_doc(task, root=root)
    run = create_task_worktree(
        task_id,
        root=root,
        parent_rev=read_doc(task_id, root=root).meta.parent_rev,
        skills=[],
    )
    install_task_wiring(root)
    return root, task_id, run


def test_build_swe_role_turn_uses_worktree_cwd(tmp_path: Path) -> None:
    root, task_id, run = _board_with_worktree(tmp_path)
    turn = build_swe_role_turn(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="implement",
        root=root,
    )
    assert turn.cwd == run.worktree.resolve()
    assert turn.role == "swe"
    assert turn.tools == []
    assert turn.custom_tools is not None
    assert set(turn.custom_tools) == {
        "swe_read",
        "swe_write",
        "read_doc",
        "swe_run_tests",
        "swe_commit",
        "fail_task",
    }


def test_build_swe_role_turn_uses_stdio_mcp_for_cli_provider(tmp_path: Path) -> None:
    root, task_id, run = _board_with_worktree(tmp_path)
    turn = build_swe_role_turn(
        task_id,
        provider="codex",
        model_id="gpt-5.3-codex",
        prompt="implement",
        root=root,
        flex_mode=True,
    )
    assert turn.cwd == run.worktree.resolve()
    assert turn.flex_mode is True
    assert turn.custom_tools is None
    mcp = turn.tools[MCP_SERVER_NAME]
    assert mcp["command"] == sys.executable
    assert mcp["args"] == ["-m", "cascade.task.swe_mcp_stdio"]
    assert "CASCADE_TASK_MCP_CONFIG" in mcp["env"]


def test_build_swe_mcp_servers_stdio_module(tmp_path: Path) -> None:
    root, task_id, _run = _board_with_worktree(tmp_path)
    servers = build_swe_mcp_servers(task_id, root=root)
    cfg = servers[MCP_SERVER_NAME]
    assert cfg["command"] == sys.executable
    assert "-m" in cfg["args"]
    assert cfg["args"][-1] == "cascade.task.swe_mcp_stdio"


def test_happy_path_commits_on_task_branch(tmp_path: Path) -> None:
    root, task_id, run = _board_with_worktree(tmp_path)
    wt = run.worktree

    async def fake_run(_turn: object) -> RoleResult:
        patch = wt / "cascade" / "added.py"
        patch.parent.mkdir(parents=True, exist_ok=True)
        patch.write_text("x = 1\n", encoding="utf-8")
        return RoleResult(text="done", status="finished")

    outcome = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="ship it",
        root=root,
        run_role_fn=fake_run,
    )

    assert outcome.failed_closed is False
    assert outcome.commit_sha is not None
    assert len(outcome.commit_sha) == 40
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == f"task/{task_id}"


@pytest.mark.parametrize("doc_id", ["epic_001", "feat_001"])
def test_forbidden_doc_path_fails_closed_without_commit(
    tmp_path: Path, doc_id: str
) -> None:
    root, task_id, run = _board_with_worktree(tmp_path)
    wt = run.worktree
    doc = read_doc(doc_id, root=root)
    rel = doc.meta.path.relative_to(root)

    async def fake_run(_turn: object) -> RoleResult:
        target = wt / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# touched\n", encoding="utf-8")
        return RoleResult(text="oops", status="finished")

    outcome = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="bad edit",
        root=root,
        commit_message="should not land",
        run_role_fn=fake_run,
    )

    assert outcome.failed_closed is True
    assert outcome.commit_sha is None
    assert outcome.failure_reason == "forbidden_commit_paths"
    assert read_doc(task_id, root=root).meta.status == "blocked"
    log = subprocess.run(
        ["git", "log", "--oneline", f"task/{task_id}"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "should not land" not in log


def test_worktree_diff_committable_matches_guard(tmp_path: Path) -> None:
    root, task_id, run = _board_with_worktree(tmp_path)
    wt = run.worktree
    patch = wt / "ok.py"
    patch.write_text("v = 1\n", encoding="utf-8")
    assert worktree_diff_committable(task_id, run, root=root) is True

    feature = read_doc("feat_001", root=root)
    rel = feature.meta.path.relative_to(root)
    target = wt / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# no\n", encoding="utf-8")
    assert worktree_diff_committable(task_id, run, root=root) is False


def test_retryable_startup_classified_as_infra_retry(tmp_path: Path) -> None:
    root, task_id, _run = _board_with_worktree(tmp_path)
    calls = {"n": 0}

    async def flaky_startup(_turn: object) -> RoleResult:
        calls["n"] += 1
        raise CursorAgentError("auth flake", retryable=True)

    first = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="try",
        root=root,
        run_role_fn=flaky_startup,
    )
    assert first.may_retry is True
    assert first.failed_closed is False
    assert get_infra_attempt(task_id) == 1

    second = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="try again",
        root=root,
        run_role_fn=flaky_startup,
    )
    assert second.may_retry is True
    assert get_infra_attempt(task_id) == 2

    third = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="try third",
        root=root,
        run_role_fn=flaky_startup,
    )
    assert third.may_retry is False
    assert third.failed_closed is True
    assert calls["n"] == 3
    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "infra_error"


def test_run_error_fails_closed_as_spec(tmp_path: Path) -> None:
    root, task_id, _run = _board_with_worktree(tmp_path)

    async def run_failed(_turn: object) -> RoleResult:
        return RoleResult(text="agent error", status="error")

    outcome = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="fail run",
        root=root,
        run_role_fn=run_failed,
    )

    assert outcome.failed_closed is True
    assert outcome.may_retry is False
    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "swe_run_error"


def test_non_retryable_startup_fails_closed(tmp_path: Path) -> None:
    root, task_id, _run = _board_with_worktree(tmp_path)

    async def bad_startup(_turn: object) -> RoleResult:
        raise CursorAgentError("invalid model", retryable=False)

    outcome = run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="bad",
        prompt="nope",
        root=root,
        run_role_fn=bad_startup,
    )

    assert outcome.failed_closed is True
    assert outcome.may_retry is False
    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "spec_error"
