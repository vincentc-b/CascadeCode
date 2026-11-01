import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.board.store import pin_parent, read_doc, write_doc
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


def test_cancellation_defers_before_any_recovery_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    task = read_doc("task_001", root=root)
    task.meta.status = "cancelling"
    write_doc(task, root=root)
    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state",
        lambda *args, **kwargs: pytest.fail(
            "cancellation must not inspect or mutate recovery state"
        ),
    )

    result = recover_orphan_delivery("task_001", root=root)

    assert (result.decision, result.reason, result.mutated) == (
        "defer_draining",
        "cancellation_in_progress",
        False,
    )


def test_validated_commit_is_requeued_once_and_restart_replays_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    snapshots = 0
    enqueues = 0

    def snapshot(*args: object, **kwargs: object) -> OrphanDeliveryState:
        nonlocal snapshots
        snapshots += 1
        return _state(delivery=DeliveryEvidence("deliverable", "feature-base", current=True))

    def enqueue(*args: object, **kwargs: object) -> bool:
        nonlocal enqueues
        enqueues += 1
        return True

    monkeypatch.setattr("cascade.task.supervisor_recovery.snapshot_orphan_delivery_state", snapshot)
    monkeypatch.setattr(
        "cascade.task.worktree.attach_active_task_run",
        lambda *args, **kwargs: SimpleNamespace(parent_rev="feat-pin"),
    )
    monkeypatch.setattr("cascade.task.wiring.enqueue_validated_delivery", enqueue)

    first = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-validated"
    )
    # A new supervisor process has no in-memory state to restore.  The ledger,
    # rather than a second queue write, is the durable replay boundary.
    replay = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-validated"
    )

    assert (first.decision, first.mutated) == ("requeue_commit", True)
    assert replay == first
    assert (snapshots, enqueues) == (1, 1)
    ledger = json.loads(
        (root / ".cascade" / "orphan_delivery_recoveries.json").read_text(encoding="utf-8")
    )
    assert ledger["recoveries"]["delivery-validated"]["decision"] == "requeue_commit"


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


def test_completed_delivery_and_unsafe_workspace_never_attach_or_mutate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    states = iter(
        (
            _state(delivery=DeliveryEvidence("a", "b", current=True, queued=True)),
            _state(git=TaskGitState(False, False, False)),
        )
    )
    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state",
        lambda *args, **kwargs: next(states),
    )
    monkeypatch.setattr(
        "cascade.task.worktree.attach_active_task_run",
        lambda *args, **kwargs: pytest.fail("safe no-op and unsafe state must not attach"),
    )

    delivered = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-complete"
    )
    unsafe = recover_orphan_delivery(
        "task_001", root=root, observed_incident="delivery-missing-worktree"
    )

    assert (delivered.decision, delivered.mutated) == ("already_delivered", False)
    assert (unsafe.decision, unsafe.reason, unsafe.mutated) == (
        "unsafe",
        "task_branch_or_worktree_missing",
        False,
    )


def test_concurrent_resume_requests_share_one_mutation_and_kickoff(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _board(tmp_path)
    attachments = 0
    queue_writes = 0
    kickoffs: list[tuple[str, Path, str | None]] = []

    def attach(*args: object, **kwargs: object) -> SimpleNamespace:
        nonlocal attachments
        attachments += 1
        return SimpleNamespace(parent_rev="feat-pin")

    def mark_queued(*args: object, **kwargs: object) -> dict[str, int]:
        nonlocal queue_writes
        queue_writes += 1
        return {"attempt": 8}

    monkeypatch.setattr(
        "cascade.task.supervisor_recovery.snapshot_orphan_delivery_state",
        lambda *args, **kwargs: _state(),
    )
    monkeypatch.setattr("cascade.task.worktree.attach_active_task_run", attach)
    monkeypatch.setattr("cascade.task.execution.mark_stall_recovery_queued", mark_queued)

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: recover_orphan_delivery(
                    "task_001",
                    root=root,
                    observed_incident="delivery-concurrent",
                    kickoff=lambda task_id, repo, parent: kickoffs.append(
                        (task_id, repo, parent)
                    ),
                ),
                range(4),
            )
        )

    assert all(result == results[0] for result in results)
    assert (attachments, queue_writes) == (1, 1)
    assert kickoffs == [("task_001", root, "feat-pin")]
