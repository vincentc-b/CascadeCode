"""Production wiring for Epic 35 review-health recovery."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import cascade.review_health as review_health
import cascade.review_rebase as review_rebase
from cascade.review_health import reconcile_open_review_health
from cascade.task.action_recovery import load_action
from cascade.watchdog.events import read_events
from tests.test_review_rebase import _execution_ready_turn


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return result.stdout.strip()


def _conflicting_snapshot(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"state": "open", "mergeability": "conflicting", "comments": []}


def test_monitor_publishes_an_already_resolved_owned_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    _git(root, "merge", "epic/epic_035", "--no-edit")
    resolved_head = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(review_health, "merge_request_snapshot", _conflicting_snapshot)
    monkeypatch.setattr(review_rebase, "_REPOSITORY_CHECK_COMMAND", (sys.executable, "-c", ""))

    result = reconcile_open_review_health(root)

    assert result == [{"owner_id": "feat_035_001", "action_id": turn.action_id, "outcome": "published"}]
    remote_head = _git(root, "ls-remote", "origin", "refs/heads/feat/feat_035_001").split()[0]
    assert remote_head == resolved_head
    action = load_action(turn.action_id, root=root)
    assert action is not None and action["recovery_state"] == "completed"


def test_monitor_routes_an_unresolved_feature_review_once_to_its_feature_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(review_health, "merge_request_snapshot", _conflicting_snapshot)

    first = reconcile_open_review_health(root)
    second = reconcile_open_review_health(root)

    assert first[0]["outcome"] == "routed"
    assert second[0]["outcome"] == "routed"
    action = load_action(turn.action_id, root=root)
    assert action is not None
    assert action["recovery"]["owning_team"] == {"kind": "feature_team", "work_id": "feat_035_001"}
    events, _ = read_events("feat_035_001", 0, root=root)
    requests = [event for event in events if event.type == "BranchActionRecoveryRequested"]
    assert len(requests) == 1
    assert requests[0].payload["action_id"] == turn.action_id
