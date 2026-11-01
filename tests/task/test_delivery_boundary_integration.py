"""End-to-end coverage for the durable task delivery boundary."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import cascade.task.boot as task_boot
import cascade.task.graph as task_graph
from cascade.board.store import pin_parent
from cascade.task import invoke_tool
from cascade.task.action_recovery import load_action
from cascade.task.boot import install_task_boot_hook
from cascade.task.registry import clear_task_tools
from cascade.task_rollup import pending_task_merges
from cascade.task.wiring import (
    clear_task_wiring_state,
    enqueue_validated_delivery,
    install_task_wiring,
    restore_active_task_runs,
)
from cascade.task.worktree import clear_task_runs, get_task_run, worktree_path
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks, invoke_boot
from tests.support import add_doc, make_repo, write_swe_default_role_skills


@pytest.fixture(autouse=True)
def _delivery_boundary_isolation() -> None:
    _clear_process_state()
    yield
    _clear_process_state()


def _clear_process_state() -> None:
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()
    task_graph._graph_cache.clear()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None


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
        title="Delivery boundary task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_037", "feat_001", root=root)
    subprocess.run(["git", "branch", "feat/feat_001"], cwd=root, check=True)
    return root, "task_037"


def _boot_task(root: Path, task_id: str) -> None:
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)


def _commit_deliverable(root: Path, task_id: str, name: str = "test_ok.py") -> None:
    worktree = worktree_path(task_id, root=root)
    worktree.joinpath(".gitignore").write_text("__pycache__/\n", encoding="utf-8")
    worktree.joinpath(name).write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    invoke_tool(
        task_id,
        "swe_commit",
        {"message": "add delivery boundary fixture"},
        root=root,
        feature_id="feat_001",
    )


def _validate_green(root: Path, task_id: str, name: str = "test_ok.py") -> dict[str, object]:
    result = invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", name]},
        root=root,
        feature_id="feat_001",
    )
    assert isinstance(result, dict)
    assert result["exit_code"] == 0
    assert result.get("final_validation") is not None
    return result


def _ready_events(root: Path) -> list[object]:
    events, _ = read_events("war_room", 0, root=root)
    return [event for event in events if event.payload.get("kind") == "task_ready"]


def _queued_evidence(root: Path, task_id: str) -> dict[str, str]:
    action = load_action(f"{task_id}:queued_merge", root=root)
    assert action is not None
    evidence = action["metadata"]["final_validation"]
    assert isinstance(evidence, dict)
    return evidence


def _restart(root: Path) -> None:
    """Model a drained supervisor: preserve disk state but discard process state."""

    _clear_process_state()
    install_task_boot_hook(root)
    install_task_wiring(root)


def test_restart_after_commit_requires_fresh_validation_before_ready(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    _boot_task(root, task_id)
    _commit_deliverable(root, task_id)

    assert pending_task_merges(root) == set()
    assert _ready_events(root) == []

    _restart(root)
    assert restore_active_task_runs(root) == [(task_id, "feat_001")]
    restored = get_task_run(task_id)
    assert restored is not None
    assert restored.state == "coding"
    assert pending_task_merges(root) == set()
    assert _ready_events(root) == []

    _validate_green(root, task_id)
    assert pending_task_merges(root) == {task_id}
    assert get_task_run(task_id).state == "awaiting_merge"
    assert len(_ready_events(root)) == 1


def test_restart_after_validation_preserves_durable_delivery_without_restarting_task(
    tmp_path: Path,
) -> None:
    root, task_id = _task_board(tmp_path)
    _boot_task(root, task_id)
    _commit_deliverable(root, task_id)
    _validate_green(root, task_id)
    evidence_before = _queued_evidence(root, task_id)

    _restart(root)

    # The pending queue is the durable handoff to downstream merge processing;
    # a fresh supervisor must not start another SWE run for the same delivery.
    assert restore_active_task_runs(root) == []
    assert get_task_run(task_id) is None
    assert pending_task_merges(root) == {task_id}
    assert _queued_evidence(root, task_id) == evidence_before
    assert len(_ready_events(root)) == 1


def test_red_final_validation_does_not_publish_delivery(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    _boot_task(root, task_id)
    _commit_deliverable(root, task_id, "test_bad.py")
    worktree_path(task_id, root=root).joinpath("test_bad.py").write_text(
        "def test_bad():\n    assert False\n", encoding="utf-8"
    )
    invoke_tool(
        task_id,
        "swe_commit",
        {"message": "make validation red"},
        root=root,
        feature_id="feat_001",
    )

    result = invoke_tool(
        task_id,
        "swe_run_tests",
        {"cmd": ["python3", "-m", "pytest", "-q", "test_bad.py"]},
        root=root,
        feature_id="feat_001",
    )

    assert result["exit_code"] != 0
    assert pending_task_merges(root) == set()
    assert get_task_run(task_id).state == "testing"
    assert _ready_events(root) == []


def test_changed_deliverable_or_feature_base_revalidates_with_new_evidence(
    tmp_path: Path,
) -> None:
    root, task_id = _task_board(tmp_path)
    _boot_task(root, task_id)
    _commit_deliverable(root, task_id)
    _validate_green(root, task_id)
    first = _queued_evidence(root, task_id)

    worktree_path(task_id, root=root).joinpath("test_ok.py").write_text(
        "def test_ok():\n    assert 2 + 2 == 4\n", encoding="utf-8"
    )
    invoke_tool(
        task_id,
        "swe_commit",
        {"message": "amend delivery boundary fixture"},
        root=root,
        feature_id="feat_001",
    )
    assert pending_task_merges(root) == set()
    assert get_task_run(task_id).state == "coding"

    _validate_green(root, task_id)
    after_deliverable_change = _queued_evidence(root, task_id)
    assert after_deliverable_change["deliverable_sha"] != first["deliverable_sha"]
    assert after_deliverable_change["feature_base_sha"] == first["feature_base_sha"]

    root.joinpath("feature_change.py").write_text("FEATURE_CHANGE = True\n", encoding="utf-8")
    subprocess.run(["git", "add", "feature_change.py"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "advance feature base"], cwd=root, check=True)
    subprocess.run(["git", "branch", "-f", "feat/feat_001", "HEAD"], cwd=root, check=True)

    assert not enqueue_validated_delivery(task_id, root=root)
    assert pending_task_merges(root) == set()
    assert get_task_run(task_id).state == "coding"
    assert not subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree_path(task_id, root=root),
        capture_output=True,
        text=True,
        check=True,
    ).stdout

    _validate_green(root, task_id)
    refreshed = _queued_evidence(root, task_id)
    assert refreshed["deliverable_sha"] == after_deliverable_change["deliverable_sha"]
    assert refreshed["feature_base_sha"] != after_deliverable_change["feature_base_sha"]
    assert pending_task_merges(root) == {task_id}
    assert get_task_run(task_id).state == "awaiting_merge"
    assert len(_ready_events(root)) == 3


def test_replaying_unchanged_green_evidence_keeps_one_durable_queue_entry(tmp_path: Path) -> None:
    root, task_id = _task_board(tmp_path)
    _boot_task(root, task_id)
    _commit_deliverable(root, task_id)
    _validate_green(root, task_id)
    evidence = _queued_evidence(root, task_id)

    assert enqueue_validated_delivery(task_id, root=root)
    assert enqueue_validated_delivery(task_id, root=root)

    queue_file = root / ".cascade" / "pending-task-merges.json"
    assert json.loads(queue_file.read_text(encoding="utf-8")) == [task_id]
    assert pending_task_merges(root) == {task_id}
    assert _queued_evidence(root, task_id) == evidence
    assert get_task_run(task_id).state == "awaiting_merge"
    assert len(_ready_events(root)) == 1
