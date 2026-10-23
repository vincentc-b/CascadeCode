"""Forever-connected fake provider end-to-end stall recovery (feat_012_004 / task_012_004_004)."""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import textwrap
import threading
import time
from pathlib import Path

import pytest

from cascade.agent.fake_provider import run_fake_role
from cascade.agent.turn_registry import get_live_turn, register_turn, set_current_turn_pid
from cascade.agent.types import RoleResult, RoleTurn
from cascade.task.checkpoint import checkpoint_path
from cascade.task.execution import execution_view, mark_running, read_in_flight_turn, read_stall_disposition
from cascade.task.worktree import TaskRun, clear_task_runs
from cascade.watchdog.events import read_events
from cascade.watchdog.loop import clear_watchdog_memory, watchdog_tick
from cascade.workspace.in_flight_turn_watchdog import (
    maintain_in_flight_turn_progress,
    reset_in_flight_turn_watchdog_for_tests,
    swe_task_turn_context,
)
from cascade.workspace.stall_cancellation import reset_stall_cancellation_for_tests
from cascade.workspace.turn_progress import reset_turn_progress_for_tests, set_turn_progress_clock_for_tests
import cascade.task.worktree as task_worktree_module


@pytest.fixture(autouse=True)
def _reset_watchdog_state() -> None:
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()
    reset_in_flight_turn_watchdog_for_tests()
    clear_task_runs()
    clear_watchdog_memory()
    yield
    reset_turn_progress_for_tests()
    reset_stall_cancellation_for_tests()
    reset_in_flight_turn_watchdog_for_tests()
    clear_task_runs()
    clear_watchdog_memory()


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


def _register_task_run(task_id: str, wt_root: Path) -> None:
    task_worktree_module._runs[task_id] = TaskRun(
        task_id=task_id,
        branch=f"task/{task_id}",
        worktree=wt_root,
        base_sha="abc123",
        parent_rev=None,
        skills=[],
        state="coding",
    )


def _seed_repo(root: Path, task_id: str) -> tuple[Path, Path]:
    root.joinpath("cascade.toml").write_text(
        "[turn_progress]\nno_progress_deadline_seconds = 2\n",
        encoding="utf-8",
    )
    cp = checkpoint_path(task_id, root=root)
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_bytes(b"checkpoint-v1")

    wt_root = root / ".cascade" / "worktrees" / f"task_{task_id}"
    wt_root.mkdir(parents=True)
    dirty = wt_root / "dirty.txt"
    dirty.write_text("keep-me", encoding="utf-8")

    registry = root / ".cascade" / "worktrees.json"
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "kind": "task",
                        "work_id": task_id,
                        "branch": f"task/{task_id}",
                        "path": wt_root.relative_to(root).as_posix(),
                        "base_sha": "abc123",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    _register_task_run(task_id, wt_root)
    return cp, dirty


async def _bound_fake_role(turn: RoleTurn, *, bridge_pid: int | None) -> RoleResult:
    with register_turn(turn.role) as live:
        if bridge_pid is not None:
            set_current_turn_pid(bridge_pid)
        return await run_fake_role(turn)


def _wait_for_turn_binding(task_id: str, root: Path, timeout: float = 5.0) -> str:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        row = read_in_flight_turn(task_id, root=root)
        if row and row.get("turn_id"):
            return str(row["turn_id"])
        time.sleep(0.02)
    raise AssertionError("in-flight turn binding never appeared")


