"""Open merge requests appear and disappear in the lifecycle browser flow (task_013)."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from tests.lifecycle.scenario import write_scenario_open_review

_DIR = Path(__file__).resolve().parent
_BROWSER_FLOW = _DIR / "open_reviews_browser_flow.mjs"


def _find_node() -> str | None:
    node = shutil.which("node")
    if node:
        return node
    for candidate in ("/usr/bin/node", "/usr/local/bin/node"):
        if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
            return candidate
    return None


def _run_browser_phase(env: dict[str, str]) -> None:
    node = _find_node()
    if not node:
        import pytest

        pytest.skip("node not on PATH")
    result = subprocess.run(
        [node, str(_BROWSER_FLOW)],
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, **env},
    )
    assert result.returncode == 0, (result.stdout or "") + (result.stderr or "")


def _war_room_shell_includes_open_reviews_script(base: str) -> None:
    with urllib.request.urlopen(f"{base}/") as resp:
        html = resp.read().decode()
    assert "/static/open_reviews_pane.js" in html
    assert html.index("/static/open_reviews_pane.js") < html.index("/static/war_room.js")


def test_open_reviews_lifecycle_browser_flow(lifecycle_war_room) -> None:
    """Seed review registry, drive pane refresh against live War Room, close and refresh."""

    base = lifecycle_war_room.base_url
    scenario = lifecycle_war_room.scenario
    review_url = "https://github.example/o/r/pull/lifecycle-gate"

    _war_room_shell_includes_open_reviews_script(base)

    _run_browser_phase(
        {
            "OPEN_REVIEWS_FLOW_PHASE": "empty",
            "WAR_ROOM_BASE": base,
        }
    )

    write_scenario_open_review(
        scenario,
        scenario.ids.feature_gate,
        closed=False,
        url=review_url,
    )
    status, payload = _get_open_reviews(base)
    assert status == 200
    assert len(payload["reviews"]) == 1
    row = payload["reviews"][0]
    assert row["id"] == scenario.ids.feature_gate
    assert row["url"] == review_url

    _run_browser_phase(
        {
            "OPEN_REVIEWS_FLOW_PHASE": "open",
            "WAR_ROOM_BASE": base,
            "EXPECT_REVIEW_URL": review_url,
            "EXPECT_FEATURE_ID": scenario.ids.feature_gate,
            "EXPECT_FEATURE_TITLE": "Gate feature",
            "EXPECT_EPIC_TITLE": "Lifecycle sandbox epic",
        }
    )

    write_scenario_open_review(
        scenario,
        scenario.ids.feature_gate,
        closed=True,
        url=review_url,
    )
    _status, after_close = _get_open_reviews(base)
    assert after_close["reviews"] == []

    _run_browser_phase(
        {
            "OPEN_REVIEWS_FLOW_PHASE": "closed",
            "WAR_ROOM_BASE": base,
        }
    )


def test_open_reviews_browser_flow_failure_state() -> None:
    _run_browser_phase({"OPEN_REVIEWS_FLOW_PHASE": "failure"})


def _get_open_reviews(base: str) -> tuple[int, dict]:
    with urllib.request.urlopen(f"{base}/api/open-reviews") as resp:
        return resp.status, json.loads(resp.read().decode())
