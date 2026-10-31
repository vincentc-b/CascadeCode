from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.board.store import pin_parent
from cascade.task.orphan_delivery import (
    DeliveryEvidence,
    OrphanDeliveryState,
    PinnedExecutionInputs,
    TaskGitState,
)
from cascade.task.supervisor_recovery import recover_orphan_delivery
from tests.support import add_doc, make_repo


def _board(tmp_path: Path) -> Path:
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
    pin_parent("task_001", "feat_001", root=root)
    return root


def _state(**changes: object) -> OrphanDeliveryState:
    values: dict[str, object] = {
        "task_id": "task_001",
        "task_active": True,
        "owner_live": False,
        "execution_phase": "running",
        "checkpoint_present": True,
        "pinned_inputs": PinnedExecutionInputs("codex", "gpt-5"),
        "delivery": DeliveryEvidence(),
        "git": TaskGitState(True, True, True, True),
    }
    values.update(changes)
    return OrphanDeliveryState(**values)  # type: ignore[arg-type]


def test_live_owner_is_durable_noop_and_replay_does_not_resnapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    calls = 0

    def snapshot(*args: object, **kwargs: object) -> OrphanDeliveryState:
        nonlocal calls
        calls += 1
        return _state(owner_live=True)

    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state", snapshot
    )
    first = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-1"
    )
    second = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-1"
    )

    assert first.decision == "no_op_live_owner"
    assert not first.mutated
    assert second == first
    assert calls == 1


def test_draining_defers_before_any_recovery_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    monkeypatch.setattr("cascade.workspace.drain.is_draining", lambda: True)
    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state",
        lambda *args, **kwargs: pytest.fail(
            "draining must not inspect or mutate recovery state"
        ),
    )

    result = recover_orphan_delivery("task_001", root=root)

    assert (result.decision, result.reason, result.mutated) == (
        "defer_draining",
        "worker_draining",
        False,
    )


def test_resume_attaches_existing_dirty_workspace_and_queues_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state",
        lambda *args, **kwargs: _state(),
    )
    monkeypatch.setattr(
        "cascade.task.worktree.attach_active_task_run",
        lambda *args, **kwargs: SimpleNamespace(parent_rev="feat-pin"),
    )
    monkeypatch.setattr(
        "cascade.task.execution.mark_stall_recovery_queued",
        lambda *args, **kwargs: {"attempt": 7},
    )
    kickoff: list[tuple[str, Path, str | None]] = []

    result = recover_orphan_delivery(
        "task_001",
        root=root,
        observed_incident="delivery-2",
        kickoff=lambda task_id, repo, parent: kickoff.append((task_id, repo, parent)),
    )

    assert result.decision == "resume_workspace"
    assert result.mutated
    assert result.attempt == 7
    assert kickoff == [("task_001", root, "feat-pin")]
