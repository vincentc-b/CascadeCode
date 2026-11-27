"""Production wiring for Epic 35 review-health recovery."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import cascade.review_health as review_health
import cascade.review_rebase as review_rebase
import cascade.tracking as tracking
from cascade.review import review_record_for_feature
from cascade.review_health import reconcile_open_review_health
from cascade.task.action_recovery import load_action
from cascade.task_rollup import queue_task_merge
from cascade.watchdog.events import read_events
from tests.test_review_rebase import _execution_ready_turn
from tests.test_tracking_find import _github_evidence_runner
from tests.support import add_doc


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    )
    return result.stdout.strip()


def _conflicting_snapshot(*_args: object, **_kwargs: object) -> dict[str, object]:
    return {"state": "open", "mergeability": "conflicting", "comments": []}


def test_open_mergeable_github_review_reaches_healthy_path_with_supported_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: {
            "state": "open",
            "mergeability": "mergeable",
            "source_revision": turn.observed_source_sha,
            "target_revision": turn.observed_target_sha,
            "review_health": {"state": "green", "checks": []},
        },
    )

    assert reconcile_open_review_health(root) == [
        {"owner_id": "feat_035_001", "outcome": "healthy"}
    ]


def _green_check_snapshot(
    turn: object, *, name: object = "build", generation: object = 0
) -> dict[str, object]:
    source_head = turn.observed_source_sha
    return {
        "state": "open",
        "mergeability": "mergeable",
        "source_revision": source_head,
        "target_revision": turn.observed_target_sha,
        "review_health": {"state": "green", "checks": [name]},
        "required_check_policy": {"available": True, "required": [name]},
        "required_check_results": {
            "available": True,
            "source_head": source_head,
            "generation": generation,
            "statuses": {name: "success"},
            "checks": {
                name: {
                    "status": "success",
                    "generation": generation,
                    "source_head": source_head,
                }
            },
        },
        "review_feedback": {"available": True, "actionable": False},
    }


@pytest.mark.parametrize("generation", [None, "", True])
def test_authoritative_health_refuses_missing_or_boolean_check_generation(
    generation: object,
) -> None:
    snapshot = {
        "state": "open",
        "url": "https://example.test/pull/1",
        "source_branch": "feat/feat_001",
        "target_branch": "epic/epic_001",
        "source_revision": "source-head",
        "target_revision": "target-head",
        "review_identity": {
            "url": "https://example.test/pull/1",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
        },
        "mergeability": "mergeable",
        "required_check_policy": {
            "available": True,
            "source_head": "source-head",
            "target_head": "target-head",
            "required": ["build"],
        },
        "required_check_results": {
            "available": True,
            "source_head": "source-head",
            "statuses": {"build": "success"},
            "checks": {
                "build": {
                    "status": "success",
                    "source_head": "source-head",
                    "generation": generation,
                }
            },
        },
        "review_feedback": {"available": True, "actionable": False},
    }

    assert tracking._review_health(snapshot) == {
        "state": "conflict_or_moving_target",
        "reason": "stale_check_generation",
    }


def test_review_evidence_preserves_exact_utf8_boundaries_and_zero_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    name = "é" * 128
    generation = "🧪" * 64
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: _green_check_snapshot(turn, name=name, generation=generation),
    )

    assert reconcile_open_review_health(root) == [
        {"owner_id": "feat_035_001", "outcome": "healthy"}
    ]
    record = review_record_for_feature("feat_035_001", root=root)
    assert record is not None
    results = record["required_check_results"]
    assert results["generation"] == generation
    assert results["checks"][name]["generation"] == generation

    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: _green_check_snapshot(turn, generation=0),
    )
    assert reconcile_open_review_health(root)[0]["outcome"] == "healthy"
    record = review_record_for_feature("feat_035_001", root=root)
    assert record["required_check_results"]["generation"] == 0
    assert record["required_check_results"]["checks"]["build"]["generation"] == 0


@pytest.mark.parametrize(
    ("name", "generation"),
    [
        ("é" * 129, 1),
        ("build", "🧪" * 65),
        ("build", 10**64),
        ("build", True),
    ],
)
def test_oversized_or_malformed_authoritative_evidence_is_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    name: object,
    generation: object,
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: _green_check_snapshot(turn, name=name, generation=generation),
    )

    assert reconcile_open_review_health(root) == [
        {
            "owner_id": "feat_035_001",
            "outcome": "waiting",
            "wait_type": "evidence_unavailable",
            "reason": "review_evidence_persistence_failed",
        }
    ]
    record = review_record_for_feature("feat_035_001", root=root)
    assert record is not None
    assert record["review_health"] == {
        "state": "unavailable",
        "reason": "review_evidence_out_of_bounds",
        "checks": [],
        "checks_omitted": 0,
    }


def test_review_evidence_write_refusal_blocks_green_classification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: _green_check_snapshot(turn),
    )
    monkeypatch.setattr(
        review_health, "record_feature_review_evidence", lambda *_args, **_kwargs: False
    )

    assert reconcile_open_review_health(root) == [
        {
            "owner_id": "feat_035_001",
            "outcome": "waiting",
            "wait_type": "evidence_unavailable",
            "reason": "review_evidence_persistence_failed",
        }
    ]


def test_normalized_review_observation_over_32_kib_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    names = ["🧪" * 63 + chr(ord("A") + index) for index in range(20)]
    snapshot = _green_check_snapshot(turn)
    snapshot["review_health"] = {
        "state": "green",
        "reason": "🧪" * 160,
        "checks": names,
    }
    snapshot["required_check_policy"] = {
        "available": True,
        "error": "🧪" * 160,
        "source_head": "🧪" * 80,
        "target_head": "🧪" * 80,
        "required": names,
    }
    snapshot["required_check_results"] = {
        "available": True,
        "error": "🧪" * 160,
        "source_head": "🧪" * 80,
        "generation": "🧪" * 64,
        "statuses": {name: "🧪" * 40 for name in names},
        "checks": {
            name: {
                "status": "🧪" * 40,
                "generation": "🧪" * 64,
                "source_head": "🧪" * 80,
                "observed_at": "🧪" * 64,
            }
            for name in names
        },
    }
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health, "merge_request_snapshot", lambda *_args: snapshot
    )

    result = reconcile_open_review_health(root)[0]

    assert result["outcome"] == "waiting"
    assert result["wait_type"] == "evidence_unavailable"
    record = review_record_for_feature("feat_035_001", root=root)
    assert record["review_health"]["state"] == "unavailable"


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


@pytest.mark.parametrize("failure", ["fetch", "worktree", "admission"])
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


@pytest.mark.parametrize(
    ("health", "wait_type"),
    [
        ({"state": "pending", "checks": ["build"]}, "pending"),
        ({"state": "missing", "checks": ["build"]}, "missing"),
        (
            {"state": "conflict_or_moving_target", "reason": "stale_check_generation"},
            "conflict_or_moving_target",
        ),
        (
            {"state": "approval_only_wait", "reason": "approval_pending"},
            "approval_only_wait",
        ),
        (
            {
                "state": "transient_outage",
                "reason": "required_check_policy_unavailable",
            },
            "transient_outage",
        ),
    ],
)
def test_normalized_non_actionable_health_is_a_typed_wait_without_recovery_event(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    health: dict[str, object],
    wait_type: str,
) -> None:
    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    monkeypatch.setattr(
        review_health,
        "merge_request_snapshot",
        lambda *_args: {
            "state": "open",
            "mergeability": "mergeable",
            "source_revision": turn.observed_source_sha,
            "target_revision": turn.observed_target_sha,
            "review_health": health,
        },
    )
    before, _ = read_events("feat_035_001", 0, root=root)

    result = reconcile_open_review_health(root)

    assert result[0]["outcome"] == "waiting"
    assert result[0]["wait_type"] == wait_type
    after, _ = read_events("feat_035_001", 0, root=root)
    assert after == before


def test_snapshot_outage_is_a_transient_wait_without_an_action(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")

    def unavailable(*_args: object) -> dict[str, object]:
        raise OSError("forge unavailable")

    monkeypatch.setattr(review_health, "merge_request_snapshot", unavailable)

    assert reconcile_open_review_health(root) == [
        {
            "owner_id": "feat_035_001",
            "outcome": "waiting",
            "wait_type": "transient_outage",
            "reason": "review_snapshot_failed",
        }
    ]


def test_failed_check_reuses_material_repair_identity_and_changed_run_reevaluates_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cascade.feature.repair as feature_repair
    import cascade.team_supervision as team_supervision

    root, turn = _execution_ready_turn(tmp_path)
    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")
    run = {"id": 41}

    def snapshot(*_args: object) -> dict[str, object]:
        check = {
            "status": "failure",
            "generation": run["id"],
            "source_head": turn.observed_source_sha,
        }
        return {
            "state": "open",
            "mergeability": "mergeable",
            "source_revision": turn.observed_source_sha,
            "target_revision": turn.observed_target_sha,
            "required_check_results": {
                "available": True,
                "source_head": turn.observed_source_sha,
                "statuses": {"build": "failure"},
                "checks": {"build": check},
            },
            "review_health": {"state": "failed", "checks": ["build"]},
        }

    admitted: list[dict[str, object]] = []
    durable_actions: list[dict[str, object]] = []

    def request(
        _feature_id: str, request_id: str, **kwargs: object
    ) -> dict[str, object]:
        admitted.append({"request_id": request_id, **kwargs})
        existing = next(
            (row for row in durable_actions if row["request_id"] == request_id), None
        )
        if existing is not None:
            return {
                "action_id": f"feature-repair-{existing['generation']}",
                "generation": existing["generation"],
                "admitted": True,
                "replayed": True,
            }
        if durable_actions:
            writer = durable_actions[-1]
            return {
                "action_id": f"feature-repair-{writer['generation']}",
                "generation": writer["generation"],
                "admitted": False,
                "replayed": True,
                "blocker": "repair_writer_active",
            }
        generation = len(durable_actions) + 1
        durable_actions.append(
            {
                "action_id": f"feature-repair-{generation}",
                "request_id": request_id,
                "generation": generation,
                "request_evidence": kwargs["evidence"],
            }
        )
        return {
            "action_id": f"feature-repair-{generation}",
            "generation": generation,
            "admitted": True,
            "replayed": False,
        }

    monkeypatch.setattr(review_health, "merge_request_snapshot", snapshot)
    monkeypatch.setattr(team_supervision, "request_feature_review_repair", request)
    monkeypatch.setattr(
        feature_repair,
        "feature_repair_actions",
        lambda *_args, **_kwargs: list(durable_actions),
    )

    first = reconcile_open_review_health(root)[0]
    replay = reconcile_open_review_health(root)[0]
    run["id"] = 42
    changed = reconcile_open_review_health(root)[0]

    assert first["outcome"] == "routed"
    assert replay["outcome"] == "waiting"
    assert replay["wait_type"] == "repair_generation_reused"
    assert changed["outcome"] == "waiting"
    assert changed["wait_type"] == "repair_writer_active"
    assert len(admitted) == 2
    assert admitted[1]["request_id"] != admitted[0]["request_id"]
    assert replay["repair_generation"] == 1
    assert changed["repair_generation"] == 1
    assert len(durable_actions) == 1
    assert first["material_identity"] == replay["material_identity"]
    assert changed["material_identity"] != replay["material_identity"]


def test_scripted_normalized_check_runs_update_downstream_fence_without_redispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Production normalization feeds one durable downstream evidence fence."""

    import cascade.feature.repair as feature_repair
    import cascade.team_supervision as team_supervision

    root, turn = _execution_ready_turn(tmp_path)
    add_doc(
        root,
        id="feat_035_002",
        title="Dependent Feature",
        tier="feature",
        status="active",
        parent="epic_035",
        depends_on=["feat_035_001"],
    )
    add_doc(
        root,
        id="task_035_002_999",
        title="Downstream delivery",
        tier="task",
        status="active",
        parent="feat_035_002",
    )
    add_doc(
        root,
        id="feat_035_003",
        title="Unrelated Feature",
        tier="feature",
        status="active",
        parent="epic_035",
    )
    add_doc(
        root,
        id="task_035_003_999",
        title="Unrelated delivery",
        tier="task",
        status="active",
        parent="feat_035_003",
    )
    queue_task_merge("task_035_002_999", root=root)
    queue_task_merge("task_035_003_999", root=root)
    material = {
        "run_id": 41,
        "source_head": "s" * 40,
        "target_head": turn.observed_target_sha,
    }

    monkeypatch.setattr(review_health, "detect_forge", lambda _root: "github")

    def normalized(root: Path, mr: tracking.MergeRequest) -> dict[str, object]:
        transport_mr = tracking.MergeRequest(
            "https://github.com/example/project/pull/35",
            "35",
            "github",
            "feat-x",
            "main",
            False,
        )
        runner = _github_evidence_runner(
            transport_mr,
            policy={"contexts": ["build"]},
            checks=[{
                "id": material["run_id"],
                "name": "build",
                "head_sha": material["source_head"],
                "conclusion": "failure",
                "completed_at": (
                    f"2026-01-{material['run_id'] - 39:02d}T00:00:00Z"
                ),
            }],
            target_sha=material["target_head"],
        )

        def material_runner(
            args: list[str], runner_root: Path
        ) -> subprocess.CompletedProcess[str]:
            result = runner(args, runner_root)
            if args[:3] == ["gh", "pr", "view"] and result.returncode == 0:
                payload = json.loads(result.stdout)
                payload["commits"] = [{"oid": material["source_head"]}]
                return subprocess.CompletedProcess(
                    args, 0, json.dumps(payload), ""
                )
            return result

        return tracking.merge_request_snapshot(
            root,
            transport_mr,
            runner=material_runner,
        )

    durable_actions: list[dict[str, object]] = []

    def request(_feature_id: str, request_id: str, **kwargs: object) -> dict[str, object]:
        if durable_actions:
            current = durable_actions[0]
            return {
                "action_id": current["action_id"],
                "generation": current["generation"],
                "admitted": False,
                "replayed": True,
                "blocker": "repair_writer_active",
            }
        current = {
            "action_id": "repair:feat_035_001",
            "request_id": request_id,
            "generation": 1,
            "request_evidence": kwargs["evidence"],
        }
        durable_actions.append(current)
        return {
            "action_id": current["action_id"],
            "generation": 1,
            "admitted": True,
            "replayed": False,
        }

    monkeypatch.setattr(review_health, "merge_request_snapshot", normalized)
    monkeypatch.setattr(team_supervision, "request_feature_review_repair", request)
    monkeypatch.setattr(
        feature_repair,
        "feature_repair_actions",
        lambda *_args, **_kwargs: list(durable_actions),
    )

    first = reconcile_open_review_health(root)[0]
    replay = reconcile_open_review_health(root)[0]
    first_action = load_action("task_035_002_999:queued_merge", root=root)
    first_observation = first_action["metadata"]["upstream_review_observation"]
    material["run_id"] = 42
    changed = reconcile_open_review_health(root)[0]
    changed_action = load_action("task_035_002_999:queued_merge", root=root)
    changed_observation = changed_action["metadata"]["upstream_review_observation"]
    material["source_head"] = "t" * 40
    source_changed = reconcile_open_review_health(root)[0]
    source_observation = load_action(
        "task_035_002_999:queued_merge", root=root
    )["metadata"]["upstream_review_observation"]
    material["target_head"] = "u" * 40
    target_changed = reconcile_open_review_health(root)[0]
    target_action = load_action("task_035_002_999:queued_merge", root=root)
    target_observation = target_action["metadata"]["upstream_review_observation"]
    unrelated_action = load_action("task_035_003_999:queued_merge", root=root)

    assert first["outcome"] == "routed"
    assert replay["wait_type"] == "repair_generation_reused"
    assert changed["wait_type"] == "repair_writer_active"
    assert source_changed["wait_type"] == "repair_writer_active"
    assert target_changed["wait_type"] == "repair_writer_active"
    assert first_observation["blocker_identity"] == changed_observation["blocker_identity"]
    assert first_observation["evidence_generation"] != changed_observation[
        "evidence_generation"
    ]
    assert len({
        changed_observation["evidence_generation"],
        source_observation["evidence_generation"],
        target_observation["evidence_generation"],
    }) == 3
    assert target_action["attempt_count"] == 0
    assert first_observation["feature_id"] == "feat_035_001"
    assert first_observation["dependent_feature_id"] == "feat_035_002"
    assert first_observation["source_ref"] == "feat/feat_035_001"
    assert first_observation["target_ref"] == "epic/epic_035"
    assert "upstream_review_observation" not in unrelated_action["metadata"]
