"""Durable deduplicated convergence diagnostics (feat_012_002 / task_012_002_002)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.watchdog import append_event
from cascade.watchdog.events import read_events
from cascade.watchdog.types import Event
from cascade.workspace.convergence import (
    publish_convergence_diagnostics,
    reset_convergence_detection_for_tests,
    set_convergence_clock_for_tests,
)
from cascade.war_room.toasts import events_to_toasts
from tests.support import add_doc, approve_board_feature, make_repo


@pytest.fixture(autouse=True)
def _reset_convergence_memory() -> None:
    reset_convergence_detection_for_tests()
    yield
    reset_convergence_detection_for_tests()


def _stall_toasts(root: Path) -> list[Event]:
    events, _ = read_events("war_room", 0, root=root)
    return [
        event
        for event in events
        if event.type == "Toast" and event.payload.get("kind") == "convergence_stall"
    ]


def test_newly_stalled_item_emits_one_durable_diagnostic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 60\n",
        encoding="utf-8",
    )
    now = {"t": 100.0}
    set_convergence_clock_for_tests(lambda: now["t"])

    publish_convergence_diagnostics(root=root)
    assert _stall_toasts(root) == []

    now["t"] = 161.0
    publish_convergence_diagnostics(root=root)
    toasts = _stall_toasts(root)
    assert len(toasts) == 1
    payload = toasts[0].payload
    assert payload["id"] == "feat_001"
    assert payload["blocker"] == "no_durable_progress"
    assert payload["stall_threshold_seconds"] == 60
    assert payload["stalled_for_seconds"] == pytest.approx(61.0)
    assert payload["progress_signature"]
    mapped = events_to_toasts([toasts[0]])
    assert mapped[0]["kind"] == "convergence_stall"
    assert mapped[0]["link"] == "/api/doc/feat_001"


def test_unchanged_stall_evidence_is_not_repeated_every_poll(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 10\n",
        encoding="utf-8",
    )
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    publish_convergence_diagnostics(root=root)
    now["t"] = 100.0
    publish_convergence_diagnostics(root=root)
    assert len(_stall_toasts(root)) == 1

    now["t"] = 500.0
    publish_convergence_diagnostics(root=root)
    assert len(_stall_toasts(root)) == 1


def test_recovery_then_stall_emits_fresh_diagnostic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    approve_board_feature(root, "feat_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 10\n",
        encoding="utf-8",
    )
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    publish_convergence_diagnostics(root=root)
    now["t"] = 100.0
    publish_convergence_diagnostics(root=root)
    assert len(_stall_toasts(root)) == 1

    append_event(
        "feat_001",
        Event(
            type="FeatureReadyToPlan",
            ts=datetime.now(timezone.utc),
            payload={"id": "feat_001"},
            dest="feat_001",
        ),
        root=root,
    )
    publish_convergence_diagnostics(root=root)
    assert len(_stall_toasts(root)) == 1

    now["t"] = 200.0
    publish_convergence_diagnostics(root=root)
    assert len(_stall_toasts(root)) == 2


def test_gated_item_does_not_emit_convergence_stall_toast(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    (root / "cascade.toml").write_text(
        "[convergence]\nstall_threshold_seconds = 1\n",
        encoding="utf-8",
    )
    now = {"t": 0.0}
    set_convergence_clock_for_tests(lambda: now["t"])
    publish_convergence_diagnostics(root=root)
    now["t"] = 100.0
    publish_convergence_diagnostics(root=root)
    assert _stall_toasts(root) == []
