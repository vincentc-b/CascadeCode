"""Backoff and degraded responder integration (feat_018_003 / task_018_003_003)."""

from __future__ import annotations

import json
import urllib.error
from pathlib import Path

from tests.harness.cascade_up_subprocess import (
    clear_worker_startup_crash,
    get_supervisor_health,
    http_get,
    inject_worker_startup_crash,
    poll_until,
    start_cascade_up,
    touch_cascade_source,
    wait_for_http,
)


def _http_get_allow_503(url: str) -> tuple[int, bytes]:
    try:
        status, _, raw = http_get(url)
        return status, raw
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_startup_crash_bounded_retries_then_degraded_recovers(tmp_path: Path) -> None:
    proc = start_cascade_up(tmp_path)
    try:
        inject_worker_startup_crash(proc.install_root)
        touch_cascade_source(proc.install_root)

        def _degraded() -> bool:
            status, payload = get_supervisor_health(proc.base)
            return (
                status == 503
                and payload is not None
                and payload.get("state") == "degraded"
                and payload.get("restart_count", 0) >= 5
            )

        poll_until(_degraded, timeout=90.0)

        status, health = get_supervisor_health(proc.base)
        assert status == 503
        assert health is not None
        assert health["state"] == "degraded"
        assert health.get("last_error", {}).get("exit_code") == 42
        assert health.get("next_action")
        assert health.get("restart_count", 0) >= 5

        board_status, board_raw = _http_get_allow_503(f"{proc.base}/api/board")
        assert board_status == 503
        board_payload = json.loads(board_raw.decode())
        assert board_payload.get("state") == "degraded"

        clear_worker_startup_crash(proc.install_root)
        touch_cascade_source(proc.install_root)

        def _serving() -> bool:
            code, payload = get_supervisor_health(proc.base)
            return code == 200 and payload is not None and payload.get("state") == "serving"

        poll_until(_serving, timeout=60.0)
        wait_for_http(f"{proc.base}/api/board")
    finally:
        proc.stop()
