"""Update preflight integration (feat_018_003 / task_018_003_004)."""

from __future__ import annotations

from pathlib import Path

from tests.harness.cascade_up_subprocess import (
    get_supervisor_health,
    http_get,
    http_post_json,
    poll_until,
    start_cascade_up,
)


def _introduce_syntax_error(install_root: Path) -> None:
    target = install_root / "cascade" / "workspace" / "up.py"
    target.write_text(target.read_text(encoding="utf-8") + "def broken(\n", encoding="utf-8")


def test_syntax_error_in_source_triggers_update_blocked_and_keeps_serving(
    tmp_path: Path,
) -> None:
    proc = start_cascade_up(tmp_path)
    try:
        worker_before = proc.worker_pid
        assert worker_before is not None
        _introduce_syntax_error(proc.install_root)

        def _update_blocked() -> bool:
            status, health = get_supervisor_health(proc.base)
            return status == 200 and health is not None and health.get("state") == "update_blocked"

        poll_until(_update_blocked, timeout=30.0)
        assert proc.worker_pid == worker_before

        status, health = get_supervisor_health(proc.base)
        assert status == 200
        assert health is not None
        assert health.get("state") == "update_blocked"
        assert health.get("next_action") == "Fix the syntax error and save again."
        last_error = health.get("last_error") or {}
        assert last_error.get("message")
        stderr_tail = last_error.get("stderr_tail") or ""
        combined = f"{last_error.get('message')} {stderr_tail}".lower()
        assert "syntax" in combined or "invalid syntax" in combined

        board_status, _, _ = http_get(f"{proc.base}/api/board")
        assert board_status == 200
        post_status, _, body = http_post_json(
            f"{proc.base}/api/activate_epic",
            {"id": "epic_missing_probe"},
            expect_error=True,
        )
        assert post_status != 503 or body.get("error") != "updating"
    finally:
        stderr = proc.stop()
        assert proc.launcher.returncode == 0, stderr
