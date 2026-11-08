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
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
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
    monkeypatch.setattr(
        review_rebase, "validation_command", lambda root: (sys.executable, "-c", "")
    )

    result = reconcile_open_review_health(root)

    assert result == [
        {
            "owner_id": "feat_035_001",
            "action_id": turn.action_id,
            "outcome": "published",
        }
    ]
    remote_head = _git(
        root, "ls-remote", "origin", "refs/heads/feat/feat_035_001"
    ).split()[0]
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
    assert action["recovery"]["owning_team"] == {
        "kind": "feature_team",
        "work_id": "feat_035_001",
    }
    events, _ = read_events("feat_035_001", 0, root=root)
    requests = [
        event for event in events if event.type == "BranchActionRecoveryRequested"
    ]
    assert len(requests) == 1
    assert requests[0].payload["action_id"] == turn.action_id


def test_health_inquiry_is_executable_and_recurring_incidents_get_new_generation(
    tmp_path, monkeypatch
):
    from cascade.feature.review_recovery import publish_review_resolution
    from cascade.war_room.recovery_incident import recovery_incidents_by_work_id

    root, turn = _execution_ready_turn(tmp_path)
    (root / ".git/info/exclude").write_text(".cascade/\ndocs/_queue/\n")
    monkeypatch.setattr(review_health, "detect_forge", lambda _: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *a: {"state": "open", "mergeability": "unknown"},
    )
    incident = reconcile_open_review_health(root)[0]["action_id"]
    assert reconcile_open_review_health(root)[0]["action_id"] == incident
    with pytest.raises(PermissionError, match="different team"):
        publish_review_resolution(incident, feature_id="feat_999_001", root=root)
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *a: {"state": "open", "mergeability": "mergeable"},
    )
    healed = publish_review_resolution(incident, feature_id="feat_035_001", root=root)
    assert healed["recovery_state"] == "completed"
    assert healed["outcomes"][0]["outcome"] == "healthy"
    assert "feat_035_001" not in recovery_incidents_by_work_id(root=root)
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *a: {"state": "open", "mergeability": "unknown"},
    )
    renewed = reconcile_open_review_health(root)[0]["action_id"]
    assert renewed != incident
    assert (
        load_action(renewed, root=root)["recovery_state"] == "awaiting_owner_decision"
    )
    events, _ = read_events("feat_035_001", 0, root=root)
    assert len([e for e in events if e.type == "BranchActionRecoveryRequested"]) == 2


@pytest.mark.parametrize("failure", ["fetch", "snapshot", "worktree", "admission"])
def test_health_failure_rechecks_and_admits_actual_review_publication(
    tmp_path, monkeypatch, failure
):
    from cascade.feature.review_recovery import publish_review_resolution

    root, turn = _execution_ready_turn(tmp_path)
    (root / ".git/info/exclude").write_text(".cascade/\ndocs/_queue/\n")
    monkeypatch.setattr(review_health, "detect_forge", lambda _: "github")
    monkeypatch.setattr(review_health, "merge_request_snapshot", _conflicting_snapshot)
    with monkeypatch.context() as broken:
        if failure == "fetch":
            broken.setattr(review_health, "_fetch_review_heads", lambda *a: None)
        elif failure == "worktree":
            broken.setattr(review_health, "get_integration_worktree", lambda *a: None)
        elif failure == "admission":
            # Move the target after the fixture's first admission so this
            # poll must admit a new exact-head action, then refuse dirty work.
            _git(root, "checkout", "epic/epic_035")
            (root / "next-target.txt").write_text("new target generation\n")
            _git(root, "add", "next-target.txt")
            _git(root, "commit", "-m", "Advance target after earlier admission")
            _git(root, "push", "origin", "epic/epic_035")
            _git(root, "checkout", "feat/feat_035_001")
            (root / "unfinished.txt").write_text("Preserve this owned work\n")
        else:

            def unavailable(*a):
                raise OSError("forge unavailable")

            broken.setattr(review_health, "merge_request_snapshot", unavailable)
        incident = reconcile_open_review_health(root)[0]["action_id"]
        assert (
            publish_review_resolution(incident, feature_id="feat_035_001", root=root)[
                "recovery_state"
            ]
            != "completed"
        )
    if failure == "admission":
        _git(root, "add", "unfinished.txt")
        _git(root, "commit", "-m", "Preserve owned work before recovery")
    _git(root, "merge", "epic/epic_035", "--no-edit")
    monkeypatch.setattr(
        review_rebase, "validation_command", lambda root: (sys.executable, "-c", "")
    )
    result = publish_review_resolution(incident, feature_id="feat_035_001", root=root)
    assert result["recovery_state"] == "completed"
    assert result["outcomes"][0]["outcome"] == "published"
    published_id = result["outcomes"][0]["action_id"]
    assert load_action(published_id, root=root)["recovery_state"] == "completed"
    assert _git(root, "ls-remote", "origin", "refs/heads/feat/feat_035_001").split()[
        0
    ] == _git(root, "rev-parse", "HEAD")
    assert (
        publish_review_resolution(incident, feature_id="feat_035_001", root=root)[
            "outcomes"
        ][0]["outcome"]
        == "healthy"
    )


def test_validation_and_publication_failures_remain_owned_and_retryable(
    tmp_path, monkeypatch
):
    from cascade.feature.review_recovery import publish_review_resolution

    root, turn = _execution_ready_turn(tmp_path)
    (root / ".git/info/exclude").write_text(".cascade/\ndocs/_queue/\n")
    _git(root, "merge", "epic/epic_035", "--no-edit")
    monkeypatch.setattr(
        review_rebase,
        "validation_command",
        lambda root: (sys.executable, "-c", "raise SystemExit(1)"),
    )
    failed = publish_review_resolution(
        turn.action_id, feature_id="feat_035_001", root=root
    )
    assert failed["recovery_state"] == "awaiting_owner_decision"
    assert (
        load_action(turn.action_id, root=root)["recovery"]["owning_team"]["work_id"]
        == "feat_035_001"
    )
    assert (
        _git(root, "ls-remote", "origin", "refs/heads/feat/feat_035_001").split()[0]
        == turn.observed_source_sha
    )
    monkeypatch.setattr(
        review_rebase, "validation_command", lambda root: (sys.executable, "-c", "")
    )
    result = publish_review_resolution(
        turn.action_id, feature_id="feat_035_001", root=root
    )
    assert result["recovery_state"] == "completed"
    action = load_action(turn.action_id, root=root)
    assert action["attempt_count"] == 2
    assert action["attempts"][0]["outcome"] == "failed"
    assert (
        publish_review_resolution(turn.action_id, feature_id="feat_035_001", root=root)[
            "attempt_count"
        ]
        == 2
    )
