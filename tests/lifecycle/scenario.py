"""Seed and tear down a deterministic disposable lifecycle board (task_009).

Uses existing public entry points (``activate_epic``, ``approve_feature``,
``move_doc``, ``reconcile_approval_dispatch``) and the War Room HTTP harness
used elsewhere under ``tests/war_room/``. Playwright is not required today; the
same fixtures compose with browser tests when that harness is added.
"""

from __future__ import annotations

import json
import socket
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import pytest

from cascade.approvals import approve_feature, feature_approved
from cascade.automation import reconcile_approval_dispatch, reset_automation_memory
from cascade.board.store import read_doc
from cascade.boss.epic_complete import reset_epic_close_prompt_surfaces
from cascade.task.worktree import clear_task_runs, get_task_run
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, read_events
from cascade.watchdog.hooks import clear_hooks
from tests.support import add_doc, commit_board, make_repo


@dataclass(frozen=True, slots=True)
class LifecycleScenarioIds:
    """Stable work ids for the sandbox scenario (task_010 reuses these)."""

    epic: str = "epic_090"
    feature_gate: str = "feat_090"
    feature_follow: str = "feat_091"
    task_gate: str = "task_090"
    task_follow: str = "task_091"


DEFAULT_SCENARIO_IDS = LifecycleScenarioIds()


@dataclass(frozen=True, slots=True)
class LifecycleScenario:
    root: Path
    ids: LifecycleScenarioIds = DEFAULT_SCENARIO_IDS


def enable_scenario_automation(root: Path, *, poll_seconds: int = 1) -> None:
    root.joinpath("cascade.toml").write_text(
        f"[automation]\nenabled = true\npoll_seconds = {poll_seconds}\n",
        encoding="utf-8",
    )


