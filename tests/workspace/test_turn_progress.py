"""In-flight turn useful-progress and stall episodes (feat_012_004 / task_012_004_001)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.workspace.turn_progress import (
    TurnTransportLiveness,
    UsefulProgressEvidence,
    observe_turn_progress,
    reset_turn_progress_for_tests,
    set_turn_progress_clock_for_tests,
    useful_progress_signature,
)


@pytest.fixture(autouse=True)
def _reset_turn_progress() -> None:
    reset_turn_progress_for_tests()
    yield
    reset_turn_progress_for_tests()


def _alive_connected() -> TurnTransportLiveness:
    return TurnTransportLiveness(
        transport_connected=True,
        pending_provider_await=True,
        process_alive=True,
    )


def test_unchanged_evidence_retains_episode_signature() -> None:
    now = {"t": 10.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    evidence = UsefulProgressEvidence(provider_events=2, completed_tool_calls=1)
    first = observe_turn_progress(
        "turn-a",
        evidence=evidence,
        transport=_alive_connected(),
        deadline_seconds=60.0,
    )
    now["t"] = 40.0
    second = observe_turn_progress(
        "turn-a",
        evidence=evidence,
        transport=TurnTransportLiveness(lease_renewed=True, transport_connected=True),
        deadline_seconds=60.0,
    )
    assert first.episode_signature == second.episode_signature
    assert first.state == "progressing"
    assert second.state == "progressing"


def test_new_useful_progress_resets_episode_timer() -> None:
    now = {"t": 0.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    base = UsefulProgressEvidence(provider_events=1)
    observe_turn_progress("turn-b", evidence=base, deadline_seconds=100.0)
    now["t"] = 90.0
    stalled_shape = observe_turn_progress("turn-b", evidence=base, deadline_seconds=100.0)
    assert stalled_shape.state == "progressing"
    assert stalled_shape.stalled_for_seconds is None

    advanced = UsefulProgressEvidence(provider_events=2)
    observe_turn_progress("turn-b", evidence=advanced, deadline_seconds=100.0)
    now["t"] = 150.0
    after = observe_turn_progress("turn-b", evidence=advanced, deadline_seconds=100.0)
    assert after.state == "progressing"
    assert after.episode_signature != useful_progress_signature(base)
    assert after.last_progress_kind == "provider_event"


def test_no_progress_deadline_boundary(tmp_path: Path) -> None:
    root = tmp_path
    (root / "cascade.toml").write_text(
        "[turn_progress]\nno_progress_deadline_seconds = 30\n",
        encoding="utf-8",
    )
    now = {"t": 100.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    evidence = UsefulProgressEvidence()

    observe_turn_progress("turn-c", evidence=evidence, root=root)
    now["t"] = 129.9
    under = observe_turn_progress("turn-c", evidence=evidence, root=root)
    assert under.state == "progressing"

    now["t"] = 130.0
    at = observe_turn_progress("turn-c", evidence=evidence, root=root)
    assert at.state == "no_progress_deadline_exceeded"
    assert at.stalled_for_seconds == pytest.approx(30.0)

    now["t"] = 131.0
    over = observe_turn_progress("turn-c", evidence=evidence, root=root)
    assert over.state == "no_progress_deadline_exceeded"
    assert over.episode_signature == at.episode_signature


def test_connected_transport_without_progress_still_expires() -> None:
    now = {"t": 0.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    evidence = UsefulProgressEvidence()
    observe_turn_progress(
        "turn-d",
        evidence=evidence,
        transport=_alive_connected(),
        deadline_seconds=5.0,
    )
    now["t"] = 5.0
    obs = observe_turn_progress(
        "turn-d",
        evidence=evidence,
        transport=_alive_connected(),
        deadline_seconds=5.0,
    )
    assert obs.state == "no_progress_deadline_exceeded"
    assert obs.transport_connected is True
    assert obs.pending_provider_await is True


def test_lease_renewal_does_not_change_episode_signature() -> None:
    now = {"t": 0.0}
    set_turn_progress_clock_for_tests(lambda: now["t"])
    evidence = UsefulProgressEvidence(completed_tool_calls=3)
    first = observe_turn_progress(
        "turn-e",
        evidence=evidence,
        transport=TurnTransportLiveness(process_alive=True),
        deadline_seconds=120.0,
    )
    now["t"] = 50.0
    second = observe_turn_progress(
        "turn-e",
        evidence=evidence,
        transport=TurnTransportLiveness(process_alive=True, lease_renewed=True),
        deadline_seconds=120.0,
    )
    assert first.episode_signature == second.episode_signature


def test_checkpoint_and_worktree_advancement_change_signature() -> None:
    sig_a = useful_progress_signature(
        UsefulProgressEvidence(checkpoint_fingerprint=(1, 100))
    )
    sig_b = useful_progress_signature(
        UsefulProgressEvidence(checkpoint_fingerprint=(2, 100))
    )
    assert sig_a != sig_b

    sig_w1 = useful_progress_signature(UsefulProgressEvidence(worktree_fingerprint="aaa"))
    sig_w2 = useful_progress_signature(UsefulProgressEvidence(worktree_fingerprint="bbb"))
    assert sig_w1 != sig_w2
