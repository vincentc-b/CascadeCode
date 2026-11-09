from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.agent.discovery.inventory import (
    InventoryFreshness,
    ProviderInventoryItem,
    ProviderInventoryResult,
)
from cascade.agent.discovery.types import DiscoveredModel
from cascade.board.errors import NotFound
from cascade.board.store import read_doc, write_doc
from cascade.feature.recovery import (
    recover_task,
    recovery_status,
    revise_task,
    retry_task,
)
from cascade.task.supervisor_recovery import RecoveryResult
from cascade.watchdog.blockage import propagate_direct_report_blockage
from cascade.task.execution import mark_awaiting_merge, mark_merge_blocked, mark_terminal
from cascade.watchdog import (
    activate_epic,
    dispatch_feature,
    dispatch_task,
)
from cascade.watchdog.types import DispatchResult
from cascade.watchdog.health import sweep_supervisor_health
from tests.support import add_doc, make_repo, approve_board_feature


@pytest.fixture(autouse=True)
def _supported_provider_inventory(monkeypatch: pytest.MonkeyPatch) -> None:
    inventory = ProviderInventoryResult(
        providers=(
            ProviderInventoryItem(
                provider_id="codex",
                display_name="Codex",
                models=(DiscoveredModel(id="offered", display_name="Offered"),),
            ),
        ),
        failures=(),
        freshness=InventoryFreshness(False, 1.0, 2.0, 1.0),
    )
    monkeypatch.setattr(
        "cascade.watchdog.dispatch.get_provider_inventory", lambda: inventory
    )
    monkeypatch.setattr(
        "cascade.approvals.get_provider_inventory", lambda: inventory
    )


def _select_roles(root: Path, work_id: str, *roles: str) -> None:
    doc = read_doc(work_id, root=root)
    doc.meta.provider = "codex"
    doc.meta.models = {role: "offered" for role in roles}
    write_doc(doc, root=root)


def _board(tmp_path: Path) -> Path:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    _select_roles(
        root,
        "epic_001",
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "swe",
    )
    _select_roles(root, "feat_001", "feature_lead", "feature_architect", "swe")
    _select_roles(root, "task_001", "swe")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    task = read_doc("task_001", root=root)
    task.meta.status = "blocked"
    write_doc(task, root=task.meta.path.parents[3])
    return root


def test_feature_team_can_revise_and_retry_its_blocked_child(tmp_path: Path) -> None:
    root = _board(tmp_path)
    original = read_doc("task_001", root=root).body
    revised = original.replace(
        "## Implementation notes\n\nNotes for the implementer.",
        "## Implementation notes\n\nProduces code and tests.",
    )

    assert revise_task("task_001", revised, feature_id="feat_001", root=root)
    assert "Produces code" in read_doc("task_001", root=root).body
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"] is True
    assert read_doc("task_001", root=root).meta.status == "active"


def test_feature_team_cannot_revise_foreign_task(tmp_path: Path) -> None:
    root = _board(tmp_path)
    with pytest.raises(NotFound):
        revise_task("task_001", "# no", feature_id="feat_999", root=root)


def test_recovery_status_marks_transient_forge_failure_retryable(
    tmp_path: Path,
) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forge connection timeout")

    status = recovery_status("task_001", feature_id="feat_001", root=root)

    assert status["phase"] == "terminal"
    assert status["reason"] == "transient_forge_failure"
    assert status["attempt_count"] >= 1
    assert status["affected"]["branch"] == "task/task_001"
    assert status["terminal_blocker"] == {"retryable": True}
    assert status["action"] == "retry"
    assert retry_task("task_001", feature_id="feat_001", root=root)["ok"] is True


def test_permission_refusal_is_not_retryable_or_a_permission_bypass(
    tmp_path: Path,
) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="permission denied by forge")

    status = recovery_status("task_001", feature_id="feat_001", root=root)
    result = retry_task("task_001", feature_id="feat_001", root=root)

    assert status["reason"] == "permission_refused"
    assert status["terminal_blocker"] == {"retryable": False}
    assert status["action"] == "permission"
    assert result["ok"] is False
    assert result["reason"] == "not_retryable"
    assert read_doc("task_001", root=root).meta.status == "blocked"


def test_retry_preserves_dispatch_preflight_response(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    preflight = SimpleNamespace(
        message="The selected model is not offered",
        to_dict=lambda: {
            "reason_code": "model_not_offered",
            "message": "The selected model is not offered",
        },
    )
    selections = SimpleNamespace(
        to_dict=lambda: {
            "work_id": "task_001",
            "roles": [
                {
                    "role": "swe",
                    "document_path": "docs/tasks/2_active/task_001.md",
                    "document_revision": "reviewed-revision",
                }
            ],
        }
    )
    monkeypatch.setattr(
        "cascade.feature.recovery.recovery_status",
        lambda *_args, **_kwargs: {"action": "retry"},
    )
    monkeypatch.setattr(
        "cascade.feature.recovery.dispatch_task",
        lambda *_args, **_kwargs: DispatchResult(
            ok=False,
            reason="provider_preflight_blocked",
            event=None,
            preflight=preflight,  # type: ignore[arg-type]
                selections=selections,  # type: ignore[arg-type]
        ),
    )

    result = retry_task("task_001", feature_id="feat_001", root=root)

    assert result["ok"] is False
    assert result["reason"] == "provider_preflight_blocked"
    assert result["code"] == "provider_preflight_blocked"
    assert result["error"] == "The selected model is not offered"
    assert result["preflight"]["reason_code"] == "model_not_offered"
    assert result["selections"]["roles"][0]["document_revision"] == "reviewed-revision"


def test_concurrent_retry_requests_resume_at_most_one_execution(tmp_path: Path) -> None:
    root = _board(tmp_path)
    mark_terminal("task_001", "failed", root=root, error="forge unavailable")

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _unused: retry_task(
                    "task_001", feature_id="feat_001", root=root
                ),
                range(4),
            )
        )

    assert sum(result["ok"] is True for result in results) == 1
    assert read_doc("task_001", root=root).meta.status == "active"


