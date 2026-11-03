"""Browser coverage for durable epic close-review controls."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from cascade.boss.epic_complete import EpicCompleteResult
from cascade.review import (
    EpicCloseBlocker,
    EpicReviewSnapshot,
    persist_epic_review_snapshot,
)
from tests.lifecycle.scenario import start_lifecycle_war_room

_BROWSER_FLOW = Path(__file__).with_name("epic_close_review_browser_flow.mjs")


def _run_browser_phase(**env: str) -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is required for browser-side lifecycle tests")
    result = subprocess.run(
        [node, str(_BROWSER_FLOW)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _with_server(scenario):
    server = start_lifecycle_war_room(scenario)
    return server, next(server)


def _stop_server(server) -> None:
    with pytest.raises(StopIteration):
        next(server)


def test_epic_close_review_controls_survive_refresh_navigation_and_restart(
    lifecycle_scenario, monkeypatch: pytest.MonkeyPatch,
) -> None:
    epic_id = lifecycle_scenario.ids.epic
    root = lifecycle_scenario.root
    review_url = "https://forge.example/reviews/epic-090"
    pending = EpicReviewSnapshot(
        stage="implementation_review_pending",
        review_url=review_url,
        source_branch=f"epic/{epic_id}",
        target_branch="main",
        forge_state="open",
    )
    persist_epic_review_snapshot(epic_id, pending, root=root)

    first_server, first = _with_server(lifecycle_scenario)
    try:
        _run_browser_phase(
            EPIC_CLOSE_FLOW_PHASE="pending",
            WAR_ROOM_BASE=first.base_url,
            EPIC_ID=epic_id,
            EXPECT_REVIEW_URL=review_url,
        )
    finally:
        _stop_server(first_server)

    # A new server process boundary must reconstruct the same controls solely
    # from the durable review registry.
    restarted_server, restarted = _with_server(lifecycle_scenario)
    try:
        _run_browser_phase(
            EPIC_CLOSE_FLOW_PHASE="pending",
            WAR_ROOM_BASE=restarted.base_url,
            EPIC_ID=epic_id,
            EXPECT_REVIEW_URL=review_url,
        )

        blocker_message = (
            "Restore forge access <script>globalThis.pwned=true</script>, then retry."
        )
        blocked = EpicReviewSnapshot(
            stage="blocked",
            review_url=review_url,
            source_branch=f"epic/{epic_id}",
            target_branch="main",
            forge_state="unknown",
            blocker=EpicCloseBlocker(
                code="review_lookup_failed",
                message=blocker_message,
                retryable=True,
            ),
        )
        persist_epic_review_snapshot(epic_id, blocked, root=root)

        def finish_close(requested_id: str, _principal: str, *, root: Path):
            assert requested_id == epic_id
            completed = EpicReviewSnapshot(
                stage="completed",
                review_url=review_url,
                source_branch=f"epic/{epic_id}",
                target_branch="main",
                forge_state="merged",
            )
            persist_epic_review_snapshot(epic_id, completed, root=root)
            return EpicCompleteResult(
                ok=True,
                close_stage="completed",
                review_url=review_url,
                source_branch=f"epic/{epic_id}",
                target_branch="main",
                forge_state="merged",
            )

        monkeypatch.setattr(
            "cascade.war_room.server.confirm_epic_complete_result", finish_close
        )
        _run_browser_phase(
            EPIC_CLOSE_FLOW_PHASE="blocked_finish",
            WAR_ROOM_BASE=restarted.base_url,
            EPIC_ID=epic_id,
            EXPECT_REVIEW_URL=review_url,
            EXPECT_BLOCKER_MESSAGE=blocker_message,
        )
    finally:
        _stop_server(restarted_server)
