from __future__ import annotations

import json
import subprocess
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.recovery_progress.notifications import register_transition_publisher
from cascade.recovery_progress.publisher import (
    _connect,
    _record_transcript_milestone,
    drain_recovery_progress,
    install_recovery_progress_publisher,
    publish_committed_transition,
    record_transcript_milestone,
)
from cascade.task.action_recovery import create_or_load_action
from cascade.war_room.chat_store import (
    TranscriptPendingError,
    append_transcript_message,
    mark_message_legacy_unknown,
    read_messages,
    transcript_source_acknowledgement,
)
from cascade.watchdog.incidents import transition_receipt_v1
from tests.support import add_doc, make_repo


def _board(root: Path) -> None:
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


def _receipt(sequence: int, transition: str = "waiting") -> dict[str, object]:
    return transition_receipt_v1(
        source_kind="task_action",
        source_key="task_001:delivery",
        action="delivery",
        action_id="task_001:delivery",
        generation="sha256:generation",
        graph_id="task_001",
        affected_work_ids=("task_001", "feat_001"),
        attempt_number=1,
        claim_id="claim-1",
        sequence=sequence,
        transition_kind=transition,
        occurred_at=None if sequence == 1 else "2026-01-01T00:00:00+00:00",
        source_reference=f"executions.json#actions/task_001:delivery/{sequence}",
        safe_payload={"target": "task_001"},
    )


def _items(root: Path) -> list[dict]:
    work = (
        root
        / ".cascade/recovery_progress/v1/work"
        / __import__("hashlib").sha256(b"task_001").hexdigest()
    )
    pointer = json.loads((work / "current.json").read_text())
    manifest = json.loads((work / pointer["manifest"]).read_text())
    page = json.loads(
        (work / "revisions" / pointer["revision"] / manifest["pages"][0]).read_text()
    )
    return page["items"]


