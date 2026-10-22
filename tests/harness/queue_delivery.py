"""System-test harness for feat_017 serialized queue delivery (epic_017)."""

from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.agent.types import RoleResult
from cascade.epic.graph import clear_epic_graph_sessions
from cascade.feature.graph import clear_feature_graph_sessions
from cascade.watchdog import append_event
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks
from cascade.watchdog.loop import clear_watchdog_memory
from cascade.watchdog.types import Event
from cascade.workspace.kickoff import install_kickoff
from tests.support import add_doc, make_repo


@dataclass
class CountingBlockedTurnRunner:
    """Count planning role invocations and block mid-turn until ``release()``."""

    block_at_turn: int | None = field(default=None, init=False)
    turn_count: int = field(default=0, init=False)
    _release: threading.Event = field(default_factory=threading.Event, init=False)
    _blocked: threading.Event = field(default_factory=threading.Event, init=False)

    def arm_block_on_next_turn(self) -> None:
        """Block inside the next planning role invocation (after boot completes)."""

        self._release.clear()
        self._blocked.clear()
        self.block_at_turn = self.turn_count + 1

    def release(self) -> None:
        self._release.set()

    def wait_blocked(self, timeout: float = 10.0) -> None:
        if not self._blocked.wait(timeout):
            raise TimeoutError("turn never reached blocked state")

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        runner = self

        async def fake_epic(
            role: str,
            model_id: str,
            prompt: str,
            *,
            provider: str,
            epic_id: str,
            root: object,
        ) -> RoleResult:
            runner._enter_turn()
            return RoleResult(text=f"{role}:{prompt}", status="finished")

        async def fake_feature(
            role: str,
            model_id: str,
            prompt: str,
            *,
            provider: str,
            feature_id: str,
            root: object,
        ) -> RoleResult:
            runner._enter_turn()
            return RoleResult(text=f"{role}:{prompt}", status="finished")

        monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake_epic)
        monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", fake_feature)

    def _enter_turn(self) -> None:
        self.turn_count += 1
        if self.block_at_turn is None or self.turn_count != self.block_at_turn:
            return
        self._blocked.set()
        if not self._release.wait(30.0):
            raise TimeoutError("blocked turn was not released")


def git_commit_all(root: Path, message: str = "docs") -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True, text=True)
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


def lifecycle_event(work_id: str, event_type: str, **payload: object) -> Event:
    return Event(
        type=event_type,
        ts=datetime.now(timezone.utc),
        payload=dict(payload),
        dest=work_id,
    )


def queue_eof(work_id: str, *, root: Path) -> int:
    _, offset = read_events(work_id, 0, root=root)
    return offset


def feature_graph_values(feature_id: str, *, root: Path) -> dict:
    from cascade.feature.checkpoint import thread_config
    from cascade.feature.graph import ensure_feature_graph

    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    values = graph.get_state(config).values
    return dict(values or {})


def seed_active_feature_board(root: Path) -> str:
    """Return feature id with parent epic on the board in ``2_active``."""

    feature_id = "feat_017_001"
    add_doc(root, id="epic_017", title="Epic 017", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id=feature_id,
        title="Queue cursor feature",
        tier="feature",
        status="ready_to_plan",
        parent="epic_017",
    )
    git_commit_all(root)
    return feature_id


def install_queue_delivery_test_isolation(monkeypatch: pytest.MonkeyPatch) -> CountingBlockedTurnRunner:
    clear_epic_graph_sessions()
    clear_feature_graph_sessions()
    clear_hooks()
    clear_watchdog_memory()
    runner = CountingBlockedTurnRunner()
    runner.install(monkeypatch)
    return runner


def boot_feature_graph(root: Path, feature_id: str) -> None:
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.feature.boot import install_feature_boot_hook
    from cascade.watchdog import activate_epic, dispatch_feature

    install_epic_boot_hook(root)
    install_feature_boot_hook(root)
    install_kickoff(root)
    assert activate_epic("epic_017", "human", root=root).ok
    from tests.support import approve_board_feature

    approve_board_feature(root, feature_id)
    assert dispatch_feature(feature_id, "human", root=root).ok


def append_lifecycle_event(work_id: str, event_type: str, *, root: Path, **payload: object) -> None:
    append_event(
        work_id,
        lifecycle_event(work_id, event_type, **payload),
        root=root,
    )
