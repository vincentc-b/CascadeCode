from __future__ import annotations

import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from cascade.recovery_progress.live import (
    begin_live_observation,
    end_live_observation,
    refresh_live_observation,
    registered_live_observations,
    reset_live_observations_for_tests,
    set_process_probe_for_tests,
)
from cascade.task.action_recovery import create_or_load_action, resume_action
from cascade.workspace.types import KickoffReason
from tests.support import make_repo


@pytest.fixture(autouse=True)
def _reset_live_registry() -> None:
    reset_live_observations_for_tests()
    yield
    reset_live_observations_for_tests()


def test_queued_turn_is_not_a_live_invocation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace import kickoff

    root = make_repo(tmp_path)
    release = threading.Event()
    entered = threading.Event()

    def held(_reason, _repo):
        entered.set()
        assert release.wait(2)

    monkeypatch.setattr(kickoff, "_run_kickoff", held)
    with kickoff.deferred_kickoffs():
        kickoff.kickoff_turn(
            KickoffReason("queue_event", "task_001", "watchdog", root)
        )

    assert entered.wait(2)
    assert kickoff.graph_turn_owner_is_live("task_001")
    assert registered_live_observations() == ()
    release.set()
    assert kickoff.wait_for_background_kickoffs(2)


def test_admitted_graph_invocation_records_begin_and_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cascade.workspace import kickoff

    root = make_repo(tmp_path)
    entered = threading.Event()
    release = threading.Event()

    def held(_reason, _repo):
        entered.set()
        assert release.wait(2)
        return True

    monkeypatch.setattr(kickoff, "_kickoff_turn", held)
    reason = KickoffReason(
        "resume_inflight",
        "feat_001",
        "watchdog",
        root,
        action_id="feat_001:recover",
        action_generation="sha256:generation",
        attempt_number=2,
        claim_id="claim-2",
    )
    worker = threading.Thread(target=lambda: kickoff.kickoff_turn(reason))
    worker.start()
    assert entered.wait(2)

    observations = registered_live_observations()
    assert len(observations) == 1
    identity = observations[0].identity
    assert (
        identity.kind,
        identity.graph_id,
        identity.action_id,
        identity.action_generation,
        identity.attempt_number,
        identity.claim_id,
    ) == (
        "invocation",
        "feat_001",
        "feat_001:recover",
        "sha256:generation",
        2,
        "claim-2",
    )
    assert refresh_live_observation(identity).state == "live"
    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert registered_live_observations() == ()
    assert refresh_live_observation(identity).state == "unmatched"


def test_resume_action_records_only_the_matching_held_executor(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path, git=False)
    create_or_load_action(
        "task_001:delivery",
        "task_turn",
        root=root,
        attempt_bound=1,
        owning_team={"kind": "task_team", "work_id": "task_001"},
    )
    entered = threading.Event()
    release = threading.Event()

    def held(_context):
        entered.set()
        assert release.wait(2)

    worker = threading.Thread(
        target=lambda: resume_action("task_001:delivery", root=root, execute=held)
    )
    worker.start()
    assert entered.wait(2)

    observation = registered_live_observations()[0]
    identity = observation.identity
    assert identity.kind == "executor"
    assert identity.graph_id == "task_001"
    assert identity.action_id == "task_001:delivery"
    assert identity.action_generation.startswith("sha256:")
    assert identity.attempt_number == 1
    assert identity.claim_id
    assert refresh_live_observation(identity).state == "live"
    assert refresh_live_observation(
        replace(identity, attempt_number=2)
    ).state == "unmatched"
    assert refresh_live_observation(
        replace(identity, action_generation="another-generation")
    ).state == "unmatched"
    assert refresh_live_observation(
        replace(identity, claim_id="another-claim")
    ).state == "unmatched"

    release.set()
    worker.join(2)
    assert not worker.is_alive()
    assert registered_live_observations() == ()


def test_expiry_unknown_process_restart_and_stop_never_remain_live() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation = begin_live_observation(
        "executor",
        graph_id="task_001",
        action_id="action",
        action_generation="generation",
        attempt_number=1,
        claim_id="claim",
        now=now,
    )
    assert refresh_live_observation(
        observation.identity, now=now + timedelta(seconds=30)
    ).state == "stale"

    inaccessible = begin_live_observation("invocation", graph_id="feat_001")

    def denied(_pid: int):
        raise PermissionError("hidden")

    set_process_probe_for_tests(denied)
    assert refresh_live_observation(inaccessible.identity).state == "unknown"
    assert end_live_observation(inaccessible.identity)

    reset_live_observations_for_tests()
    restarted = begin_live_observation("invocation", graph_id="feat_001")
    set_process_probe_for_tests(
        lambda _pid: (restarted.identity.boot_id, restarted.identity.process_start_id + ":new")
    )
    assert refresh_live_observation(restarted.identity).state == "stale"

    reset_live_observations_for_tests()
    stopped = begin_live_observation("invocation", graph_id="feat_001")
    set_process_probe_for_tests(lambda _pid: None)
    assert refresh_live_observation(stopped.identity).state == "stale"
    assert registered_live_observations() == ()


def test_claim_expiry_caps_observation_validity() -> None:
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    observation = begin_live_observation(
        "executor",
        graph_id="task_001",
        action_id="action",
        action_generation="generation",
        attempt_number=1,
        claim_id="claim",
        claim_expires_at=now + timedelta(seconds=5),
        now=now,
    )
    assert observation.valid_until == now + timedelta(seconds=5)
    assert refresh_live_observation(
        observation.identity, now=now + timedelta(seconds=5)
    ).state == "stale"
