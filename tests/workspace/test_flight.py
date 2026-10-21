"""Flight report and overlap detection (task_068)."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import urllib.request
from http import HTTPStatus
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from cascade.agent.types import RoleResult
from cascade.watchdog import activate_epic, dispatch_feature, read_events
from cascade.watchdog.loop import clear_watchdog_memory, watchdog_tick
from cascade.war_room.serialize import flight_report_to_dict
from cascade.war_room.server import serve
from cascade.workspace.flight import clear_flight_memory, flight_report, refresh_flight_report
from cascade.workspace.integration_worktree import (
    get_integration_worktree,
    integration_worktree_path,
)
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _isolate_flight_state() -> None:
    clear_watchdog_memory()
    clear_flight_memory()
    yield
    clear_watchdog_memory()
    clear_flight_memory()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _commit_all(root: Path, message: str = "docs") -> None:
    _git(root, "add", "-A")
    result = subprocess.run(
        ["git", "commit", "-m", message],
        cwd=root,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0 and "nothing to commit" not in (result.stdout + result.stderr):
        raise subprocess.CalledProcessError(
            result.returncode,
            result.args,
            result.stdout,
            result.stderr,
        )


def _commit_file(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    _git(worktree, "add", rel)
    _git(worktree, "commit", "-m", message)


def _seed_epic_with_features(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature one",
        tier="feature",
        status="ready_to_plan",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_002",
        title="Feature two",
        tier="feature",
        status="ready_to_plan",
        parent="epic_001",
    )
    _commit_all(root)


def _activate_and_dispatch_features(root: Path) -> None:
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_feature("feat_002", "human", root=root).ok


def test_two_features_same_path_overlap(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_epic_with_features(root)
    _activate_and_dispatch_features(root)

    shared = "src/overlap_target.txt"
    feat1_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    feat2_wt = integration_worktree_path("feature", "feat_002", trunk=root)
    _commit_file(feat1_wt, shared, "from feat_001\n", "feat1 change")
    _commit_file(feat2_wt, shared, "from feat_002\n", "feat2 change")

    report = flight_report(root)
    assert shared in report.changed_paths["feat_001"]
    assert shared in report.changed_paths["feat_002"]
    assert len(report.overlaps) == 1
    overlap = report.overlaps[0]
    assert overlap.paths == (shared,)
    assert overlap.work_ids == ("feat_001", "feat_002")


def test_feature_epic_branch_overlap_after_cut(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_epic_with_features(root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok

    shared = "docs/epic_delta.txt"
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_file(epic_wt, shared, "epic landed after cut\n", "epic progress")
    _commit_file(feat_wt, shared, "feature edits same path\n", "feat change")

    report = flight_report(root)
    epic_overlaps = [o for o in report.overlaps if "epic_001" in o.work_ids]
    assert len(epic_overlaps) == 1
    assert epic_overlaps[0].paths == (shared,)
    assert epic_overlaps[0].work_ids == ("epic_001", "feat_001")


def test_watchdog_tick_refresh_advances_active_teams(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    mock = AsyncMock(return_value=RoleResult(text="ok", status="finished"))

    async def _wrapped(turn):  # type: ignore[no-untyped-def]
        return await mock(turn)

    monkeypatch.setattr("cascade.agent.adapter.run_role", _wrapped)
    monkeypatch.setattr("cascade.agent.planning_turn.run_role", _wrapped)
    monkeypatch.setattr("cascade.task.swe_turn.run_role", _wrapped)

    _seed_epic_with_features(root)
    _activate_and_dispatch_features(root)
    mock.reset_mock()

    watchdog_tick(root)
    from cascade.workspace.kickoff import wait_for_background_kickoffs

    assert wait_for_background_kickoffs()
    # The same tick refreshes the flight report and delivers queued activation
    # events. Each active Epic/Feature team runs both of its roster roles.
    assert mock.await_count == 6


def test_overlap_toast_on_new_intersection(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_epic_with_features(root)
    _activate_and_dispatch_features(root)

    refresh_flight_report(root)
    events_before, _ = read_events("war_room", 0, root=root)
    overlap_toasts_before = [
        e for e in events_before if e.type == "Toast" and e.payload.get("kind") == "flight_overlap"
    ]

    shared = "src/late_overlap.txt"
    feat1_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    feat2_wt = integration_worktree_path("feature", "feat_002", trunk=root)
    _commit_file(feat1_wt, shared, "a\n", "a")
    _commit_file(feat2_wt, shared, "b\n", "b")

    refresh_flight_report(root)
    events_after, _ = read_events("war_room", 0, root=root)
    overlap_toasts = [
        e
        for e in events_after
        if e.type == "Toast" and e.payload.get("kind") == "flight_overlap"
    ]
    assert len(overlap_toasts) == len(overlap_toasts_before) + 1
    latest = overlap_toasts[-1]
    assert latest.payload.get("paths") == [shared]
    assert set(latest.payload.get("work_ids", [])) == {"feat_001", "feat_002"}

    refresh_flight_report(root)
    events_again, _ = read_events("war_room", 0, root=root)
    overlap_again = [
        e
        for e in events_again
        if e.type == "Toast" and e.payload.get("kind") == "flight_overlap"
    ]
    assert len(overlap_again) == len(overlap_toasts)


def test_get_api_flight_matches_dataclass(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _seed_epic_with_features(root)
    _activate_and_dispatch_features(root)
    report = refresh_flight_report(root)
    expected = flight_report_to_dict(report, root=root)

    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        with urllib.request.urlopen(f"{base}/api/flight") as resp:
            assert resp.status == HTTPStatus.OK
            payload = json.loads(resp.read().decode())
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    assert payload == expected
    assert "features" in payload
    feat_entry = get_integration_worktree(root, "feature", "feat_001")
    assert feat_entry is not None
    assert payload["features"][0]["work_id"] == "feat_001"
    assert payload["features"][0]["base_sha"] == feat_entry.base_sha