def test_committed_receipts_append_once_and_publish_ordered_refs(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    first = _receipt(1)
    publish_committed_transition(root, first, {"recovery_state": "waiting"})
    publish_committed_transition(root, first, {"recovery_state": "waiting"})
    publish_committed_transition(
        root, _receipt(2), {"recovery_state": "waiting"}
    )

    messages = read_messages("feat_001", root=root)
    assert len(messages) == 2
    assert [row["transition_sequence"] for row in messages] == [1, 2]
    assert messages[0]["author"] == "System · Recovery"
    assert messages[0]["occurred_at"] is None
    assert messages[0]["provenance"] == "direct"
    assert messages[0]["source_reference"].startswith("executions.json#")
    entry = _items(root)[0]
    assert entry["receipt_refs"] == [first["receipt_id"], _receipt(2)["receipt_id"]]
    assert entry["milestone_refs"] == [row["id"] for row in messages]


def _milestone_ack(root: Path, receipt: dict[str, object]) -> dict[str, object]:
    message = next(
        row
        for row in read_messages("feat_001", root=root)
        if row.get("receipt_id") == receipt["receipt_id"]
    )
    return {
        "receipt_id": receipt["receipt_id"],
        "entry_id": message["entry_id"],
        **transcript_source_acknowledgement(
            "feat_001",
            source_key=f"recovery:{receipt['receipt_id']}",
            root=root,
        ),
    }


def _stored_milestone(root: Path, receipt_id: str) -> dict[str, object]:
    connection = _connect(root)
    try:
        row = connection.execute(
            "SELECT * FROM transcript_milestones WHERE receipt_id = ?",
            (receipt_id,),
        ).fetchone()
        assert row is not None
        return dict(row)
    finally:
        connection.close()


def test_receipt_retry_refreshes_rewrite_incarnation_and_rejects_stale_downgrade(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    receipt = _receipt(1)
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    stale_ack = _milestone_ack(root, receipt)

    unrelated = append_transcript_message(
        "feat_001", author="feature_lead", body="authored", root=root
    )
    mark_message_legacy_unknown("feat_001", unrelated["id"], root=root)
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    current_ack = _milestone_ack(root, receipt)

    assert current_ack["message_id"] == stale_ack["message_id"]
    assert current_ack["incarnation"] != stale_ack["incarnation"]
    with pytest.raises(ValueError, match="different transcript acknowledgement"):
        record_transcript_milestone(root, {**current_ack, "message_id": "different"})
    with pytest.raises(ValueError, match="different transcript acknowledgement"):
        record_transcript_milestone(root, {**current_ack, "entry_id": "different"})
    record_transcript_milestone(root, stale_ack)
    stored = _stored_milestone(root, str(receipt["receipt_id"]))
    assert stored["incarnation"] == current_ack["incarnation"]
    assert stored["append_sequence"] == current_ack["append_sequence"]
    connection = _connect(root)
    try:
        connection.execute("BEGIN IMMEDIATE")
        with _record_transcript_milestone(
            connection, stale_ack, root=root, now=datetime.now(timezone.utc)
        ):
            connection.commit()
    finally:
        connection.close()
    stored = _stored_milestone(root, str(receipt["receipt_id"]))
    assert stored["incarnation"] == current_ack["incarnation"]
    assert stored["append_sequence"] == current_ack["append_sequence"]
    assert _items(root)[0]["milestone_refs"] == [current_ack["message_id"]]
    assert (
        len(
            [
                row
                for row in read_messages("feat_001", root=root)
                if row.get("receipt_id")
            ]
        )
        == 1
    )


def test_delayed_fast_path_ack_cannot_downgrade_first_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.war_room import recovery_milestones

    root = make_repo(tmp_path, git=False)
    _board(root)
    receipt = _receipt(1)
    acknowledgement_ready = threading.Event()
    resume_old_writer = threading.Event()
    stale_ack: dict[str, object] = {}
    failures: list[BaseException] = []
    original = recovery_milestones.append_committed_recovery_receipt

    def delayed_append(*args, **kwargs):
        ack = original(*args, **kwargs)
        if threading.current_thread().name == "old-publisher":
            stale_ack.update(ack)
            acknowledgement_ready.set()
            assert resume_old_writer.wait(timeout=10)
        return ack

    monkeypatch.setattr(
        recovery_milestones, "append_committed_recovery_receipt", delayed_append
    )

    def publish_old() -> None:
        try:
            publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
        except BaseException as exc:  # pragma: no cover - asserted in the parent thread
            failures.append(exc)

    old_writer = threading.Thread(target=publish_old, name="old-publisher")
    old_writer.start()
    assert acknowledgement_ready.wait(timeout=10)

    unrelated = append_transcript_message(
        "feat_001", author="feature_lead", body="authored", root=root
    )
    mark_message_legacy_unknown("feat_001", unrelated["id"], root=root)
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    current_ack = _milestone_ack(root, receipt)
    assert current_ack["incarnation"] != stale_ack["incarnation"]

    resume_old_writer.set()
    old_writer.join(timeout=10)
    assert not old_writer.is_alive()
    assert failures == []
    stored = _stored_milestone(root, str(receipt["receipt_id"]))
    assert stored["incarnation"] == current_ack["incarnation"]
    assert stored["append_sequence"] == current_ack["append_sequence"]
    assert stored["message_id"] == current_ack["message_id"]
    assert _items(root)[0]["milestone_refs"] == [current_ack["message_id"]]
    assert (
        len(
            [
                row
                for row in read_messages("feat_001", root=root)
                if row.get("receipt_id")
            ]
        )
        == 1
    )


def test_public_mapping_commit_holds_fence_across_rewrite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.war_room import chat_store

    root = make_repo(tmp_path, git=False)
    _board(root)
    receipt = _receipt(1)
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    stale_ack = _milestone_ack(root, receipt)
    messages = [
        append_transcript_message(
            "feat_001", author="feature_lead", body=f"authored-{index}", root=root
        )
        for index in range(2)
    ]
    mark_message_legacy_unknown("feat_001", messages[0]["id"], root=root)

    fence_held = threading.Event()
    release_mapping = threading.Event()
    rewrite_started = threading.Event()
    rewrite_done = threading.Event()
    failures: list[BaseException] = []
    original = chat_store.fenced_transcript_source_acknowledgement

    @contextmanager
    def observed_fence(*args, **kwargs):
        with original(*args, **kwargs) as current:
            if threading.current_thread().name == "old-public-mapping":
                fence_held.set()
                assert release_mapping.wait(timeout=10)
            yield current

    monkeypatch.setattr(
        chat_store, "fenced_transcript_source_acknowledgement", observed_fence
    )

    def map_old() -> None:
        try:
            record_transcript_milestone(root, stale_ack)
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            failures.append(exc)

    def rewrite() -> None:
        rewrite_started.set()
        try:
            mark_message_legacy_unknown("feat_001", messages[1]["id"], root=root)
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            failures.append(exc)
        finally:
            rewrite_done.set()

    mapping_thread = threading.Thread(target=map_old, name="old-public-mapping")
    mapping_thread.start()
    assert fence_held.wait(timeout=10)
    rewrite_thread = threading.Thread(target=rewrite)
    rewrite_thread.start()
    assert rewrite_started.wait(timeout=10)
    assert not rewrite_done.wait(timeout=0.1)

    release_mapping.set()
    mapping_thread.join(timeout=10)
    rewrite_thread.join(timeout=10)
    assert failures == []
    assert not mapping_thread.is_alive()
    assert not rewrite_thread.is_alive()

    record_transcript_milestone(root, stale_ack)
    current_ack = _milestone_ack(root, receipt)
    stored = _stored_milestone(root, str(receipt["receipt_id"]))
    assert stored["incarnation"] == current_ack["incarnation"]
    assert stored["append_sequence"] == current_ack["append_sequence"]


def test_receipt_retry_refreshes_registered_room_move_incarnation(
    tmp_path: Path,
) -> None:
    from cascade.workspace.integration_worktree import create_integration_worktree

    root = make_repo(tmp_path)
    _board(root)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    receipt = _receipt(1)
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    before = _milestone_ack(root, receipt)

    create_integration_worktree(
        "feature",
        "feat_001",
        branch="feat/feat_001",
        base_ref="HEAD",
        trunk=root,
    )
    publish_committed_transition(root, receipt, {"recovery_state": "waiting"})
    after = _milestone_ack(root, receipt)

    assert after["message_id"] == before["message_id"]
    assert after["incarnation"] != before["incarnation"]
    stored = _stored_milestone(root, str(receipt["receipt_id"]))
    assert stored["incarnation"] == after["incarnation"]
    assert stored["append_sequence"] == after["append_sequence"]
    assert _items(root)[0]["milestone_refs"] == [after["message_id"]]
    assert len(
        [row for row in read_messages("feat_001", root=root) if row.get("receipt_id")]
    ) == 1


def test_missed_notification_replays_as_reconciled_after_source_commit(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    register_transition_publisher(None)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
    )

    try:
        result = drain_recovery_progress(root)
        messages = read_messages("feat_001", root=root)
        assert result["imported_receipts"] == 1
        assert len(messages) == 1
        assert messages[0]["provenance"] == "reconciled"
        assert _items(root)[0]["milestone_refs"] == [messages[0]["id"]]
        assert drain_recovery_progress(root)["imported_receipts"] == 0
        assert len(read_messages("feat_001", root=root)) == 1
    finally:
        register_transition_publisher(None)


def test_pending_authoritative_source_keeps_replay_cursor_and_mapping_retryable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.war_room import chat_store

    root = make_repo(tmp_path, git=False)
    _board(root)
    register_transition_publisher(None)
    create_or_load_action(
        "task_001:delivery",
        "queued_delivery",
        root=root,
        attempt_bound=1,
        metadata={"task_id": "task_001"},
        owning_team={"kind": "feature_team", "work_id": "feat_001"},
    )

    @contextmanager
    def unavailable(*args, **kwargs):
        raise TranscriptPendingError("source unavailable")
        yield  # pragma: no cover

    with monkeypatch.context() as scoped:
        scoped.setattr(
            chat_store, "fenced_transcript_source_acknowledgement", unavailable
        )
        first = drain_recovery_progress(root)

    receipt = next(row["receipt_id"] for row in read_messages("feat_001", root=root))
    connection = _connect(root)
    try:
        assert (
            connection.execute(
                "SELECT 1 FROM transcript_milestones WHERE receipt_id = ?", (receipt,)
            ).fetchone()
            is None
        )
        assert (
            connection.execute(
                "SELECT value FROM meta WHERE key = 'source_cursor'"
            ).fetchone()["value"]
            == "0"
        )
    finally:
        connection.close()
    assert first["complete"] is False
    assert _items(root)[0]["milestone_refs"] == []

    second = drain_recovery_progress(root)
    assert second["complete"] is True
    assert (
        _stored_milestone(root, receipt)["message_id"]
        == read_messages("feat_001", root=root)[0]["id"]
    )
    assert _items(root)[0]["milestone_refs"] == [
        read_messages("feat_001", root=root)[0]["id"]
    ]


def test_installed_notification_publishes_before_source_call_returns(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    try:
        install_recovery_progress_publisher(root)
        action = create_or_load_action(
            "task_001:delivery",
            "queued_delivery",
            root=root,
            attempt_bound=1,
            metadata={"task_id": "task_001"},
            owning_team={"kind": "feature_team", "work_id": "feat_001"},
        )
        messages = read_messages("feat_001", root=root)
        assert messages[-1]["receipt_id"] == action["transition_receipts"][-1]["receipt_id"]
        assert _items(root)[0]["milestone_refs"] == [messages[-1]["id"]]
    finally:
        register_transition_publisher(None)


def test_chat_failure_keeps_progress_pending_without_milestone_ref(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path, git=False)
    _board(root)
    monkeypatch.setattr(
        "cascade.war_room.recovery_milestones.append_transcript_message",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk unavailable")),
    )

    publish_committed_transition(
        root, _receipt(1), {"recovery_state": "waiting"}
    )

    assert read_messages("feat_001", root=root) == []
    assert _items(root)[0]["milestone_refs"] == []
