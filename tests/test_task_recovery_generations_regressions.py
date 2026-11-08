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
from cascade.task_rollup import queue_task_merge
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
                provider_id="cursor",
                display_name="Cursor",
                models=(
                    DiscoveredModel(id="proj-epic", display_name="Project Epic"),
                    DiscoveredModel(id="proj-feature", display_name="Project Feature"),
                    DiscoveredModel(id="proj-task", display_name="Project Task"),
                ),
            ),
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


def test_audit_requeues_lost_validated_delivery_through_original_action(
    tmp_path: Path, monkeypatch
) -> None:
    from cascade.boss.merge import MergeResult
    from cascade.task.action_recovery import load_action
    from cascade.task_rollup import (
        invalidate_task_merge,
        pending_task_merges,
        retry_pending_task_merges,
    )
    from cascade.watchdog.audit import project_audit_observation
    from cascade.watchdog.audit_recovery import dispatch_audit_recovery
    from cascade.watchdog.dispatch import dispatch_task
    from cascade.watchdog.events import read_events
    from cascade.workspace.integration_worktree import create_integration_worktree

    root = make_repo(tmp_path, models=True)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
        children=["feat_001"],
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
        children=["task_001", "task_002"],
    )
    add_doc(
        root,
        id="task_001",
        title="Delivered task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    add_doc(
        root,
        id="task_002",
        title="Dependent task",
        tier="task",
        parent="feat_001",
        depends_on=["task_001"],
    )
    _git(root, "add", ".")
    _git(root, "commit", "-m", "Create recovery board")
    feature = create_integration_worktree(
        "feature", "feat_001", branch="feat/feat_001", base_ref="HEAD", trunk=root
    )
    task = create_integration_worktree(
        "task", "task_001", branch="task/task_001", base_ref=feature.branch, trunk=root
    )
    (task.path / "delivery.py").write_text("delivered = True\n")
    _git(task.path, "add", "delivery.py")
    _git(task.path, "commit", "-m", "Validated task delivery")
    mark_queued("task_001", root=root)
    mark_awaiting_merge("task_001", root=root)
    evidence = {
        "task_id": "task_001",
        "deliverable_sha": _git(task.path, "rev-parse", "HEAD"),
        "feature_base_sha": _git(feature.path, "rev-parse", "HEAD"),
    }
    queue_task_merge("task_001", root=root, delivery_evidence=evidence)

    # Reproduce the original delivery incident: one transient canonical merge
    # refusal followed by loss of only the scheduling index. The durable action
    # and exact validation evidence remain authoritative.
    with monkeypatch.context() as busy:
        busy.setattr(
            "cascade.boss.merge.merge_task_branch",
            lambda *_a, **_k: MergeResult(ok=False, reason="busy"),
        )
        assert retry_pending_task_merges(root) == []
    original = load_action("task_001:queued_merge", root=root)
    assert original is not None
    assert original["recovery_state"] == "retryable"
    assert original["attempt_count"] == 1
    invalidate_task_merge("task_001", root=root)
    assert pending_task_merges(root) == set()

    user_work = root / "user-notes.txt"
    user_work.write_text("keep this work exactly as written\n")
    observation = project_audit_observation("task_001", root=root)
    assert (observation.classification, observation.reason) == (
        "proven_incident",
        "validated_delivery_missing",
    )

    assert dispatch_audit_recovery(root, "task_001")
    assert pending_task_merges(root) == {"task_001"}
    requeued = load_action("task_001:queued_merge", root=root)
    assert requeued is not None
    assert requeued["action_id"] == original["action_id"]
    assert requeued["attempt_count"] == 1
    assert requeued["metadata"]["final_validation"] == evidence

    assert retry_pending_task_merges(root) == ["task_001"]
    assert read_doc("task_001", root=root).meta.status == "completed"
    completed = load_action("task_001:queued_merge", root=root)
    assert completed is not None
    assert completed["action_id"] == original["action_id"]
    assert completed["recovery_state"] == "completed"
    assert completed["attempt_count"] == 2
    assert pending_task_merges(root) == set()
    assert retry_pending_task_merges(root) == []
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TaskMerged" for event in events) == 1

    released = dispatch_task("task_002", "human", root=root)
    assert released.ok
    assert read_doc("task_002", root=feature.path).meta.status == "active"
    assert user_work.read_text() == "keep this work exactly as written\n"


