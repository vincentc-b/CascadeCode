"""A validated handoff must not invalidate its own Feature base."""

import subprocess

import pytest

from cascade.board.store import read_doc, write_doc
from cascade.task import invoke_tool
from cascade.task.action_recovery import load_action
from cascade.task.execution import execution_view, mark_queued
from cascade.task.wiring import clear_task_wiring_state, load_task_tools
from cascade.task.worktree import attach_active_task_run, clear_task_runs
from cascade.task_rollup import delivery_evidence_is_current, queued_delivery_evidence, retry_pending_task_merges
from cascade.watchdog.blockage import propagate_direct_report_blockage
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import create_integration_worktree
from tests.support import add_doc, make_repo


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=root, check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture(autouse=True)
def _isolate_runs():
    clear_task_runs()
    clear_task_wiring_state()
    yield
    clear_task_runs()
    clear_task_wiring_state()


def _delivery(tmp_path, *, gate="none", green=True):
    root = make_repo(tmp_path)
    (root / "cascade.toml").write_text("[automation]\nenabled = true\n")
    (root / ".gitignore").write_text(".cascade/\ndocs/_queue/\ndocs/_war_room/\n__pycache__/\n.pytest_cache/\n")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active", children=["feat_001"])
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active",
            parent="epic_001", children=["task_001", "task_002"])
    add_doc(root, id="task_001", title="Deliverable", tier="task", status="active", parent="feat_001")
    # Keep the parent open so its remaining gates can be checked after the
    # normal Task merge and completion reconciliation.
    add_doc(root, id="task_002", title="Independent sibling", tier="task", status="backlog", parent="feat_001")
    _git(root, "add", ".gitignore", "cascade.toml")
    _git(root, "commit", "-m", "Configure isolated validation workspace")
    feature = create_integration_worktree("feature", "feat_001", branch="feat/feat_001", base_ref="HEAD", trunk=root)
    task = create_integration_worktree("task", "task_001", branch="task/task_001", base_ref=feature.branch, trunk=root)
    if gate == "manual":
        doc = read_doc("feat_001", root=feature.path)
        doc.meta.status = "blocked"
        write_doc(doc, root=feature.path)
    propagated = propagate_direct_report_blockage(
        read_doc("feat_001", root=root), read_doc("task_001", root=root),
        "Previous Task delivery failed", root=root, incident_id="task_001:delivery:1",
    )
    assert propagated.ok
    if gate == "sibling":
        assert propagate_direct_report_blockage(
            read_doc("feat_001", root=root), read_doc("task_002", root=root),
            "Independent sibling decision", root=root, incident_id="task_002:delivery:1",
        ).ok
    if gate == "comment":
        from cascade.comments.store import comment
        comment("feat_001", "scope", "Human review required", blocking=True,
                blocks=["task_001"], author="human", root=root)
    run = attach_active_task_run("task_001", root=root)
    assert run is not None
    (task.path / "implementation.py").write_text("value = 42\n")
    (task.path / "test_delivery.py").write_text(
        "from implementation import value\ndef test_delivery():\n    assert value == " + ("42" if green else "43") + "\n"
    )
    _git(task.path, "add", "implementation.py", "test_delivery.py")
    _git(task.path, "commit", "-m", "Implement scoped Task\n\nCascade-Task: task_001")
    mark_queued("task_001", root=root)
    load_task_tools()
    return root, feature, task


@pytest.mark.parametrize("gate", ["none", "sibling", "manual", "comment"])
def test_blocked_parent_does_not_change_validated_head_during_handoff(tmp_path, gate):
    root, feature, task = _delivery(tmp_path, gate=gate)
    feature_head = _git(feature.path, "rev-parse", "HEAD")
    result = invoke_tool("task_001", "swe_run_tests",
                         {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                         root=root, feature_id="feat_001")
    assert result["exit_code"] == 0
    evidence = result["final_validation"]
    assert queued_delivery_evidence("task_001", root=root) == evidence
    assert evidence["feature_base_sha"] == feature_head
    assert _git(feature.path, "rev-parse", "HEAD") == feature_head
    assert delivery_evidence_is_current("task_001", evidence, root=root)
    assert read_doc("feat_001", root=root).meta.monitoring_blockers

    # The real finished-turn path replays the evidence before normal merge.
    from cascade.task.graph import _auto_merge_finished_task
    _auto_merge_finished_task("task_001", root)
    events, _ = read_events("feat_001", 0, root=root)
    merged = [event for event in events if event.type == "TaskMerged"]
    parent = read_doc("feat_001", root=root)
    if gate in {"manual", "comment"}:
        assert not merged
        assert read_doc("task_001", root=root).meta.status == "active"
        assert parent.meta.status == "blocked"
        assert any(b.child_id == "task_001" for b in parent.meta.monitoring_blockers)
        assert _git(feature.path, "rev-parse", "HEAD") == feature_head
    else:
        assert len(merged) == 1
        assert read_doc("task_001", root=root).meta.status == "completed"
        assert load_action("task_001:queued_merge", root=root)["recovery_state"] == "completed"
        assert (feature.path / "implementation.py").read_text() == "value = 42\n"
        assert [b.child_id for b in parent.meta.monitoring_blockers] == (["task_002"] if gate == "sibling" else [])
        assert parent.meta.status == ("blocked" if gate == "sibling" else "active")
        final_head = _git(feature.path, "rev-parse", "HEAD")
        assert retry_pending_task_merges(root) == []
        assert _git(feature.path, "rev-parse", "HEAD") == final_head
    execution = execution_view("task_001", root=root)
    assert execution.get("validation_failures", 0) == 0
    assert execution.get("last_error") != "final_validation_required"
    task_events, _ = read_events("task_001", 0, root=root)
    assert not any(event.type == "TaskValidationRetryRequested" for event in task_events)


def test_red_validation_preserves_derived_blocker_and_parent_head(tmp_path):
    root, feature, _ = _delivery(tmp_path, green=False)
    before = _git(feature.path, "rev-parse", "HEAD")
    blockers = read_doc("feat_001", root=root).meta.monitoring_blockers
    result = invoke_tool("task_001", "swe_run_tests",
                         {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                         root=root, feature_id="feat_001")
    assert result["exit_code"] != 0
    assert _git(feature.path, "rev-parse", "HEAD") == before
    assert read_doc("feat_001", root=root).meta.monitoring_blockers == blockers
    assert queued_delivery_evidence("task_001", root=root) is None
