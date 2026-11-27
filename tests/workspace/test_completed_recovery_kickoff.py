"""Completed planning teams remain wakeable for routed recovery decisions."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.task.action_recovery import capture_and_route_action_failure
from cascade.watchdog import Event, append_event
from cascade.workspace.kickoff import (
    _run_queue_delivery_locked,
    _queue_is_ahead,
    deliver_queue_kickoffs,
    resume_inflight_graphs,
)
from tests.support import add_doc, make_repo


def _completed_epic_with_recovery(tmp_path: Path) -> tuple[Path, str]:
    root = make_repo(tmp_path, git=False)
    epic_id = "epic_001"
    add_doc(root, id=epic_id, title="Done", tier="epic", status="completed")
    capture_and_route_action_failure(
        f"{epic_id}:review_rebase",
        "review_rebase",
        affected_work_id=epic_id,
        intended_target_ref="main",
        root=root,
        failure_code="review_conflict",
        safe_summary="The completed Epic still owns an unresolved review.",
        owning_team={"kind": "epic_team", "work_id": epic_id},
    )
    return root, epic_id


def _completed_feature_with_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, str]:
    import cascade.review as review

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    feature_id = "feat_001"
    add_doc(
        root,
        id=feature_id,
        title="Delivered",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    review._store_review_generation(
        root,
        feature_id,
        {
            "url": "https://example.test/pulls/1",
            "number": "1",
            "forge": "github",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
            "source_head": "source-head",
            "target_head": "target-head",
            "draft": False,
            "closed": False,
            "seen_comments": [],
            "toast_notified": True,
        },
        generation=0,
        action_id=None,
    )
    monkeypatch.setattr(review, "review_enabled", lambda _root: True)
    return root, feature_id


def test_regular_delivery_includes_completed_team_with_pending_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, epic_id = _completed_epic_with_recovery(tmp_path)
    scheduled: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._schedule_queue_delivery",
        lambda work_id, *_args, **_kwargs: scheduled.append(work_id),
    )

    deliver_queue_kickoffs(root)

    assert scheduled == [epic_id]


def test_completed_team_recovery_event_reaches_a_role_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, epic_id = _completed_epic_with_recovery(tmp_path)
    started: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._checkpoint_has_models",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff._invoke_role_turn",
        lambda work_id, *_args, **_kwargs: started.append(work_id),
    )

    deliver_queue_kickoffs(root)

    assert started == [epic_id]


def test_stale_delivery_job_does_not_resume_completed_team(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    epic_id = "epic_001"
    add_doc(root, id=epic_id, title="Done", tier="epic", status="completed")
    started: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._resume_inflight_turn_if_needed",
        lambda work_id, *_args, **_kwargs: started.append(work_id),
    )

    _run_queue_delivery_locked(epic_id, "epic", root, None)

    assert started == []


def test_startup_recovery_includes_completed_team_with_pending_recovery(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, epic_id = _completed_epic_with_recovery(tmp_path)
    scheduled: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._graph_has_inflight_turn",
        lambda *_args, **_kwargs: False,
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff._schedule_queue_delivery",
        lambda work_id, *_args, **kwargs: scheduled.append(
            (work_id, bool(kwargs.get("retry_staged")))
        ),
    )
    monkeypatch.setattr(
        "cascade.workspace.supervisor_readiness.record_recovery_enqueued",
        lambda _work_id: None,
    )

    resume_inflight_graphs(root)

    assert scheduled == [(epic_id, True)]


def test_recreated_queue_is_ahead_when_old_cursor_exceeds_new_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path, git=False)
    append_event(
        "epic_001",
        Event(
            type="BranchActionRecoveryRequested",
            ts=datetime.now(timezone.utc),
            payload={"investigation_id": "recovery:action"},
            dest="epic_001",
        ),
        root=root,
    )
    size = (root / "docs/_queue/epic_001.jsonl").stat().st_size
    monkeypatch.setattr(
        "cascade.workspace.kickoff._queue_offset",
        lambda *_args, **_kwargs: size + 1,
    )

    assert _queue_is_ahead(
        "epic_001", "epic", root=root, feature_id=None
    )


def test_completed_feature_open_review_consumes_idle_queue_without_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, feature_id = _completed_feature_with_open_review(tmp_path, monkeypatch)
    append_event(
        feature_id,
        Event(
            type="TeamMessage",
            ts=datetime.now(timezone.utc),
            payload={"body": "generic poll"},
            dest=feature_id,
        ),
        root=root,
    )
    started: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._invoke_role_turn",
        lambda work_id, *_args, **_kwargs: started.append(work_id),
    )

    deliver_queue_kickoffs(root)
    deliver_queue_kickoffs(root)

    assert started == []
    assert not _queue_is_ahead(feature_id, "feature", root=root, feature_id=None)


def test_completed_feature_current_admitted_repair_wakes_once_after_restart(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, feature_id = _completed_feature_with_open_review(tmp_path, monkeypatch)
    monkeypatch.setattr(
        "cascade.feature.repair.current_feature_repair_record",
        lambda *_args, **_kwargs: {
            "generation": 1,
            "phase": "authority_recorded",
            "next_action": "resume_original_delivery",
        },
    )
    append_event(
        feature_id,
        Event(
            type="FeatureRepairAuthorized",
            ts=datetime.now(timezone.utc),
            payload={"feature_id": feature_id, "generation": 1},
            dest=feature_id,
        ),
        root=root,
    )
    scheduled: list[tuple[str, bool]] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._schedule_queue_delivery",
        lambda work_id, *_args, **kwargs: scheduled.append(
            (work_id, bool(kwargs.get("retry_staged")))
        ),
    )

    resume_inflight_graphs(root)

    assert scheduled == [(feature_id, True)]

    started: list[str] = []
    monkeypatch.setattr(
        "cascade.workspace.kickoff._checkpoint_has_models",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "cascade.workspace.kickoff._invoke_role_turn",
        lambda work_id, *_args, **_kwargs: started.append(work_id),
    )
    _run_queue_delivery_locked(feature_id, "feature", root, None)
    _run_queue_delivery_locked(feature_id, "feature", root, None)

    assert started == [feature_id]
    assert not _queue_is_ahead(feature_id, "feature", root=root, feature_id=None)


def test_completed_feature_discovery_batches_delivery_projection(tmp_path, monkeypatch):
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    for i in range(1, 5):
        add_doc(root, id=f"feat_{i:03d}", title=f"Feature {i}", tier="feature", status="completed", parent="epic_001")
    calls = []
    def project(ids, *, root):
        calls.append(set(ids))
        return {work_id: {"phase": "verified_integrated"} for work_id in ids}
    monkeypatch.setattr("cascade.review.feature_delivery_views", project)
    monkeypatch.setattr("cascade.workspace.kickoff._queue_is_ahead", lambda *_a, **_k: False)
    monkeypatch.setattr("cascade.workspace.kickoff._graph_has_inflight_turn", lambda *_a, **_k: False)
    monkeypatch.setattr("cascade.workspace.kickoff._unanswered_staged_input", lambda *_a, **_k: False)
    resume_inflight_graphs(root)
    deliver_queue_kickoffs(root)
    expected = {f"feat_{i:03d}" for i in range(1, 5)}
    assert calls == [expected, expected]
