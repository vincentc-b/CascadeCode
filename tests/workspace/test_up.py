"""cascade up supervisor entry (task_064)."""

from __future__ import annotations

import importlib
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from cascade.workspace import WorkspaceError, init_workspace, up
from cascade.workspace.kickoff import kickoff_turn, wait_for_background_kickoffs
from cascade.workspace.lock import SupervisorLock
from cascade.workspace.types import KickoffReason
from cascade.workspace.up import resume_legally_active_graphs
from tests.support import make_git_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


def _seed_trunk_commit(root: Path) -> None:
    (root / "README.md").write_text("workspace\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init board")


def _wait_for_http(url: str, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url) as resp:
                if resp.status == 200:
                    return
        except (urllib.error.URLError, OSError) as exc:
            last_error = exc
            time.sleep(0.05)
    raise AssertionError(f"server did not respond at {url}: {last_error}")


def _get_board(url: str) -> dict:
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode())


def test_up_starts_war_room_on_trunk(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    _seed_trunk_commit(root)
    port = _free_port()
    stop = threading.Event()

    thread = threading.Thread(
        target=up,
        kwargs={"root": root, "host": "127.0.0.1", "port": port, "stop_when": stop.is_set},
        daemon=True,
    )
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        _wait_for_http(f"{base}/api/board")
        body = _get_board(f"{base}/api/board")
        assert "epics" in body or "items" in body or isinstance(body, dict)
    finally:
        stop.set()
        thread.join(timeout=10)


def test_launcher_readiness_accepts_high_file_descriptor() -> None:
    import fcntl

    from cascade.workspace.launcher import _wait_readiness

    read_fd, write_fd = os.pipe()
    high_fd = fcntl.fcntl(read_fd, fcntl.F_DUPFD, 1024)

    class RunningWorker:
        returncode = None

        def poll(self):
            return None

    try:
        os.write(write_fd, b"ready\n")
        _wait_readiness(high_fd, proc=RunningWorker(), stop_requested=lambda: False)
    finally:
        os.close(high_fd)
        os.close(read_fd)
        os.close(write_fd)


def test_up_refuses_integration_branch_checkout(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    _seed_trunk_commit(root)
    _git(root, "checkout", "-b", "task/foo")

    with pytest.raises(WorkspaceError, match="product trunk"):
        up(root, port=_free_port(), stop_when=lambda: True)


def test_second_up_refuses_while_lock_held(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    _seed_trunk_commit(root)
    port = _free_port()

    held = SupervisorLock(root)
    held.acquire()
    try:
        with pytest.raises(WorkspaceError, match="already running"):
            up(root, port=port, stop_when=lambda: True)
    finally:
        held.release()


def test_up_refuses_without_board_layout(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    _seed_trunk_commit(root)

    with pytest.raises(WorkspaceError, match="cascade init"):
        up(root, port=_free_port(), stop_when=lambda: True)


def test_up_keeps_listener_after_loaded_python_source_changes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    _seed_trunk_commit(root)
    source = tmp_path / "installed" / "cascade"
    source.mkdir(parents=True)
    module = source / "runtime.py"
    module.write_text("VERSION = 1\n", encoding="utf-8")
    port = _free_port()
    up_module = importlib.import_module("cascade.workspace.up")
    worker_module = importlib.import_module("cascade.workspace.worker")
    fingerprint = up_module._source_fingerprint
    monkeypatch.setattr(up_module, "_source_fingerprint", lambda: fingerprint(source))
    monkeypatch.setattr(worker_module, "_source_fingerprint", lambda: fingerprint(source))
    monkeypatch.setattr(up_module, "_SOURCE_CHECK_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(worker_module, "_SOURCE_CHECK_INTERVAL_SECONDS", 0.01)
    stop = threading.Event()
    relaunched = threading.Event()

    def update_after_start() -> None:
        base = f"http://127.0.0.1:{port}"
        _wait_for_http(f"{base}/api/board")
        module.write_text("VERSION = 2\n", encoding="utf-8")
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline:
            try:
                _wait_for_http(f"{base}/api/board", timeout=1.0)
            except AssertionError:
                time.sleep(0.05)
                continue
            relaunched.set()
            return
        raise AssertionError("listener did not recover after source change")

    updater = threading.Thread(target=update_after_start, daemon=True)
    thread = threading.Thread(
        target=up,
        kwargs={"root": root, "port": port, "stop_when": stop.is_set},
        daemon=True,
    )
    thread.start()
    updater.start()
    try:
        updater.join(timeout=20)
        assert relaunched.is_set()
    finally:
        stop.set()
        thread.join(timeout=15)


def test_long_inflight_resume_does_not_block_startup_progression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    turn_started = threading.Event()
    release_turn = threading.Event()
    startup_progressed = threading.Event()
    repairs: list[str] = []

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.retire_terminal_registered_worktrees",
        lambda _root: repairs.append("retire"),
    )
    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.repair_all_registered",
        lambda _root: repairs.append("repair"),
    )

    def long_model_turn(_reason: KickoffReason, _root: Path) -> None:
        turn_started.set()
        release_turn.wait()

    monkeypatch.setattr("cascade.workspace.kickoff._run_kickoff", long_model_turn)

    def resume_one_graph(root: Path) -> None:
        kickoff_turn(
            KickoffReason(
                kind="resume_inflight",
                work_id="epic_startup_test",
                by="watchdog",
                root=root,
            )
        )

    monkeypatch.setattr(
        "cascade.workspace.kickoff.resume_inflight_graphs", resume_one_graph
    )

    def startup() -> None:
        resume_legally_active_graphs(tmp_path)
        startup_progressed.set()

    thread = threading.Thread(target=startup, daemon=True)
    thread.start()
    try:
        assert turn_started.wait(timeout=1)
        assert startup_progressed.wait(timeout=1)
        assert repairs == ["retire", "repair"]
    finally:
        release_turn.set()
        thread.join(timeout=2)
        assert wait_for_background_kickoffs(timeout=2)
