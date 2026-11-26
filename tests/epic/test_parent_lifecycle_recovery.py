from pathlib import Path
from datetime import datetime, timezone
import json

import pytest

from cascade.task.action_recovery import create_or_load_action
from cascade.board.store import read_doc, write_doc
from cascade.epic.dependency_approvals import AuthenticatedHuman
from cascade.epic.recovery import recover_feature
import cascade.feature.repair as repair
import cascade.review as review
from cascade.team_supervision import request_feature_review_repair, supervise_child
from cascade.watchdog.events import read_events
from tests.support import add_doc, commit_board, make_repo


def _open_review_repair_request(root: Path) -> dict[str, object]:
    feature = read_doc("feat_001", root=root)
    feature.meta.approved_at = datetime.now(timezone.utc)
    write_doc(feature, root=root)
    commit_board(root)
    head = repair.head_sha(root)
    assert head is not None
    review._update_record(
        root,
        "feat_001",
        {
            "url": "https://example.test/pulls/7",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": head,
            "target_head": head,
            "current_generation": 3,
            "closed": False,
            "state": "open",
        },
        create=True,
    )
    return {
        "request_id": "review-fix:comment-7",
        "reason": "Address the scoped red-review finding",
        "evidence": {"comment_id": "comment-7", "finding": "edge case"},
        "approval_reference": "feature-approval:1",
        "scope_reference": "review-comment:comment-7",
        "review_url": "https://example.test/pulls/7",
        "review_forge": "github",
        "source_ref": "feat/feat_001",
        "target_ref": "epic/epic_001",
        "observed_source_head": head,
        "observed_target_head": head,
        "observed_review_generation": 3,
    }


def _completed_open_review(root: Path) -> dict[str, object]:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    return _open_review_repair_request(root)


def test_epic_supervision_executes_exact_feature_repair_adapter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
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
    generation = "sha256:" + "a" * 64
    create_or_load_action(
        "task_001:queued_merge",
        "queued_task_merge",
        root=root,
        attempt_bound=3,
        recovery_state="retryable",
        failure_classification="parent_lifecycle_mismatch",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        metadata={
            "task_id": "task_001",
            "parent_lifecycle_mismatch": {
                "authoritative_generation": generation,
                "accountable_owner": "feature_team:feat_001",
            },
        },
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda *_a: False
    )
    monkeypatch.setattr(
        "cascade.task_rollup._parent_lifecycle_mismatch",
        lambda *_a, **_k: {
            "authoritative_generation": generation,
            "accountable_owner": "feature_team:feat_001",
        },
    )
    calls: list[tuple[str, str, str]] = []

    def recover(task_id: str, *, feature_id: str, expected_generation: str, **_k):
        calls.append((task_id, feature_id, expected_generation))
        return {
            "ok": True,
            "selected_operation": "feature_repair.admit",
            "accountable_owner": "feature_team:feat_001",
            "admitted_or_requested": True,
            "acknowledged": True,
            "executed": True,
            "verified": False,
            "refusal": None,
            "next_prerequisite": "resume_original_task_delivery",
        }

    monkeypatch.setattr("cascade.feature.recovery.recover_task", recover)

    result = recover_feature("feat_001", root=root, epic_id="epic_001")

    assert calls == [("task_001", "feat_001", generation)]
    assert result["selected_operation"] == "feature_repair.admit"
    assert result["executed"] is True
    assert result["verified"] is False


def test_epic_supervision_rejects_mismatched_registered_owner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
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
    create_or_load_action(
        "task_001:queued_merge",
        "queued_task_merge",
        root=root,
        attempt_bound=3,
        recovery_state="retryable",
        failure_classification="parent_lifecycle_mismatch",
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
        metadata={
            "task_id": "task_001",
            "parent_lifecycle_mismatch": {
                "authoritative_generation": "sha256:" + "b" * 64,
                "accountable_owner": "feature_team:feat_999",
            },
        },
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda *_a: False
    )
    monkeypatch.setattr(
        "cascade.feature.recovery.recover_task",
        lambda *_a, **_k: pytest.fail("wrong owner reached Feature repair"),
    )

    result = supervise_child("feat_001", "recover", root=root, epic_id="epic_001")

    assert result["action"] == "recover"
    assert "selected_operation" not in result


def test_direct_parent_open_review_request_uses_durable_adapter_without_task_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    request = _completed_open_review(root)
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda *_a: False
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_graph_queue_event", lambda *_a, **_k: True
    )

    result = recover_feature(
        "feat_001", root=root, epic_id="epic_001", repair_request=request
    )

    assert result["selected_operation"] == "feature_repair.admit"
    assert result["child_id"] == "feat_001"
    assert result["status"] == "active"
    assert result["accountable_owner"] == "feature_team:feat_001"
    assert result["requested"] is True
    assert result["admitted"] is True
    assert result["acknowledged"] is True
    assert result["wakeup_acknowledged"] is True
    assert result["executing"] is False
    assert result["executed"] is False
    assert result["verification_pending"] is True
    assert result["verified"] is False
    assert result["action_id"].startswith("feature_repair:feat_001:")
    assert result["generation"] == 1


def test_human_adapter_replays_admission_after_pre_enqueue_crash_and_refuses_impostor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    request = _completed_open_review(root)
    request_id = str(request.pop("request_id"))
    human = AuthenticatedHuman("human:operator")
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda *_a: False
    )
    calls = 0

    def crash_once(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("injected pre-enqueue crash")
        return True

    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_graph_queue_event", crash_once
    )
    with pytest.raises(OSError, match="pre-enqueue"):
        request_feature_review_repair(
            "feat_001",
            request_id,
            root=root,
            authenticated_human=human,
            **request,
        )

    replay = request_feature_review_repair(
        "feat_001",
        request_id,
        root=root,
        authenticated_human=human,
        **request,
    )

    ledger = json.loads((root / ".cascade/executions.json").read_text())
    events, _ = read_events("feat_001", 0, root=root)
    assert replay["replayed"] is True
    assert replay["wakeup_acknowledged"] is True
    assert len(ledger["actions"]) == 1
    assert (
        len([event for event in events if event.type == "FeatureRepairAuthorized"]) == 1
    )
    with pytest.raises(PermissionError, match="authenticated human"):
        request_feature_review_repair(
            "feat_001",
            "review-fix:impostor",
            root=root,
            authenticated_human="human:operator",
            **request,
        )
    with pytest.raises(PermissionError, match="direct Epic parent"):
        request_feature_review_repair(
            "feat_001",
            "review-fix:unrelated-parent",
            root=root,
            requesting_parent_id="epic_999",
            **request,
        )


def test_live_feature_owner_defers_wakeup_without_claiming_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    request = _completed_open_review(root)
    monkeypatch.setattr(
        "cascade.workspace.kickoff.graph_turn_owner_is_live", lambda *_a: True
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff.kickoff_graph_queue_event",
        lambda *_a, **_k: pytest.fail("live owner must not receive competing kickoff"),
    )

    result = recover_feature(
        "feat_001", root=root, epic_id="epic_001", repair_request=request
    )

    assert result["admitted"] is False
    assert result["owner_live"] is True
    assert result["waiting"] is True
    assert result["wakeup_acknowledged"] is False
    assert result["executing"] is False
    assert result["executed"] is False
    assert result["verified"] is False
    assert result["next_prerequisite"] == "join_live_feature_owner"
    events, _ = read_events("feat_001", 0, root=root)
    assert events == []
    assert not (root / ".cascade/executions.json").exists()
