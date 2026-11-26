from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path

import pytest

from cascade.recovery_progress import publisher
from cascade.recovery_progress.live import (
    begin_live_observation,
    end_live_observation,
    reset_live_observations_for_tests,
    set_process_probe_for_tests,
)
from cascade.recovery_progress.publisher import (
    _connect,
    _writer_lock,
    drain_recovery_progress,
    publish_committed_transition,
)
from cascade.task.action_recovery import create_or_load_action
from cascade.recovery_progress.notifications import register_transition_publisher
from cascade.watchdog.incidents import transition_receipt_v1
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _reset_live() -> None:
    reset_live_observations_for_tests()
    yield
    reset_live_observations_for_tests()


def _receipt(
    *,
    action_id: str = "task_001:delivery",
    generation: str = "sha256:generation",
    work_ids: tuple[str, ...] = ("task_001",),
    graph_id: str | None = "feat_001",
    attempt: int | None = 1,
    claim: str | None = "claim-1",
    sequence: int = 1,
    transition: str = "created",
    safe_payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return transition_receipt_v1(
        source_kind="task_action",
        source_key=action_id,
        action="delivery",
        action_id=action_id,
        generation=generation,
        graph_id=graph_id,
        affected_work_ids=work_ids,
        attempt_number=attempt,
        claim_id=claim,
        sequence=sequence,
        transition_kind=transition,
        occurred_at="2026-01-01T00:00:00+00:00",
        source_reference=f"test:{action_id}:{sequence}",
        safe_payload=safe_payload,
    )


def _projection(root: Path, work_id: str) -> tuple[dict, list[dict]]:
    work_root = (
        root
        / ".cascade"
        / "recovery_progress"
        / "v1"
        / "work"
        / __import__("hashlib").sha256(work_id.encode()).hexdigest()
    )
    pointer = json.loads((work_root / "current.json").read_text())
    manifest = json.loads((work_root / pointer["manifest"]).read_text())
    page = json.loads(
        (
            work_root / "revisions" / pointer["revision"] / manifest["pages"][0]
        ).read_text()
    )
    return pointer, page["items"]


def test_exact_live_execution_and_aliases_share_immutable_revision(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    receipt = _receipt(
        work_ids=("task_001", "feat_001"), transition="execution_started"
    )
    observation = begin_live_observation(
        "executor",
        graph_id="feat_001",
        action_id="task_001:delivery",
        action_generation="sha256:generation",
        attempt_number=1,
        claim_id="claim-1",
    )
    publish_committed_transition(
        root,
        receipt,
        {"recovery_state": "running", "attempts": [{"attempt": 1, "outcome": None}]},
    )

    task_pointer, task_items = _projection(root, "task_001")
    feature_pointer, feature_items = _projection(root, "feat_001")
    assert task_pointer["revision"] == feature_pointer["revision"]
    assert task_items[0]["entry_id"] == feature_items[0]["entry_id"]
    assert task_items[0]["entry_revision"] == feature_items[0]["entry_revision"]
    assert task_items[0]["state"] == "executing"
    assert task_items[0]["valid_until"]
    assert end_live_observation(observation.identity)


def test_investigation_requires_exact_live_invocation_and_conflicts_are_unavailable(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    receipt = _receipt(transition="investigating")
    matching = begin_live_observation(
        "invocation",
        graph_id="feat_001",
        action_id="task_001:delivery",
        action_generation="sha256:generation",
        attempt_number=1,
        claim_id="claim-1",
    )
    publish_committed_transition(root, receipt, {"recovery_state": "investigating"})
    assert _projection(root, "task_001")[1][0]["state"] == "investigating"
    assert end_live_observation(matching.identity)

    conflicting = begin_live_observation(
        "invocation",
        graph_id="feat_001",
        action_id="task_001:delivery",
        action_generation="sha256:other-generation",
        attempt_number=1,
        claim_id="claim-1",
    )
    publish_committed_transition(
        root,
        _receipt(transition="investigating", sequence=2),
        {"recovery_state": "investigating"},
    )
    assert _projection(root, "task_001")[1][0]["state"] == "stale_unavailable"
    assert end_live_observation(conflicting.identity)


def test_proven_dead_executor_is_unavailable_not_executing(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    begin_live_observation(
        "executor",
        graph_id="feat_001",
        action_id="task_001:delivery",
        action_generation="sha256:generation",
        attempt_number=1,
        claim_id="claim-1",
    )
    set_process_probe_for_tests(lambda _pid: None)
    publish_committed_transition(
        root,
        _receipt(transition="execution_started"),
        {"recovery_state": "running"},
    )
    assert _projection(root, "task_001")[1][0]["state"] == "stale_unavailable"


@pytest.mark.parametrize(
    ("transition", "snapshot", "expected"),
    [
        ("created", {}, "requested_queued"),
        (
            "acknowledged",
            {"acknowledgement": {"at": "2026-01-01T00:00:00+00:00"}},
            "acknowledged",
        ),
        (
            "waiting",
            {
                "accountable_owner": "human",
                "evidence": {"prerequisite": "human approval"},
            },
            "waiting_blocked",
        ),
        (
            "failed",
            {
                "outcome": "error",
                "attempts": [{"outcome": "failed"}],
                "retry_policy": {"attempt_bound": 2},
            },
            "retryable_failed",
        ),
        (
            "failed",
            {
                "outcome": "error",
                "attempts": [{"outcome": "failed"}],
                "retry_policy": {"attempt_bound": 1},
            },
            "exhausted",
        ),
        ("attempt_finished", {"outcome": "success"}, "verification_pending"),
        (
            "resolved",
            {
                "outcome": "success",
                "result": {
                    "postcheck": {"verified": True, "generation": "sha256:other"}
                },
            },
            "verification_pending",
        ),
        ("execution_started", {"recovery_state": "running"}, "stale_unavailable"),
        (
            "resolved",
            {
                "outcome": "success",
                "result": {
                    "postcheck": {"verified": True, "generation": "sha256:generation"}
                },
            },
            "verified_complete",
        ),
    ],
)
def test_public_states_require_their_matching_evidence(
    tmp_path: Path, transition: str, snapshot: dict, expected: str
) -> None:
    root = make_repo(tmp_path, git=False)
    publish_committed_transition(root, _receipt(transition=transition), snapshot)
    _, items = _projection(root, "task_001")
    assert items[0]["state"] == expected


def test_missed_notification_replays_fairly_from_authoritative_source(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    create_or_load_action(
        "task_002:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_002"},
    )

    first = drain_recovery_progress(root, max_receipts=1)
    assert first["imported_receipts"] == 1
    assert first["complete"] is False
    second = drain_recovery_progress(root, max_receipts=1)
    assert second["imported_receipts"] == 1
    assert first["source_load_seconds"] >= 0
    assert _projection(root, "task_001")[1] or _projection(root, "task_002")[1]
    assert _projection(root, "task_001")[1] and _projection(root, "task_002")[1]


def test_drain_publisher_thread_lock_uses_one_deadline_then_replays(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    register_transition_publisher(None)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    locked = threading.Event()
    release = threading.Event()

    def hold() -> None:
        with _writer_lock:
            locked.set()
            assert release.wait(timeout=5)

    holder = threading.Thread(target=hold)
    holder.start()
    assert locked.wait(timeout=5)
    started = time.monotonic()
    pending = drain_recovery_progress(root, max_seconds=0.2)
    elapsed = time.monotonic() - started
    assert pending["complete"] is False
    assert 0.12 <= elapsed < 0.75

    release.set()
    holder.join(timeout=5)
    assert not holder.is_alive()
    assert drain_recovery_progress(root)["imported_receipts"] == 1
    assert drain_recovery_progress(root)["imported_receipts"] == 0


def test_drain_sqlite_writer_lock_uses_remaining_budget_then_replays(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    register_transition_publisher(None)
    seed = _connect(root)
    seed.close()
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
    )
    blocker = sqlite3.connect(
        root / ".cascade/recovery_progress/v1/writer-index.sqlite3"
    )
    blocker.execute("BEGIN IMMEDIATE")
    try:
        started = time.monotonic()
        pending = drain_recovery_progress(root, max_seconds=0.2)
        elapsed = time.monotonic() - started
        assert pending["complete"] is False
        assert 0.12 <= elapsed < 0.75
    finally:
        blocker.rollback()
        blocker.close()

    assert drain_recovery_progress(root)["imported_receipts"] == 1
    assert drain_recovery_progress(root)["imported_receipts"] == 0


def test_connect_refreshes_remaining_budget_for_each_schema_statement(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    observed: list[int] = []
    original = publisher._set_busy_deadline
    ticks = iter(range(1_000, 2_000, 10))
    monkeypatch.setattr(publisher.time, "monotonic", lambda: next(ticks) / 1_000)

    def record(connection: sqlite3.Connection, deadline: float) -> None:
        original(connection, deadline)
        observed.append(int(connection.execute("PRAGMA busy_timeout").fetchone()[0]))

    monkeypatch.setattr(publisher, "_set_busy_deadline", record)
    connection = publisher._connect(root, deadline=2.0)
    connection.close()

    assert len(observed) == 8
    assert all(later < earlier for earlier, later in zip(observed, observed[1:]))


def test_owner_limit_leaves_explicit_lag_for_fair_continuation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    for work_id in ("task_001", "task_002"):
        create_or_load_action(
            f"{work_id}:delivery",
            "queued_delivery",
            root=root,
            attempt_bound=1,
            metadata={"task_id": work_id},
        )

    first = drain_recovery_progress(root, max_owners=1)
    assert first["imported_receipts"] == 2
    assert first["published_owners"] == 1
    assert first["lag"]["backlog_count"] == 1
    assert first["complete"] is False
    second = drain_recovery_progress(root, max_owners=1)
    assert second["published_owners"] == 1
    assert second["lag"]["backlog_count"] == 0
    assert second["complete"] is True


def test_blocker_order_and_safe_public_text(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    publish_committed_transition(
        root,
        _receipt(action_id="task_001:complete", transition="resolved", sequence=1),
        {
            "outcome": "success",
            "result": {
                "postcheck": {"verified": True, "generation": "sha256:generation"}
            },
        },
    )
    publish_committed_transition(
        root,
        _receipt(
            action_id="task_001:blocker",
            transition="waiting",
            sequence=1,
            safe_payload={"target": "../../secret", "reason": "blocked\nraw\x00output"},
        ),
        {
            "accountable_owner": "human",
            "evidence": {"prerequisite": "human approval\nwithout raw output"},
        },
    )
    _, items = _projection(root, "task_001")
    assert [item["state"] for item in items] == ["waiting_blocked", "verified_complete"]
    assert items[0]["target"] is None
    assert "\n" not in items[0]["safe_reason"]
    assert "\x00" not in items[0]["safe_reason"]


def test_legacy_receipt_preserves_unknown_provenance(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    receipt = _receipt(transition="created")
    receipt.pop("schema_version")
    receipt["occurred_at"] = None
    publish_committed_transition(root, receipt, {})
    item = _projection(root, "task_001")[1][0]
    assert item["provenance"] == "legacy_unknown"
    assert item["occurred_at"] is None


def test_legacy_source_import_is_incomplete_until_its_cursor_finishes(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    source = root / ".cascade" / "executions.json"
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        json.dumps(
            {
                "actions": {
                    "task_001:legacy": {
                        "action_id": "task_001:legacy",
                        "action_kind": "legacy_recovery",
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    first = drain_recovery_progress(root, max_receipts=1)
    assert first["complete"] is False
    manifest_pointer, items = _projection(root, "task_001")
    work_root = (
        root
        / ".cascade"
        / "recovery_progress"
        / "v1"
        / "work"
        / __import__("hashlib").sha256(b"task_001").hexdigest()
    )
    manifest = json.loads((work_root / manifest_pointer["manifest"]).read_text())
    assert manifest["completeness"] == "incomplete"
    assert items[0]["state"] == "stale_unavailable"
    assert drain_recovery_progress(root)["complete"] is True


def test_matching_action_and_incident_postcheck_converge_on_one_entry(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    action_receipt = _receipt(transition="attempt_finished")
    incident = {
        "accountable_owner": "watchdog",
        "outcome": "success",
        "request": {"original_action": {"action_id": "task_001:delivery"}},
        "result": {
            "postcheck": {
                "verified": True,
                "generation": "sha256:generation",
            }
        },
    }
    publish_committed_transition(
        root,
        action_receipt,
        {"recovery_state": "completed", "incident": incident},
    )
    incident_receipt = _receipt(
        action_id="task_001:action_recovery:sha256:generation",
        transition="resolved",
        sequence=2,
    )
    publish_committed_transition(root, incident_receipt, incident)
    _, items = _projection(root, "task_001")
    assert len(items) == 1
    assert items[0]["action_id"] == "task_001:delivery"
    assert items[0]["state"] == "verified_complete"
    assert len(items[0]["receipt_refs"]) == 2
