from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import Event, Thread

from cascade.recovery_progress.notifications import register_transition_publisher
from cascade.task.action_recovery import (
    ActionFailure,
    create_or_load_action,
    load_action,
    record_action_checkpoint,
    resume_action,
)
from cascade.task.lifecycle_lock import task_lifecycle_lock
from cascade.watchdog.incidents import (
    append_stage_receipts,
    authoritative_generation,
    incident_record,
    recovery_stage_receipt,
)
from tests.support import make_repo


def test_committed_action_survives_notification_failure(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)

    observed_committed = False

    def missed_notification(
        published_root: Path, receipt: dict[str, object], _snapshot: dict[str, object]
    ) -> None:
        nonlocal observed_committed
        persisted = load_action("task_001:delivery", root=published_root)
        assert persisted is not None
        assert persisted["transition_receipts"][-1]["receipt_id"] == receipt["receipt_id"]
        acquired = Event()

        def acquire_from_another_thread() -> None:
            with task_lifecycle_lock(root=published_root):
                acquired.set()

        contender = Thread(target=acquire_from_another_thread)
        contender.start()
        contender.join(2)
        assert acquired.is_set()
        observed_committed = True
        raise RuntimeError("publisher crashed")

    register_transition_publisher(missed_notification)
    try:
        created = create_or_load_action(
            "task_001:delivery",
            "queued_delivery",
            root=root,
            attempt_bound=1,
            metadata={"task_id": "task_001"},
        )
    finally:
        register_transition_publisher(None)

    reloaded = load_action("task_001:delivery", root=root)
    assert observed_committed is True
    assert reloaded == created
    assert created["transition_receipts"][-1]["transition_kind"] == "created"


def test_generation_attempt_and_concurrent_sequence_are_retained(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    created = create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    errors: list[BaseException] = []

    def checkpoint(index: int) -> None:
        try:
            record_action_checkpoint(
                "task_001:delivery",
                f"checkpoint-{index}",
                root=root,
                refs={"source": "task/task_001"},
                shas={"source_head": str(index)},
                resume_instructions="resume from the retained checkpoint",
            )
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)

    workers = [Thread(target=checkpoint, args=(index,)) for index in range(6)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert errors == []
    action = load_action("task_001:delivery", root=root)
    assert action is not None
    receipts = action["transition_receipts"]
    assert [item["transition_sequence"] for item in receipts] == list(
        range(1, len(receipts) + 1)
    )
    assert len({item["receipt_id"] for item in receipts}) == len(receipts)
    assert receipts[0]["generation"] == created["incident"]["authoritative_generation"]
    assert all(item["action_id"] == "task_001:delivery" for item in receipts)


def test_execution_start_is_committed_before_held_executor_finishes(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    entered = Event()
    release = Event()

    def execute(_context: object) -> None:
        entered.set()
        assert release.wait(5)

    worker = Thread(
        target=lambda: resume_action("task_001:delivery", root=root, execute=execute)
    )
    worker.start()
    assert entered.wait(5)
    running = load_action("task_001:delivery", root=root)
    assert running is not None
    kinds = [item["transition_kind"] for item in running["transition_receipts"]]
    assert kinds[-2:] == ["attempt_claimed", "execution_started"]
    assert running["attempts"][-1]["outcome"] is None
    assert running["transition_receipts"][-1]["attempt_number"] == 1
    assert running["transition_receipts"][-1]["claim_id"]
    release.set()
    worker.join(5)
    assert not worker.is_alive()


def test_preflight_refusal_never_records_execution_start(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    executed = False

    def execute(_context: object) -> None:
        nonlocal executed
        executed = True

    def refuse(_context: object) -> None:
        raise ActionFailure("human_gate", metadata={"code": "approval_required"})

    action = resume_action(
        "task_001:delivery", root=root, execute=execute, preflight=refuse
    )
    assert executed is False
    assert action["transition_receipts"][-1]["transition_kind"] == "preflight_refused"
    assert "execution_started" not in {
        item["transition_kind"] for item in action["transition_receipts"]
    }


def test_equal_repeated_watchdog_stages_keep_distinct_sequences() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    generation = authoritative_generation(
        work_id="task_001",
        tier="task",
        evidence={"state": "blocked"},
        capability="retry_task",
    )
    def stage() -> dict[str, object]:
        return recovery_stage_receipt(
            "waiting",
            actor="feature:feat_001",
            capability="retry_task",
            permitted_inputs=("authoritative_generation",),
            authority_revision="revision",
            obligation=f"task_001:blocked:{generation}",
            result="owner_result_deferred",
            now=now,
        )
    incident = incident_record(
        work_id="task_001",
        tier="task",
        accountable_owner="feature:feat_001",
        failure_class="blocked",
        generation=generation,
        evidence={"state": "blocked"},
        selected_capability="retry_task",
        outcome="deferred",
        now=now,
        stage_receipts=append_stage_receipts([], stage(), stage()),
    )
    receipts = incident["transition_receipts"]
    assert [item["transition_sequence"] for item in receipts] == [1, 2]
    assert receipts[0]["recorded_at"] == receipts[1]["recorded_at"]
    assert receipts[0]["receipt_id"] != receipts[1]["receipt_id"]
