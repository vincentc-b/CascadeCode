"""Completed planning teams remain wakeable for routed recovery decisions."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.task.action_recovery import capture_and_route_action_failure
from cascade.watchdog import Event, append_event
from cascade.workspace.kickoff import (
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
