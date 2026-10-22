"""End-to-end remote backlog sync via watchdog cadence and War Room APIs (task_017)."""

from __future__ import annotations

import json
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.automation import reset_automation_memory
from cascade.watchdog import activate_epic, read_events, watchdog_tick
from cascade.watchdog.hooks import clear_hooks
from cascade.workspace.backlog_snapshot import read_provenance
from cascade.workspace.integration_worktree import get_integration_worktree
from cascade.war_room.server import serve
from tests.support import add_doc, commit_board, make_repo
from tests.test_backlog_snapshot import (
    _enable_automation,
    _push_remote_brief,
    _seed_remote,
)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, json.loads(resp.read().decode())


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _post_expect_error(url: str, payload: dict | None = None) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _git_rev(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _backlog_epic_ids(board_payload: dict) -> set[str]:
    return {row["id"] for row in board_payload["epics"].get("1_backlog", [])}


def _import_toast_count(root: Path, epic_id: str) -> int:
    events, _ = read_events("war_room", 0, root=root)
    return sum(
        1
        for event in events
        if event.type == "Toast"
        and event.payload.get("kind") == "brief_imported"
        and event.payload.get("id") == epic_id
    )


@pytest.fixture
def war_room(tmp_path: Path):
    port = _free_port()
    holder: dict[str, object] = {}

    def start(root: Path) -> str:
        server = serve(root=root, host="127.0.0.1", port=port)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        holder["server"] = server
        holder["thread"] = thread
        return f"http://127.0.0.1:{port}"

    try:
        yield start
    finally:
        server = holder.get("server")
        thread = holder.get("thread")
        if server is not None:
            server.shutdown()  # type: ignore[union-attr]
            server.server_close()  # type: ignore[union-attr]
        if thread is not None:
            thread.join(timeout=5)  # type: ignore[union-attr]


def test_remote_backlog_workflow_watchdog_board_and_activation(
    tmp_path: Path, war_room, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream, remote = _seed_remote(tmp_path)

    root = make_repo(tmp_path / "operator")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    add_doc(root, id="epic_001", title="Local active", tier="epic", status="ready_to_plan")
    commit_board(root, "local epic")
    (root / "cascade_local.txt").write_text("cascade-only\n", encoding="utf-8")
    subprocess.run(["git", "add", "cascade_local.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "cascade only"], cwd=root, check=True, capture_output=True)
    _enable_automation(root)
    reset_automation_memory()
    clear_hooks()

    monkeypatch.setattr("cascade.watchdog.hooks.invoke_boot", lambda *args, **kwargs: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("cascade.automation.advance_work", lambda _root: {"features": [], "tasks": []})
    monkeypatch.setattr("cascade.automation.poll_reviews", lambda _root: None)

    assert activate_epic("epic_001", "human", root=root).ok
    local_epic_wt = get_integration_worktree(root, "epic", "epic_001")
    assert local_epic_wt is not None
    branch_before = _git_rev(root, "branch", "--show-current")
    head_before = _git_rev(root, "rev-parse", "HEAD")

    base = war_room(root)
    status, board = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    assert "epic_090" not in _backlog_epic_ids(board)

    _push_remote_brief(upstream, "epic_090", "Remote workflow")
    reset_automation_memory()
    watchdog_tick(root)

    status, board = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    assert "epic_090" in _backlog_epic_ids(board)
    assert _import_toast_count(root, "epic_090") == 1

    status, activated = _post(f"{base}/api/activate_epic", {"id": "epic_090"})
    assert status == HTTPStatus.OK
    assert activated["ok"] is True

    assert _git_rev(root, "branch", "--show-current") == branch_before
    assert _git_rev(root, "rev-parse", "HEAD") == head_before
    assert get_integration_worktree(root, "epic", "epic_001") == local_epic_wt
    remote_epic_wt = get_integration_worktree(root, "epic", "epic_090")
    assert remote_epic_wt is not None
    provenance = read_provenance(root)
    assert provenance is not None
    assert remote_epic_wt.base_sha == provenance.sha

    status, repeat_board = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    backlog_rows = repeat_board["epics"]["1_backlog"]
    assert sum(row["id"] == "epic_090" for row in backlog_rows) == 0

    reset_automation_memory()
    watchdog_tick(root)
    status, pull = _post(f"{base}/api/sync/pull", {})
    assert status == HTTPStatus.OK
    assert pull["new_briefs"] == []
    assert _import_toast_count(root, "epic_090") == 1


def test_forced_sync_pull_surfaces_error_and_keeps_snapshot(
    tmp_path: Path, war_room, monkeypatch: pytest.MonkeyPatch
) -> None:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_091", "Stable")

    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    (root / "README.md").write_text("local\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local"], cwd=root, check=True, capture_output=True)
    _enable_automation(root)
    reset_automation_memory()

    base = war_room(root)
    status, first = _post(f"{base}/api/sync/pull", {})
    assert status == HTTPStatus.OK
    assert first["new_briefs"] == ["epic_091"]
    good = read_provenance(root)
    assert good is not None

    def boom(args, root_path, check=True):
        if args[:2] == ["fetch", "origin"]:
            return subprocess.CompletedProcess(args, 1, "", "network down")
        raise AssertionError(args)

    monkeypatch.setattr("cascade.workspace.backlog_snapshot.git_run", boom)

    code, err = _post_expect_error(f"{base}/api/sync/pull", {})
    assert code == HTTPStatus.CONFLICT
    assert "network down" in err["error"]
    assert read_provenance(root) == good
    status, board = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK
    assert "epic_091" in _backlog_epic_ids(board)
