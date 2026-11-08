"""Contract-generation and stale-delivery regressions using durable state."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import time

import pytest

from cascade.board.store import read_doc, write_doc
from cascade.feature.recovery import recovery_status, revise_task, retry_task
from cascade.task.execution import (
    execution_view,
    mark_awaiting_merge,
    mark_queued,
    mark_running,
    mark_terminal,
)
from cascade.task.supervisor_recovery import recover_orphan_delivery
from cascade.task_rollup import invalidate_task_merge, queue_task_merge
from tests.feature.test_recovery import _board as dispatched_blocked_board
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def isolate_hooks_and_inventory(monkeypatch):
    from cascade.watchdog.hooks import clear_hooks
    from cascade.task.worktree import clear_task_runs
    from cascade.agent.discovery.inventory import (
        InventoryFreshness,
        ProviderInventoryItem,
        ProviderInventoryResult,
    )
    from cascade.agent.discovery.types import DiscoveredModel

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
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr("cascade.approvals.get_provider_inventory", lambda: inventory)
    clear_hooks()
    clear_task_runs()
    yield
    clear_hooks()
    clear_task_runs()


def test_revised_permission_blocker_dispatches_once_preserving_failure_history(
    tmp_path: Path,
) -> None:
    root = dispatched_blocked_board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forbidden_commit_paths")
    before = execution_view("task_001", root=root)
    assert (
        recovery_status("task_001", feature_id="feat_001", root=root)["action"]
        == "permission"
    )
    body = read_doc("task_001", root=root).body.replace(
        "- cascade/", "- cascade/task/recovery.py\n- tests/test_task_recovery.py"
    )
    assert revise_task("task_001", body, feature_id="feat_001", root=root)
    assert revise_task("task_001", body, feature_id="feat_001", root=root) is None
    assert (
        recovery_status("task_001", feature_id="feat_001", root=root)["action"]
        == "retry"
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        results = list(
            pool.map(
                lambda _: retry_task("task_001", feature_id="feat_001", root=root),
                range(3),
            )
        )
    assert sum(result["ok"] for result in results) == 1
    after = execution_view("task_001", root=root)
    assert after["attempt"] == before["attempt"] + 1
    assert len(after["contract_revisions"]) == 1
    assert after["contract_revisions"][0]["consumed"] is True
    assert any(
        row["attempt"] == before["attempt"]
        and row["last_error"] == "forbidden_commit_paths"
        for row in after["attempt_history"]
    )

    # Repeat the same contract after another failure; replay cannot buy a new run.
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=task.meta.path.parents[3])
    mark_terminal("task_001", "failed", root=root, error="forbidden_commit_paths")
    assert revise_task("task_001", body, feature_id="feat_001", root=root) is None
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"] is False
    assert execution_view("task_001", root=root)["attempt"] == after["attempt"]


def _git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.mark.parametrize(
    "claim_owner_immediately", [True, False, "real", "restart", "conflict"]
)
def test_cached_queued_delivery_cannot_suppress_resume_after_feature_movement(
    tmp_path: Path, claim_owner_immediately: bool | str
) -> None:
    from cascade.task.graph import ensure_task_graph
    from cascade.task.checkpoint import thread_config
    from cascade.workspace.integration_worktree import create_integration_worktree

    root = make_repo(tmp_path)
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
        id="task_001",
        title="Task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    from cascade.board.store import pin_parent

    pin_parent("task_001", "feat_001", root=root)
    revision = read_doc("task_001", root=root).meta.parent_rev
    assert revision and revision != "feat_001"
    feature = create_integration_worktree(
        "feature", "feat_001", branch="feat/feat_001", base_ref="HEAD", trunk=root
    )
    task = create_integration_worktree(
        "task", "task_001", branch="task/task_001", base_ref=feature.branch, trunk=root
    )
    (task.path / "implementation.py").write_text("value = 1\n")
    (task.path / "test_delivery.py").write_text(
        "from pathlib import Path\ndef test_current_feature():\n    assert Path('feature_progress.py').read_text() == 'progress = True\\n'\n"
    )
    (task.path / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n")
    _git(task.path, "add", "implementation.py", "test_delivery.py", ".gitignore")
    _git(task.path, "commit", "-m", "Task deliverable")
    graph = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    graph.update_state(
        thread_config("task_001"),
        {
            "messages": [
                {"role": "human", "content": "Revalidate and deliver this Task."}
            ],
            "task_id": "task_001",
            "feature_id": "feat_001",
            "provider_ids": {"swe": "codex"},
            "model_ids": {"swe": "offered"},
        },
    )
    mark_queued("task_001", root=root)
    mark_awaiting_merge("task_001", root=root)
    evidence = {
        "task_id": "task_001",
        "deliverable_sha": _git(task.path, "rev-parse", "HEAD"),
        "feature_base_sha": _git(feature.path, "rev-parse", "HEAD"),
    }
    queue_task_merge("task_001", root=root, delivery_evidence=evidence)
    first = recover_orphan_delivery("task_001", root=root)
    assert (first.decision, first.reason) == (
        "already_delivered",
        "validated_delivery_already_queued",
    )
    assert recover_orphan_delivery("task_001", root=root) == first

    (feature.path / "feature_progress.py").write_text("progress = True\n")
    if claim_owner_immediately == "conflict":
        (feature.path / "implementation.py").write_text("value = 2\n")
    _git(feature.path, "add", "feature_progress.py", ".")
    _git(feature.path, "commit", "-m", "Feature advanced")
    if claim_owner_immediately == "conflict":
        from cascade.task_rollup import retry_pending_task_merges
        from cascade.task.action_recovery import load_action

        # A delivery admitted by the old validator may not contain its stamped
        # Feature base. Exercise migration of this pre-existing conflict.
        legacy_evidence = {
            **evidence,
            "feature_base_sha": _git(feature.path, "rev-parse", "HEAD"),
        }
        queue_task_merge("task_001", root=root, delivery_evidence=legacy_evidence)
        assert retry_pending_task_merges(root) == []
        action = load_action("task_001:queued_merge", root=root)
        assert action["recovery_state"] == "awaiting_owner_decision"
        assert action["recovery"]["owning_team"] == {
            "kind": "task_team",
            "work_id": "task_001",
        }
        assert action["recovery"]["evidence"]["supervisor"] == "feat_001"
        from cascade.watchdog.blockage import propagate_direct_report_blockage

        propagate_direct_report_blockage(
            read_doc("feat_001", root=root),
            read_doc("task_001", root=root),
            "semantic merge conflict",
            root=root,
            incident_id="task_001:delivery:conflict",
        )
        assert read_doc("feat_001", root=root).meta.status == "blocked"
    else:
        invalidate_task_merge("task_001", root=root)
    starts = []

    def kickoff(task_id, repo, feature_id):
        # Cross the real attach and graph checkpoint boundary with the resumed identity.
        resumed = ensure_task_graph(task_id, root=repo, feature_id=feature_id)
        assert (
            resumed.get_state(thread_config(task_id)).values["feature_id"] == "feat_001"
        )
        starts.append((task_id, feature_id))
        if claim_owner_immediately:
            mark_running(task_id, root=repo)

    if claim_owner_immediately in ("real", "restart", "conflict"):
        from cascade.task.graph import set_task_run_role_fn, clear_task_graph_sessions
        from cascade.task.wiring import load_task_tools
        from cascade.task.worktree import clear_task_runs
        from cascade.task import invoke_tool
        from cascade.agent.types import RoleResult
        from cascade.task_rollup import pending_task_merges, queued_delivery_evidence

        if claim_owner_immediately == "restart":

            def interrupted_handoff(*args):
                raise RuntimeError("supervisor exited before kickoff")

            with pytest.raises(RuntimeError, match="supervisor exited"):
                recover_orphan_delivery(
                    "task_001", root=root, kickoff=interrupted_handoff
                )
        # Simulate a fresh supervisor: rebuild both run and graph from disk.
        clear_task_runs()
        clear_task_graph_sessions()
        load_task_tools()
        validations = []

        async def provider(turn):
            starts.append(("task_001", "feat_001"))
            assert turn.cwd == task.path
            if claim_owner_immediately == "conflict":
                refused = invoke_tool(
                    "task_001",
                    "swe_run_tests",
                    {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                    root=root,
                    feature_id="feat_001",
                )
                integration = refused["recovery"]
                assert not integration["ok"]
                assert integration["conflict_paths"] == ["implementation.py"]
                invoke_tool(
                    "task_001",
                    "swe_write",
                    {
                        "path": "implementation.py",
                        "content": "task_value = 1\nfeature_value = 2\n",
                    },
                    root=root,
                    feature_id="feat_001",
                )
                invoke_tool(
                    "task_001",
                    "swe_commit",
                    {"message": "Preserve both task and Feature values"},
                    root=root,
                    feature_id="feat_001",
                )
            # Only the provider is stubbed: use real scoped test/tool/queue boundaries.
            result = invoke_tool(
                "task_001",
                "swe_run_tests",
                {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                root=root,
                feature_id="feat_001",
            )
            validations.append(result)
            return RoleResult(text="Validated the resumed delivery.", status="finished")

        set_task_run_role_fn(provider)
        if claim_owner_immediately == "conflict":
            from cascade.workspace.kickoff import kickoff_graph_queue_event

            kickoff_graph_queue_event("task_001", root=root, by="watchdog")
        elif claim_owner_immediately == "restart":
            from cascade.workspace.up import resume_interrupted_task_runs
            from cascade.workspace.kickoff import wait_for_background_kickoffs

            assert resume_interrupted_task_runs(root) == [("task_001", "feat_001")]
            assert wait_for_background_kickoffs()
            assert resume_interrupted_task_runs(root) == []
        else:
            recovered = recover_orphan_delivery(
                "task_001", root=root, observed_incident=first.incident_id
            )
            assert recovered.decision == "resume_workspace"
        assert starts == [("task_001", "feat_001")], (
            ensure_task_graph("task_001", root=root)
            .get_state(thread_config("task_001"))
            .values
        )
        assert len(validations) == 1 and validations[0]["exit_code"] == 0
        assert (task.path / "feature_progress.py").is_file()
        replacement = queued_delivery_evidence("task_001", root=root)
        assert replacement["feature_base_sha"] == _git(
            feature.path, "rev-parse", "HEAD"
        )
        assert replacement != evidence
        assert pending_task_merges(root) == {"task_001"}
        assert (
            recover_orphan_delivery("task_001", root=root).decision
            == "already_delivered"
        )
        assert len(starts) == 1
        with pytest.raises(ValueError, match="Feature identity"):
            ensure_task_graph("task_001", root=root, feature_id=revision)
        from cascade.task_rollup import retry_pending_task_merges
        from cascade.task.action_recovery import load_action
        from cascade.watchdog.events import read_events
        from cascade.war_room.recovery_incident import recovery_incidents_by_work_id

        assert retry_pending_task_merges(root) == ["task_001"]
        assert read_doc("task_001", root=root).meta.status == "completed"
        completed_action = load_action("task_001:queued_merge", root=root)
        assert completed_action["recovery_state"] == "completed"
        if claim_owner_immediately == "conflict":
            assert (
                feature.path / "implementation.py"
            ).read_text() == "task_value = 1\nfeature_value = 2\n"
            assert completed_action["attempt_count"] >= 2
            assert all(
                decision["state"] == "resolved"
                for decision in completed_action["owner_decisions"]
            )
            assert not read_doc("feat_001", root=root).meta.monitoring_blockers
        assert "task_001" not in recovery_incidents_by_work_id(root=root)
        assert pending_task_merges(root) == set()
        feature_head = _git(feature.path, "rev-parse", "HEAD")
        assert retry_pending_task_merges(root) == []
        assert _git(feature.path, "rev-parse", "HEAD") == feature_head
        events, _ = read_events("feat_001", 0, root=root)
        assert sum(event.type == "TaskMerged" for event in events) == 1
        return

    recovered = recover_orphan_delivery(
        "task_001", root=root, observed_incident=first.incident_id, kickoff=kickoff
    )
    assert recovered.incident_id != first.incident_id
    assert recovered.decision == "resume_workspace"
    assert starts == [("task_001", "feat_001")]
    replay = recover_orphan_delivery(
        "task_001", root=root, observed_incident=first.incident_id, kickoff=kickoff
    )
    if claim_owner_immediately:
        assert replay.decision == "no_op_live_owner"
    assert len(starts) == 1, (
        "a queued resume awaiting its worker lease must not launch again"
    )
    with pytest.raises(ValueError, match="Feature identity"):
        ensure_task_graph("task_001", root=root, feature_id=revision)