@pytest.mark.parametrize(
    ("decision", "reason", "outcome"),
    [
        ("requeue_commit", "validated_delivery_matches_git", "merge_queued"),
        ("resume_workspace", "orphaned_execution_resumable", "restart_requested"),
        ("no_op_live_owner", "execution_lease_live", "already_running"),
        ("already_delivered", "validated_delivery_already_queued", "merge_queued"),
        ("unsafe", "task_checkpoint_missing", "blocker"),
    ],
)
def test_feature_recover_task_translates_shared_recovery_outcomes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    decision: str,
    reason: str,
    outcome: str,
) -> None:
    root = _board(tmp_path)

    expected_root = root.resolve()

    def recover_through_supervisor(task_id, *, root, feature_id):
        assert task_id == "task_001"
        assert root == expected_root
        assert feature_id == "feat_001"
        return RecoveryResult(
            "task_001:delivery:1",
            decision,
            reason,
            decision in {"requeue_commit", "resume_workspace"},
        )

    monkeypatch.setattr(
        "cascade.feature.recovery.supervisor_recover_task_delivery",
        recover_through_supervisor,
    )

    result = recover_task("task_001", feature_id="feat_001", root=root)

    assert result["outcome"] == outcome
    assert result["ok"] is (outcome != "blocker")
    assert result["reason"] == reason
    if outcome == "blocker":
        assert result["blocker"] == reason


def test_feature_recover_task_rejects_foreign_task_before_supervisor_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    add_doc(root, id="feat_002", title="Other", tier="feature", parent="epic_001")
    add_doc(root, id="task_002", title="Other task", tier="task", parent="feat_002")
    monkeypatch.setattr(
        "cascade.feature.recovery.supervisor_recover_task_delivery",
        lambda *_args, **_kwargs: pytest.fail("foreign task reached supervisor"),
    )

    with pytest.raises(ValueError, match="not a child"):
        recover_task("task_002", feature_id="feat_001", root=root)


def test_tool_and_health_sweep_share_one_scoped_recovery_incident(
    tmp_path: Path,
) -> None:
    """A direct Feature request and a sweep coalesce at the shared ledger."""

    root = _board(tmp_path)
    mark_awaiting_merge("task_001", root=root)

    with ThreadPoolExecutor(max_workers=2) as pool:
        tool_result, _sweep = list(
            pool.map(
                lambda request: (
                    recover_task("task_001", feature_id="feat_001", root=root)
                    if request == "tool"
                    else sweep_supervisor_health(root)
                ),
                ("tool", "sweep"),
            )
        )

    assert tool_result["outcome"] == "blocker"
    blockers = read_doc("feat_001", root=root).meta.monitoring_blockers
    assert [(item.child_id, item.incident_id) for item in blockers] == [
        ("task_001", tool_result["recovery"]["incident_id"])
    ]
    assert recovery_status("task_001", feature_id="feat_001", root=root)[
        "incident"
    ] == tool_result["recovery"]


def test_semantic_conflict_blocker_clears_only_its_matching_incident(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    mark_merge_blocked(
        "task_001",
        root=root,
        reason="branch_conflict",
        conflict_paths=("cascade/feature/recovery.py", "tests/feature/test_recovery.py"),
        source_sha="task-sha",
        target_sha="feature-sha",
    )
    feature = read_doc("feat_001", root=root)
    task = read_doc("task_001", root=root)
    assert propagate_direct_report_blockage(
        feature,
        task,
        "another recovery",
        root=root,
        incident_id="task_001:delivery:other",
    ).ok
    monkeypatch.setattr(
        "cascade.feature.recovery.supervisor_recover_task_delivery",
        lambda *_args, **_kwargs: RecoveryResult(
            "task_001:delivery:1", "unsafe", "task_checkpoint_missing", False
        ),
    )

    result = recover_task("task_001", feature_id="feat_001", root=root)

    assert result["outcome"] == "blocker"
    assert result["blocker"] == "task_checkpoint_missing"
    blockers = read_doc("feat_001", root=root).meta.monitoring_blockers
    assert {(item.incident_id, item.reason) for item in blockers} == {
        ("task_001:delivery:other", "another recovery"),
        (
            "task_001:delivery:1",
            "semantic merge conflict (cascade/feature/recovery.py, tests/feature/test_recovery.py)",
        ),
    }

    monkeypatch.setattr(
        "cascade.feature.recovery.supervisor_recover_task_delivery",
        lambda *_args, **_kwargs: RecoveryResult(
            "task_001:delivery:1",
            "resume_workspace",
            "orphaned_execution_resumable",
            True,
        ),
    )
    recover_task("task_001", feature_id="feat_001", root=root)

    blockers = read_doc("feat_001", root=root).meta.monitoring_blockers
    assert [(item.incident_id, item.reason) for item in blockers] == [
        ("task_001:delivery:other", "another recovery")
    ]
