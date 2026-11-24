from pathlib import Path

import pytest

from cascade.task.action_recovery import create_or_load_action
from cascade.epic.recovery import recover_feature
from cascade.team_supervision import supervise_child
from tests.support import add_doc, make_repo


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

    result = supervise_child(
        "feat_001", "recover", root=root, epic_id="epic_001"
    )

    assert result["action"] == "recover"
    assert "selected_operation" not in result
