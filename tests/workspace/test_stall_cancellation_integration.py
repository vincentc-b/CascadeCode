"""Targeted stall cancellation and preserved work (feat_012_004 / task_012_004_002)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import textwrap
import threading
from pathlib import Path

import pytest

from cascade.agent.turn_registry import get_live_turn, register_turn, set_current_turn_pid
from cascade.task.checkpoint import checkpoint_path
from cascade.workspace.stall_cancellation import (
    cancel_stalled_turn,
    capture_preserved_work_state,
    reset_stall_cancellation_for_tests,
    stall_cancellation_seam_available,
)
from cascade.workspace.turn_progress import (
    UsefulProgressEvidence,
    observe_turn_progress,
    reset_turn_progress_for_tests,
    set_turn_progress_clock_for_tests,
)


@pytest.fixture(autouse=True)
def _reset_stall_state() -> None:
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()
    yield
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()


def test_stall_cancellation_seam_is_available() -> None:
    assert stall_cancellation_seam_available()


def _spawn_sigterm_ignoring_process() -> subprocess.Popen[bytes]:
    script = textwrap.dedent(
        """
        import signal
        import time

        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        time.sleep(600)
        """
    )
    return subprocess.Popen([sys.executable, "-c", script])


def _spawn_sleeping_process() -> subprocess.Popen[bytes]:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"])


def _start_turn_thread(*, pid: int | None) -> tuple[threading.Thread, str]:
    ready = threading.Event()
    turn_id_holder: dict[str, str] = {}

    def _runner() -> None:
        async def _main() -> None:
            with register_turn("swe") as live:
                if pid is not None:
                    set_current_turn_pid(pid)
                turn_id_holder["turn_id"] = live.turn_id
                ready.set()
                try:
                    await asyncio.sleep(3600)
                except asyncio.CancelledError:
                    raise

        try:
            asyncio.run(_main())
        except asyncio.CancelledError:
            pass

    thread = threading.Thread(target=_runner, daemon=True)
    thread.start()
    assert ready.wait(timeout=5.0)
    return thread, turn_id_holder["turn_id"]


def test_cancel_stalled_turn_targets_one_process_tree(tmp_path: Path) -> None:
    stalled_proc = _spawn_sigterm_ignoring_process()
    other_proc = _spawn_sleeping_process()
    stalled_thread, stalled_turn_id = _start_turn_thread(pid=stalled_proc.pid)
    other_thread, other_turn_id = _start_turn_thread(pid=other_proc.pid)

    try:
        now = {"t": 0.0}
        set_turn_progress_clock_for_tests(lambda: now["t"])
        evidence = UsefulProgressEvidence()
        observe_turn_progress(
            stalled_turn_id,
            evidence=evidence,
            deadline_seconds=1.0,
        )
        now["t"] = 2.0
        expired = observe_turn_progress(
            stalled_turn_id,
            evidence=evidence,
            deadline_seconds=1.0,
        )
        assert expired.state == "no_progress_deadline_exceeded"

        outcome = cancel_stalled_turn(
            expired,
            task_id="task_012_004_002",
            root=tmp_path,
            grace_seconds=0.3,
        )
        assert outcome is not None
        assert outcome.turn_id == stalled_turn_id
        assert outcome.process_tree_pid == stalled_proc.pid
        assert outcome.termination == "forced"
        assert outcome.force_kill_applied is True

        stalled_proc.wait(timeout=5.0)
        assert stalled_proc.returncode is not None

        assert get_live_turn(other_turn_id) is not None
        other = get_live_turn(other_turn_id)
        assert other is not None
        assert other.cancelled is False
        other_proc.poll()
        assert other_proc.poll() is None
    finally:
        stalled_proc.kill()
        other_proc.kill()
        stalled_proc.wait(timeout=5)
        other_proc.wait(timeout=5)
        stalled_thread.join(timeout=5)
        other_thread.join(timeout=5)


def test_cancel_stalled_turn_preserves_checkpoint_and_worktree(tmp_path: Path) -> None:
    task_id = "task_012_004_001"
    cp = checkpoint_path(task_id, root=tmp_path)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(b"checkpoint-bytes")

    wt_root = tmp_path / ".cascade" / "worktrees" / f"task_{task_id}"
    wt_root.mkdir(parents=True)
    dirty = wt_root / "dirty.txt"
    dirty.write_text("keep-me", encoding="utf-8")

    registry = tmp_path / ".cascade" / "worktrees.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "kind": "task",
                        "work_id": task_id,
                        "branch": f"task/{task_id}",
                        "path": wt_root.relative_to(tmp_path).as_posix(),
                        "base_sha": "abc123",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    proc = _spawn_sleeping_process()
    thread, turn_id = _start_turn_thread(pid=proc.pid)
    try:
        now = {"t": 0.0}
        set_turn_progress_clock_for_tests(lambda: now["t"])
        evidence = UsefulProgressEvidence()
        observe_turn_progress(turn_id, evidence=evidence, deadline_seconds=0.5)
        now["t"] = 1.0
        expired = observe_turn_progress(
            turn_id,
            evidence=evidence,
            deadline_seconds=0.5,
        )

        before_cp = cp.read_bytes()
        before_dirty = dirty.read_text(encoding="utf-8")
        preserved_before = capture_preserved_work_state(task_id, root=tmp_path)

        outcome = cancel_stalled_turn(
            expired,
            task_id=task_id,
            root=tmp_path,
            grace_seconds=0.2,
        )
        assert outcome is not None
        assert outcome.preserved == preserved_before
        assert cp.read_bytes() == before_cp
        assert dirty.read_text(encoding="utf-8") == before_dirty
        assert outcome.preserved.checkpoint_present
        assert outcome.preserved.worktree_present
    finally:
        proc.kill()
        proc.wait(timeout=5)
        thread.join(timeout=5)


def test_episode_cancellation_is_idempotent_for_same_signature() -> None:
    proc = _spawn_sleeping_process()
    thread, turn_id = _start_turn_thread(pid=proc.pid)
    try:
        now = {"t": 0.0}
        set_turn_progress_clock_for_tests(lambda: now["t"])
        evidence = UsefulProgressEvidence()
        observe_turn_progress(turn_id, evidence=evidence, deadline_seconds=0.1)
        now["t"] = 1.0
        expired = observe_turn_progress(
            turn_id,
            evidence=evidence,
            deadline_seconds=0.1,
        )
        first = cancel_stalled_turn(
            expired,
            task_id="task_012_004_003",
            root=Path("/tmp/unused"),
            grace_seconds=0.1,
        )
        second = cancel_stalled_turn(
            expired,
            task_id="task_012_004_003",
            root=Path("/tmp/unused"),
            grace_seconds=0.1,
        )
        assert first is not None
        assert second is None
    finally:
        proc.kill()
        proc.wait(timeout=5)
        thread.join(timeout=5)