def test_forever_connected_provider_bounded_recovery_and_idempotency(tmp_path: Path) -> None:
    task_id = "task_012_004_004"
    cp, dirty = _seed_repo(tmp_path, task_id)
    mark_running(task_id, root=tmp_path)

    stalled_bridge = _spawn_sigterm_ignoring_process()
    other_bridge = _spawn_sleeping_process()
    stalled_error: list[BaseException] = []
    other_error: list[BaseException] = []

    wt_root = tmp_path / ".cascade" / "worktrees" / f"task_{task_id}"

    def _run_stalled() -> None:
        try:

            async def _main() -> None:
                turn = RoleTurn(
                    role="swe",
                    provider="fake",
                    model_id="forever-connected",
                    prompt="stall",
                    cwd=wt_root.resolve(),
                    tools=[],
                )
                with swe_task_turn_context(
                    task_id,
                    provider="fake",
                    model_id="forever-connected",
                    root=tmp_path,
                ):
                    await _bound_fake_role(turn, bridge_pid=stalled_bridge.pid)

            asyncio.run(_main())
        except BaseException as exc:
            stalled_error.append(exc)

    def _run_other() -> None:
        try:
            async def _other() -> None:
                with register_turn("swe") as live:
                    set_current_turn_pid(other_bridge.pid)
                    await asyncio.sleep(3600)

            asyncio.run(_other())
        except asyncio.CancelledError:
            pass
        except BaseException as exc:
            other_error.append(exc)

    stalled_thread = threading.Thread(target=_run_stalled, daemon=True)
    other_thread = threading.Thread(target=_run_other, daemon=True)
    stalled_thread.start()
    other_thread.start()

    try:
        assert not stalled_error, stalled_error[0] if stalled_error else None
        stalled_turn_id = _wait_for_turn_binding(task_id, tmp_path)
        other_turn_id = None
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            from cascade.agent.turn_registry import live_turns

            others = [turn.turn_id for turn in live_turns() if turn.turn_id != stalled_turn_id]
            if others:
                other_turn_id = others[0]
                break
            time.sleep(0.02)
        assert other_turn_id is not None

        now = {"t": 0.0}
        set_turn_progress_clock_for_tests(lambda: now["t"])
        before_cp = cp.read_bytes()
        before_dirty = dirty.read_text(encoding="utf-8")

        maintain_in_flight_turn_progress(tmp_path)
        assert execution_view(task_id, root=tmp_path)["phase"] == "running"
        events, _ = read_events(task_id, 0, root=tmp_path)
        assert not [event for event in events if event.type == "TaskStallRecoveryScheduled"]

        now["t"] = 2.0
        maintain_in_flight_turn_progress(tmp_path)
        assert now["t"] >= 2.0

        stalled_bridge.wait(timeout=8.0)
        assert stalled_bridge.returncode is not None
        assert get_live_turn(stalled_turn_id) is None
        assert get_live_turn(other_turn_id) is not None
        other = get_live_turn(other_turn_id)
        assert other is not None and other.cancelled is False
        other_bridge.poll()
        assert other_bridge.poll() is None

        assert cp.read_bytes() == before_cp
        assert dirty.read_text(encoding="utf-8") == before_dirty

        from cascade.workspace.turn_progress import (
            UsefulProgressEvidence,
            checkpoint_content_fingerprint,
            task_worktree_content_fingerprint,
            useful_progress_signature,
        )

        evidence = UsefulProgressEvidence(
            checkpoint_fingerprint=checkpoint_content_fingerprint(task_id, root=tmp_path),
            worktree_fingerprint=task_worktree_content_fingerprint(task_id, root=tmp_path),
        )
        episode_signature = useful_progress_signature(evidence)
        disposition = read_stall_disposition(task_id, episode_signature, root=tmp_path)
        assert disposition is not None
        assert disposition.get("diagnostic_recorded") is True
        assert disposition.get("recovery_scheduled") is True
        diagnostic = disposition.get("diagnostic")
        assert isinstance(diagnostic, dict)
        assert diagnostic.get("task_id") == task_id
        assert diagnostic.get("turn_id") == stalled_turn_id
        assert diagnostic.get("provider") == "fake"
        assert "prompt" not in json.dumps(diagnostic).lower()

        events, _ = read_events(task_id, 0, root=tmp_path)
        recovery_events = [
            event for event in events if event.type == "TaskStallRecoveryScheduled"
        ]
        assert len(recovery_events) == 1
        assert recovery_events[0].payload["episode_signature"] == episode_signature
        assert execution_view(task_id, root=tmp_path)["phase"] == "queued"

        maintain_in_flight_turn_progress(tmp_path)
        watchdog_tick(tmp_path)
        events_after, _ = read_events(task_id, 0, root=tmp_path)
        recovery_after = [
            event for event in events_after if event.type == "TaskStallRecoveryScheduled"
        ]
        assert len(recovery_after) == 1
    finally:
        stalled_bridge.kill()
        other_bridge.kill()
        stalled_bridge.wait(timeout=5)
        other_bridge.wait(timeout=5)
        stalled_thread.join(timeout=5)
        other_thread.join(timeout=5)