def quiet_lifecycle_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent real agent boot during scenario tests."""

    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)


def seed_lifecycle_scenario(
    tmp_path: Path,
    *,
    ids: LifecycleScenarioIds = DEFAULT_SCENARIO_IDS,
    git: bool = True,
) -> LifecycleScenario:
    """Create a disposable repo with approval + dependency gating primed."""

    reset_automation_memory()
    clear_hooks()
    clear_task_runs()
    reset_epic_close_prompt_surfaces()

    root = make_repo(tmp_path, git=git, parallelism=4)
    enable_scenario_automation(root)
    add_doc(
        root,
        id=ids.epic,
        title="Lifecycle sandbox epic",
        tier="epic",
        status="ready_to_plan",
    )
    add_doc(
        root,
        id=ids.feature_gate,
        title="Gate feature",
        tier="feature",
        parent=ids.epic,
        children=[ids.task_gate],
    )
    add_doc(
        root,
        id=ids.feature_follow,
        title="Follow feature",
        tier="feature",
        parent=ids.epic,
        depends_on=[ids.feature_gate],
        children=[ids.task_follow],
    )
    add_doc(
        root,
        id=ids.task_gate,
        title="Gate task",
        tier="task",
        parent=ids.feature_gate,
    )
    add_doc(
        root,
        id=ids.task_follow,
        title="Follow task",
        tier="task",
        parent=ids.feature_follow,
    )
    commit_board(root, message="lifecycle scenario seed")
    assert activate_epic(ids.epic, "human", root=root).ok
    approve_feature(ids.feature_gate, root=root)
    approve_feature(ids.feature_follow, root=root)
    return LifecycleScenario(root=root, ids=ids)


def gate_feature_active(scenario: LifecycleScenario) -> bool:
    doc = read_doc(scenario.ids.feature_gate, root=scenario.root)
    return doc.meta.path.parent.name == "2_active"


def follow_feature_blocked_in_backlog(scenario: LifecycleScenario) -> bool:
    doc = read_doc(scenario.ids.feature_follow, root=scenario.root)
    return (
        feature_approved(scenario.ids.feature_follow, root=scenario.root)
        and doc.meta.path.parent.name == "1_backlog"
    )


def ready_to_plan_event_count(feature_id: str, *, root: Path) -> int:
    events, _ = read_events(feature_id, 0, root=root)
    return sum(1 for event in events if event.type == "FeatureReadyToPlan")


def task_dispatched_count(task_id: str, *, root: Path) -> int:
    events, _ = read_events(task_id, 0, root=root)
    return sum(1 for event in events if event.type == "TaskDispatched")


def feature_completed_count(epic_id: str, feature_id: str, *, root: Path) -> int:
    events, _ = read_events(epic_id, 0, root=root)
    return sum(
        1
        for event in events
        if event.type == "FeatureCompleted" and event.payload.get("feature_id") == feature_id
    )


def epic_ready_to_close_toast_count(epic_id: str, *, root: Path) -> int:
    events, _ = read_events("war_room", 0, root=root)
    return sum(
        1
        for event in events
        if event.type == "Toast"
        and event.payload.get("kind") == "epic_ready_to_close"
        and event.payload.get("epic_id") == epic_id
    )


def commit_task_run(
    task_id: str,
    *,
    rel: str = "scenario.txt",
    content: str = "scenario work\n",
    message: str | None = None,
) -> None:
    """Commit deliverable work on the active task branch (merge-gate scenarios)."""

    run = get_task_run(task_id)
    if run is None:
        raise RuntimeError(f"no active task run for {task_id}")
    path = run.worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=run.worktree, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message or f"{task_id} scenario work"],
        cwd=run.worktree,
        check=True,
        capture_output=True,
    )


def install_scenario_review_recording(
    monkeypatch: pytest.MonkeyPatch,
    scenario: LifecycleScenario,
) -> None:
    """Record open feature reviews in ``reviews.json`` without forge I/O."""

    from cascade.tracking import MergeRequest

    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)

    def ensure(feature_id: str, *, root: Path) -> MergeRequest:
        write_scenario_open_review(scenario, feature_id, closed=False)
        return MergeRequest(
            url=f"https://github.example/o/r/pull/{feature_id}",
            number="1",
            forge="github",
            source_branch=f"feat/{feature_id}",
            target_branch=f"epic/{scenario.ids.epic}",
            draft=False,
        )

    monkeypatch.setattr("cascade.review.ensure_feature_review", ensure)


def complete_scenario_gate_feature(scenario: LifecycleScenario) -> list[str]:
    """Mark the gate feature completed and release blocked follow-up dispatch."""

    from cascade.board.store import move_doc

    move_doc(scenario.ids.feature_gate, "completed", root=scenario.root)
    released = reconcile_approval_dispatch(scenario.root)
    return list(released.get("features") or [])


def write_scenario_open_review(
    scenario: LifecycleScenario,
    feature_id: str,
    *,
    closed: bool = False,
    url: str = "https://github.example/o/r/pull/sb",
) -> None:
    """Seed durable review registry state for merge-gated steps (task_010)."""

    state_path = scenario.root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, object] = {}
    if state_path.is_file():
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    payload[feature_id] = {
        "url": url,
        "number": "1",
        "forge": "github",
        "source_branch": f"feat/{feature_id}",
        "target_branch": f"epic/{scenario.ids.epic}",
        "draft": False,
        "closed": closed,
    }
    state_path.write_text(json.dumps(payload), encoding="utf-8")


def teardown_lifecycle_scenario(root: Path) -> None:
    reset_automation_memory()
    clear_hooks()
    clear_task_runs()
    reset_epic_close_prompt_surfaces()


def free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass(frozen=True, slots=True)
class LifecycleWarRoom:
    base_url: str
    scenario: LifecycleScenario
    _server: object

    def shutdown(self) -> None:
        server = self._server
        assert hasattr(server, "shutdown")
        server.shutdown()  # type: ignore[union-attr]
        server.server_close()  # type: ignore[union-attr]


def start_lifecycle_war_room(scenario: LifecycleScenario) -> Iterator[LifecycleWarRoom]:
    port = free_loopback_port()
    server = serve(root=scenario.root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    handle = LifecycleWarRoom(
        base_url=f"http://127.0.0.1:{port}",
        scenario=scenario,
        _server=server,
    )
    try:
        yield handle
    finally:
        handle.shutdown()
        thread.join(timeout=5)


def initial_git_commit(root: Path, message: str = "init") -> None:
    """One commit on an empty repo (merge/task worktree scenarios)."""

    subprocess.run(
        ["git", "config", "init.defaultBranch", "main"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    marker = root / "README.md"
    if not marker.is_file():
        marker.write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=root, check=True, capture_output=True)
