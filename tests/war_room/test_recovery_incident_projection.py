"""Durable recovery-incident board contract."""

from __future__ import annotations

import json
from pathlib import Path

from cascade.war_room.serialize import board_view_from_index
from cascade.workspace.integration_worktree import merged_board
from tests.support import add_doc, make_repo


def _board(root: Path):
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    return board_view_from_index(merged_board(root), root=root)


def _write_action(
    root: Path, *, state: str, routing: str | None, completed: bool = False
) -> None:
    action = {
        "action_id": "merge:feat_001:1",
        "action_kind": "merge",
        "recovery_state": "completed" if completed else state,
        "attempt_count": 2,
        "updated_at": "2026-11-03T12:00:00+00:00",
        "attempts": [
            {
                "started_at": "2026-11-03T11:59:00+00:00",
                "completed_at": "2026-11-03T12:00:00+00:00",
            }
        ],
        "recovery": {
            "owning_team": {"kind": "epic_team", "work_id": "epic_001"},
            "evidence": {
                "affected_work_id": "feat_001",
                "safe_summary": "Merge failed because the target changed.",
                "conflicting_paths": ["cascade/merge.py"],
            },
            "provenance": {"source_branch": "feat/feat_001"},
            "routing_marker": ({"status": routing} if routing else {}),
            "human_blocker": None,
        },
    }
    path = root / ".cascade" / "executions.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 3, "actions": {action["action_id"]: action}}),
        encoding="utf-8",
    )


def test_incident_is_durable_and_only_claims_investigation_after_queue(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _write_action(root, state="awaiting_owner_decision", routing=None)
    failed = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert failed["state"] == "failed"
    assert failed["affected"] == {
        "branch": "feat/feat_001",
        "paths": ["cascade/merge.py"],
    }
    assert failed["last_attempt"]["number"] == 2

    _write_action(root, state="awaiting_owner_decision", routing="enqueued")
    restarted = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert restarted["state"] == "investigating"
    assert restarted["owner"] == {"kind": "epic_team", "work_id": "epic_001"}
    assert restarted["target"] == {
        "kind": "action",
        "id": "merge:feat_001:1",
        "href": "/api/doc/feat_001",
    }


def test_resolution_clears_active_incident_and_blocker_is_actionable(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    _write_action(root, state="blocked", routing="blocked")
    path = root / ".cascade" / "executions.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["actions"]["merge:feat_001:1"]["recovery"]["human_blocker"] = {
        "message": "Approval is required.",
        "required_action": "Approve the review before resuming.",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert blocked["state"] == "blocked"
    assert blocked["next_step"] == "Approve the review before resuming."

    _write_action(root, state="blocked", routing="enqueued", completed=True)
    assert _board(root)["features"]["2_active"][0]["recovery_incident"] is None


def test_recovery_incident_lifecycle_rehydrates_exactly_across_reads(tmp_path: Path) -> None:
    """One persisted action drives the full operator lifecycle after every refresh."""

    root = make_repo(tmp_path, git=False)
    _write_action(root, state="awaiting_owner_decision", routing=None)
    path = root / ".cascade" / "executions.json"

    failed = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert failed == {
        "state": "failed",
        "reason": "Merge failed because the target changed.",
        "owner": {"kind": "epic_team", "work_id": "epic_001"},
        "affected": {"branch": "feat/feat_001", "paths": ["cascade/merge.py"]},
        "last_attempt": {"number": 2, "at": "2026-11-03T12:00:00+00:00"},
        "target": {
            "kind": "action",
            "id": "merge:feat_001:1",
            "href": "/api/doc/feat_001",
        },
        "next_step": "The failure is recorded; queue the owning team investigation before resuming.",
    }
    # A refresh and a new process both derive the same projection from disk.
    assert _board(root)["features"]["2_active"][0]["recovery_incident"] == failed

    payload = json.loads(path.read_text(encoding="utf-8"))
    action = payload["actions"]["merge:feat_001:1"]
    action["recovery"]["routing_marker"] = {"status": "enqueued"}
    path.write_text(json.dumps(payload), encoding="utf-8")
    investigating = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert investigating["state"] == "investigating"
    assert investigating["next_step"] == (
        "The owning team has been durably asked to investigate this action."
    )

    action["recovery_state"] = "blocked"
    action["recovery"]["human_blocker"] = {
        "message": "Approval is required.",
        "required_action": "Approve the recovery review before retrying.",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    blocked = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert blocked["state"] == "blocked"
    assert blocked["owner"] == {"kind": "epic_team", "work_id": "epic_001"}
    assert blocked["next_step"] == "Approve the recovery review before retrying."

    action["recovery_state"] = "awaiting_owner_decision"
    action["recovery"]["human_blocker"] = None
    action["attempt_count"] = 3
    action["updated_at"] = "2026-11-03T12:05:00+00:00"
    action["attempts"].append({"started_at": "2026-11-03T12:04:00+00:00"})
    path.write_text(json.dumps(payload), encoding="utf-8")
    retrying = _board(root)["features"]["2_active"][0]["recovery_incident"]
    assert retrying["state"] == "investigating"
    assert retrying["last_attempt"] == {"number": 3, "at": "2026-11-03T12:04:00+00:00"}

    action["recovery_state"] = "completed"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert _board(root)["features"]["2_active"][0]["recovery_incident"] is None
