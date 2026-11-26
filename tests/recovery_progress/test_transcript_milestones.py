from __future__ import annotations

import json
from pathlib import Path

from cascade.recovery_progress.notifications import register_transition_publisher
from cascade.recovery_progress.publisher import (
    drain_recovery_progress,
    install_recovery_progress_publisher,
    publish_committed_transition,
)
from cascade.task.action_recovery import create_or_load_action
from cascade.war_room.chat_store import read_messages
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
