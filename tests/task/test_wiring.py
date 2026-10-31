"""Task boot wiring integration (task_037)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

import cascade.task.boot as task_boot
import cascade.task.graph as task_graph
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.task.boot import install_task_boot_hook
from cascade.task.failure import fail_task
from cascade.task.registry import clear_task_tools, task_tools
from cascade.task.wiring import (
    clear_task_wiring_state,
    install_task_wiring,
    load_task_tools,
)
from cascade.task.worktree import clear_task_runs, get_task_run, worktree_path
from cascade.task.action_recovery import load_action
from cascade.task_rollup import pending_task_merges
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks, invoke_boot
from cascade.watchdog.hooks import _boot
from tests.support import add_doc, make_repo, write_swe_default_role_skills


@pytest.fixture(autouse=True)
def _wiring_test_isolation() -> None:
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()
    task_graph._graph_cache.clear()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None
    yield
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()
    task_graph._graph_cache.clear()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None


def _branch_exists(root: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "show-ref", "--verify", f"refs/heads/{branch}"],
        cwd=root,
        capture_output=True,
    )
    return result.returncode == 0


def _task_board(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, models=True)
    write_swe_default_role_skills(root)
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
        id="task_037",
        title="Wiring task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_037", "feat_001", root=root)
    return root, "task_037"


def test_boot_wiring_integration(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, task_id = _task_board(tmp_path)

    pushes: list[list[str]] = []
    real_run = subprocess.run

    def guarded_run(args: list[str], *a: object, **kw: object) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "git" and "push" in args:
            pushes.append(list(args))
        return real_run(args, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(subprocess, "run", guarded_run)

    install_task_boot_hook(root)
    install_task_wiring(root)

    task_hooks = _boot["task"]
    boot_indices = [i for i, fn in enumerate(task_hooks) if fn.__name__ == "boot_task"]
    wired_indices = [
        i for i, fn in enumerate(task_hooks) if fn.__name__ == "boot_task_wired"
    ]
    assert len(boot_indices) == 1
    assert len(wired_indices) == 1
    assert boot_indices[0] < wired_indices[0]

    invoke_boot("task", task_id)

    wt = worktree_path(task_id, root=root)
    assert wt.is_dir()
    assert _branch_exists(root, f"task/{task_id}")

    expected_tools = (
        "swe_read",
        "swe_write",
        "read_doc",
        "swe_run_tests",
        "swe_commit",
        "fail_task",
    )
    assert all(name in task_tools() for name in expected_tools)

    events, _ = read_events("feat_001", 0, root=root)
    activated = [e for e in events if e.type == "TaskActivated"]
    assert len(activated) == 1
    assert activated[0].payload["task_id"] == task_id

    assert pushes == []

    run = get_task_run(task_id)
    assert run is not None
    assert run.state == "coding"

    load_task_tools()
    from cascade.task import invoke_tool

    wt = worktree_path(task_id, root=root)
    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_ok.py"]},
        root=root,
        feature_id="feat_001",
    )
    assert result["exit_code"] == 0

    run_after = get_task_run(task_id)
    assert run_after is not None
    assert run_after.state == "awaiting_merge"

    toasts, _ = read_events("war_room", 0, root=root)
    ready = [e for e in toasts if e.payload.get("kind") == "task_ready"]
    assert len(ready) == 1
    assert ready[0].payload["id"] == task_id

    fail_task(task_id, "integration_cleanup", root=root)
    assert wt.exists()
    failed_run = get_task_run(task_id)
    assert failed_run is not None
    assert failed_run.state == "failed"
    assert _branch_exists(root, f"task/{task_id}")


def test_redispatch_after_fail_task_recreates_worktree(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    assert get_task_run(task_id) is not None
    assert get_task_run(task_id).state == "coding"
    branch = f"task/{task_id}"

    fail_task(task_id, "first_failure", root=root)
    failed_run = get_task_run(task_id)
    assert failed_run is not None
    assert failed_run.state == "failed"
    failed_worktree = failed_run.worktree
    assert failed_worktree.is_dir()
    assert _branch_exists(root, branch)

    invoke_boot("task", task_id)
    run = get_task_run(task_id)
    assert run is not None
    assert run.state == "coding"
    assert run.worktree == failed_worktree
    assert worktree_path(task_id, root=root).is_dir()
    assert _branch_exists(root, branch)


def test_invoke_tool_green_tests_awaiting_merge(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    wt = worktree_path(task_id, root=root)
    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    from cascade.task import invoke_tool

    invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_ok.py"]},
        root=root,
        feature_id="feat_001",
    )
    assert get_task_run(task_id).state == "awaiting_merge"
    toasts, _ = read_events("war_room", 0, root=root)
    assert any(e.payload.get("kind") == "task_ready" for e in toasts)


def test_green_tests_persist_evidence_and_queue_before_ready(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    wt = worktree_path(task_id, root=root)
    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    from cascade.task import invoke_tool

    invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_ok.py"]},
        root=root,
        feature_id="feat_001",
    )

    action = load_action(f"{task_id}:queued_merge", root=root)
    assert action is not None
    evidence = action["metadata"]["final_validation"]
    run = get_task_run(task_id)
    assert run is not None
    deliverable = subprocess.run(
        ["git", "rev-parse", run.branch], cwd=root, text=True, capture_output=True, check=True
    ).stdout.strip()
    assert evidence == {
        "task_id": task_id,
        "deliverable_sha": deliverable,
        "feature_base_sha": run.base_sha,
    }
    assert task_id in pending_task_merges(root)
    assert run.state == "awaiting_merge"


def test_queue_failure_does_not_publish_ready_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)
    wt = worktree_path(task_id, root=root)
    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    monkeypatch.setattr(
        "cascade.task_rollup.queue_task_merge",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("queue unavailable")),
    )

    from cascade.task import invoke_tool

    with pytest.raises(OSError, match="queue unavailable"):
        invoke_tool(
            task_id,
            "swe_run_tests",
            {"cmd": ["python3", "-m", "pytest", "-q", "test_ok.py"]},
            root=root,
            feature_id="feat_001",
        )
    run = get_task_run(task_id)
    assert run is not None
    assert run.state == "testing"
    events, _ = read_events("war_room", 0, root=root)
    assert not any(event.payload.get("kind") == "task_ready" for event in events)


def test_invoke_tool_failing_pytest_fails_without_retry(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    wt = worktree_path(task_id, root=root)
    (wt / "test_bad.py").write_text("def test_bad():\n    assert False\n", encoding="utf-8")

    from cascade.task import invoke_tool

    result = invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_bad.py"]},
        root=root,
        feature_id="feat_001",
    )
    assert result["exit_code"] != 0

    events, _ = read_events("feat_001", 0, root=root)
    assert not [e for e in events if e.type == "TaskFailed"]
    assert read_doc(task_id, root=root).meta.status == "active"
    assert get_task_run(task_id).state == "testing"


def test_invoke_tool_infra_retries_at_most_twice(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    from cascade.task import invoke_tool, register_task_tool

    calls = {"n": 0}

    def flaky(**_kwargs: object) -> str:
        calls["n"] += 1
        raise TimeoutError("transient")

    register_task_tool("flaky", flaky)

    with pytest.raises(TimeoutError):
        invoke_tool(task_id, "flaky", {}, root=root, feature_id="feat_001")

    assert calls["n"] == 3
    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"] == "infra_error"


def test_stale_parent_rev_skips_worktree(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    stale_rev = read_doc(task_id, root=root).meta.parent_rev
    assert stale_rev is not None

    feature = read_doc("feat_001", root=root)
    feature.body = feature.body + "\nRevised feature.\n"
    write_doc(feature, root=root)

    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    wt = worktree_path(task_id, root=root)
    assert not wt.exists()
    assert get_task_run(task_id) is None