@pytest.mark.parametrize(
    "claim_owner_immediately",
    [True, False, "real", "restart", "conflict", "semantic_restart"],
)
def test_cached_queued_delivery_cannot_suppress_resume_after_feature_movement(
    tmp_path: Path, claim_owner_immediately: bool | str, monkeypatch
) -> None:
    from cascade.task.graph import ensure_task_graph
    from cascade.task.checkpoint import thread_config
    from cascade.workspace.integration_worktree import create_integration_worktree

    semantic = claim_owner_immediately == "semantic_restart"
    conflict = claim_owner_immediately in {"conflict", "semantic_restart"}
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
    if semantic:
        (task.path / "implementation.py").write_text(
            "from threading import RLock\nprocess_lock = RLock()\ndef guarded(value):\n    with process_lock:\n        return value\n"
        )
        (task.path / "test_delivery.py").write_text(
            "import pytest\nfrom implementation import guarded\n@pytest.mark.parametrize('value', range(11))\ndef test_guarded(value):\n    assert guarded(value) == value\n"
        )
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

    # Preserve the real delivery queue through two transient target refusals,
    # then let ordinary periodic maintenance invalidate it when the base moves.
    from cascade.task_rollup import retry_pending_task_merges
    from cascade.boss.merge import MergeResult

    with monkeypatch.context() as busy_target:
        busy_target.setattr(
            "cascade.boss.merge.merge_task_branch",
            lambda *a, **k: MergeResult(ok=False, reason="busy"),
        )
        assert retry_pending_task_merges(root) == []
        assert retry_pending_task_merges(root) == []

    (feature.path / "feature_progress.py").write_text("progress = True\n")
    if conflict:
        (feature.path / "implementation.py").write_text(
            "from threading import RLock\nrecovery_ledger_lock = RLock()\ndef guarded(value):\n    with recovery_ledger_lock:\n        return value\n"
            if semantic
            else "value = 2\n"
        )
    _git(feature.path, "add", "feature_progress.py", ".")
    _git(feature.path, "commit", "-m", "Feature advanced")
    if conflict:
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
        if semantic:
            add_doc(
                root,
                id="task_002",
                title="Sibling blocker",
                tier="task",
                status="blocked",
                parent="feat_001",
            )
            propagate_direct_report_blockage(
                read_doc("feat_001", root=root),
                read_doc("task_002", root=root),
                "Independent sibling incident",
                root=root,
                incident_id="task_002:delivery:conflict",
            )
            from cascade.task.action_recovery import acknowledge_team_recovery

            acknowledge_team_recovery("task_001", root=root)
            assert load_action("task_001:queued_merge", root=root)["recovery"][
                "routing_marker"
            ]["acknowledged_at"]
    else:
        assert retry_pending_task_merges(root) == []
        from cascade.task_rollup import pending_task_merges

        assert "task_001" not in pending_task_merges(root)
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

    if claim_owner_immediately in ("real", "restart", "conflict", "semantic_restart"):
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
            if conflict:
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
                        "content": (
                            "from threading import RLock\nrecovery_ledger_lock = RLock()\ndef guarded(value):\n    with process_lock:\n        return value\n"
                            if semantic
                            else "task_value = 1\nfeature_value = 2\n"
                        ),
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
                if semantic:
                    failed = invoke_tool(
                        "task_001",
                        "swe_run_tests",
                        {"cmd": ["python3", "-m", "pytest", "-q", "test_delivery.py"]},
                        root=root,
                        feature_id="feat_001",
                    )
                    assert failed["exit_code"] != 0
                    assert (
                        "process_lock" in failed["output"]
                        and "11 failed" in failed["output"]
                    )
                    assert "task_001" not in pending_task_merges(root)
                    invoke_tool(
                        "task_001",
                        "swe_write",
                        {
                            "path": "implementation.py",
                            "content": "from threading import RLock\nrecovery_ledger_lock = RLock()\ndef guarded(value):\n    with recovery_ledger_lock:\n        return value\n",
                        },
                        root=root,
                        feature_id="feat_001",
                    )
                    invoke_tool(
                        "task_001",
                        "swe_commit",
                        {"message": "Use the canonical recovery ledger lock"},
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
        if conflict:
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
        if conflict:
            delivered = (feature.path / "implementation.py").read_text()
            if semantic:
                assert "with recovery_ledger_lock:" in delivered
                assert "11 passed" in validations[0]["output"]
            else:
                assert delivered == "task_value = 1\nfeature_value = 2\n"
            assert completed_action["attempt_count"] >= 2
            assert all(
                decision["state"] == "resolved"
                for decision in completed_action["owner_decisions"]
            )
            blockers = read_doc("feat_001", root=root).meta.monitoring_blockers
            if semantic:
                assert [item.child_id for item in blockers] == ["task_002"]
                assert read_doc("feat_001", root=root).meta.status == "blocked"
            else:
                assert not blockers
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


@pytest.mark.parametrize("edit", ["cosmetic", "same_scope", "external_permission"])
def test_contract_edit_cannot_buy_an_unchanged_or_unauthorized_retry(tmp_path, edit):
    root = dispatched_blocked_board(tmp_path)
    error = (
        "permission denied by forge"
        if edit == "external_permission"
        else "forbidden_commit_paths"
    )
    mark_terminal("task_001", "failed", root=root, error=error)
    original = read_doc("task_001", root=root).body
    if edit == "external_permission":
        revised = original.replace("- cascade/", "- app.py")
    elif edit == "same_scope":
        revised = original.replace(
            "Notes for the implementer.", "Please try the same paths again."
        )
    else:
        revised = original.replace(
            "Notes for the implementer.", "Notes  for the implementer.\n"
        )
    assert revise_task("task_001", revised, feature_id="feat_001", root=root)
    from cascade.watchdog.dispatch import dispatch_task

    assert not retry_task("task_001", feature_id="feat_001", root=root)["ok"]
    assert (
        dispatch_task("task_001", "boss", root=root).reason
        == "task_contract_revision_required"
    )
    assert execution_view("task_001", root=root)["attempt"] == 1


def test_revised_task_preserves_scoped_dirty_work_but_rejects_protected_paths(tmp_path):
    from cascade.task.worktree import get_task_run

    root = dispatched_blocked_board(tmp_path)
    run = get_task_run("task_001")
    mark_terminal("task_001", "failed", root=root, error="forbidden_commit_paths")
    original = read_doc("task_001", root=root).body
    revise_task(
        "task_001",
        original.replace("- cascade/", "- app.py"),
        feature_id="feat_001",
        root=root,
    )
    protected = run.worktree / "docs/features/unauthorized.md"
    protected.write_text("preserved evidence\n")
    assert (
        retry_task("task_001", feature_id="feat_001", root=root)["reason"]
        == "task_worktree_scope_denied"
    )
    assert protected.read_text() == "preserved evidence\n"
    # Simulate the owning planning team preserving its prose in an allowed
    # project note; the Task must never be allowed to commit planning files.
    protected.rename(run.worktree / "planning-evidence.md")
    (run.worktree / "app.py").write_text("value = 1\n")
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"]
    assert (run.worktree / "app.py").read_text() == "value = 1\n"


def test_scope_blocked_contract_revised_to_source_completes_real_delivery(tmp_path):
    from cascade.task import invoke_tool
    from cascade.task.guard import TaskToolDenied
    from cascade.task.wiring import load_task_tools, route_swe_turn_failure
    from cascade.task.graph import ensure_task_graph, set_task_run_role_fn
    from cascade.task.checkpoint import thread_config
    from cascade.agent.types import RoleResult
    from cascade.task_rollup import retry_pending_task_merges
    from cascade.watchdog.events import read_events

    root = dispatched_blocked_board(tmp_path)
    task = read_doc("task_001", root=root)
    task.body = task.body.replace("- cascade/", "- docs/features/contract.md")
    task.meta.status = "active"
    write_doc(task, root=task.meta.path.parents[3])
    load_task_tools()
    with pytest.raises(TaskToolDenied) as refused:
        invoke_tool(
            "task_001",
            "swe_write",
            {"path": "docs/features/contract.md", "content": "contract"},
            root=root,
        )
    assert not route_swe_turn_failure("task_001", refused.value, root=root)
    assert execution_view("task_001", root=root)["last_error"] == "task_scope_denied"
    feature = read_doc("feat_001", root=root)
    feature.body += (
        "\nThe Feature owns the prose contract; its Task implements app.py.\n"
    )
    write_doc(feature, root=feature.meta.path.parents[3])
    revised = read_doc("task_001", root=root).body.replace(
        "- docs/features/contract.md", "- app.py\n- test_app.py"
    )
    revise_task("task_001", revised, feature_id="feat_001", root=root)
    graph = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    graph.update_state(
        thread_config("task_001"),
        {
            "task_id": "task_001",
            "feature_id": "feat_001",
            "provider_ids": {"swe": "codex"},
            "model_ids": {"swe": "offered"},
        },
    )
    starts = []

    async def provider(turn):
        starts.append(turn.cwd)
        for path, content in {
            "app.py": "value = 42\n",
            "test_app.py": "from app import value\ndef test_value():\n    assert value == 42\n",
            ".gitignore": "__pycache__/\n.pytest_cache/\n",
        }.items():
            invoke_tool(
                "task_001", "swe_write", {"path": path, "content": content}, root=root
            )
        invoke_tool(
            "task_001",
            "swe_commit",
            {"message": "Implement authorized contract"},
            root=root,
        )
        result = invoke_tool(
            "task_001",
            "swe_run_tests",
            {"cmd": ["python3", "-m", "pytest", "-q", "test_app.py"]},
            root=root,
        )
        assert result["exit_code"] == 0
        return RoleResult(text="Implemented and validated.", status="finished")

    set_task_run_role_fn(provider)
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"]
    from cascade.workspace.kickoff import wait_for_background_kickoffs

    assert wait_for_background_kickoffs()
    assert len(starts) == 1
    assert retry_pending_task_merges(root) == ["task_001"]
    assert read_doc("task_001", root=root).meta.status == "completed"
    assert retry_pending_task_merges(root) == []
    history = execution_view("task_001", root=root)["attempt_history"]
    assert any(row.get("last_error") == "task_scope_denied" for row in history)
    events, _ = read_events("feat_001", 0, root=root)
    assert sum(event.type == "TaskMerged" for event in events) == 1


def test_revision_intent_survives_crash_after_document_commit(tmp_path, monkeypatch):
    import cascade.task.execution as execution

    root = dispatched_blocked_board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forbidden_commit_paths")
    original = read_doc("task_001", root=root).body
    revised = original.replace("- cascade/", "- app.py")
    write = execution._write
    writes = []

    def interrupted(repo, records):
        writes.append(1)
        if len(writes) == 2:
            raise OSError("interrupted after document commit")
        return write(repo, records)

    with monkeypatch.context() as crash:
        crash.setattr(execution, "_write", interrupted)
        with pytest.raises(OSError, match="interrupted"):
            revise_task("task_001", revised, feature_id="feat_001", root=root)
    # Durable state, not a process-local receipt, authorizes one fresh retry.
    import sys

    program = "from pathlib import Path; import json,sys; from cascade.feature.recovery import recovery_status; print(json.dumps(recovery_status('task_001',feature_id='feat_001',root=Path(sys.argv[1]))))"
    import json

    result = subprocess.run(
        [sys.executable, "-c", program, str(root)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout)["action"] == "retry"
    assert revise_task("task_001", revised, feature_id="feat_001", root=root) is None
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"]
    assert not retry_task("task_001", feature_id="feat_001", root=root)["ok"]
