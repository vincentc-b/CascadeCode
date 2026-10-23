"""Branch drift board serialization and update_integration_branch API (task_016_002_001)."""

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

from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace.integration_worktree import (
    ensure_integration_worktree,
    integration_branch,
    integration_worktree_path,
)
from tests.support import add_doc, approve_board_feature, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict) -> tuple[int, dict]:
    data = json.dumps(payload).encode("utf-8")
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


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _commit_on_branch(repo: Path, branch: str, rel: str, content: str, message: str) -> None:
    subprocess.run(["git", "checkout", branch], cwd=repo, check=True, capture_output=True)
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=repo, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


def _active_stack(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok


def _board_item(board: dict, tier: str, work_id: str) -> dict:
    key = {"epic": "epics", "feature": "features", "task": "tasks"}[tier]
    for item in board[key]["2_active"]:
        if item["id"] == work_id:
            return item
    raise AssertionError(f"{work_id} not on active board")


@pytest.fixture
def sync_server(tmp_path):
    clear_task_runs()
    root = make_repo(tmp_path, parallelism=4)
    _initial_commit(root)
    _active_stack(root)
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_on_branch(epic_wt, "epic/epic_001", "epic.txt", "epic work\n", "on epic")
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        yield base, root
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        clear_task_runs()


def test_board_serializes_branch_sync_for_active_tiers(sync_server):
    base, _root = sync_server
    status, board = _get(f"{base}/api/board")
    assert status == HTTPStatus.OK

    epic = _board_item(board, "epic", "epic_001")
    feature = _board_item(board, "feature", "feat_001")
    task = _board_item(board, "task", "task_001")

    for item in (epic, feature, task):
        sync = item["branch_sync"]
        assert sync["ok"] is True
        assert sync["ahead"] >= 0
        assert sync["behind"] >= 0
        assert "base_branch" in sync
        assert "work_branch" in sync

    assert feature["branch_sync"]["behind"] > 0
    assert feature["branch_sync"]["update_eligible"] is True
    assert feature["branch_sync"]["update_disabled_reason"] is None

    backlog = board["features"]["1_backlog"]
    assert all("branch_sync" not in item for item in backlog)


def test_update_integration_branch_success_and_no_op(sync_server):
    base, _root = sync_server
    status, body = _post(f"{base}/api/update_integration_branch", {"id": "feat_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["work_id"] == "feat_001"
    assert body["no_op"] is False
    assert body["merge_sha"]

    status, body = _post(f"{base}/api/update_integration_branch", {"id": "feat_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["no_op"] is True

    _, board = _get(f"{base}/api/board")
    feature = _board_item(board, "feature", "feat_001")
    assert feature["branch_sync"]["behind"] == 0
    assert feature["branch_sync"]["update_eligible"] is False
    assert feature["branch_sync"]["update_disabled_reason"] == "current"


def test_update_integration_branch_epic_and_task_tiers(sync_server):
    base, root = sync_server
    create_task_worktree(
        "task_001",
        root=root,
        parent_rev=None,
        skills=[],
        base_ref=integration_branch("feature", "feat_001"),
    )
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_on_branch(feat_wt, "feat/feat_001", "feat.txt", "feat work\n", "on feat")

    status, task_body = _post(f"{base}/api/update_integration_branch", {"id": "task_001"})
    assert status == HTTPStatus.OK
    assert task_body["ok"] is True
    assert task_body["work_id"] == "task_001"


def test_update_integration_branch_dirty_index(sync_server):
    base, root = sync_server
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    dirty = feat_wt / "staged.txt"
    dirty.write_text("staged\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=feat_wt, check=True, capture_output=True)

    code, body = _post_expect_error(
        f"{base}/api/update_integration_branch", {"id": "feat_001"}
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert body["ok"] is False
    assert body["reason"] == "dirty_index"
    assert "guidance" in body
    assert "git" not in body["guidance"].lower()


def test_update_integration_branch_conflict_paths_and_no_raw_git(sync_server):
    base, root = sync_server
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    rel = "conflict.txt"
    _commit_on_branch(epic_wt, "epic/epic_001", rel, "base side\n", "epic change")
    _commit_on_branch(feat_wt, "feat/feat_001", rel, "work side\n", "feature change")

    code, body = _post_expect_error(
        f"{base}/api/update_integration_branch", {"id": "feat_001"}
    )
    assert code == HTTPStatus.CONFLICT
    assert body["reason"] == "branch_conflict"
    assert body["merge_aborted"] is True
    assert rel in body["conflict_paths"]
    serialized = json.dumps(body)
    assert "CONFLICT" not in serialized
    assert "<<<<<<" not in serialized


def test_update_integration_branch_not_found(sync_server):
    base, _root = sync_server
    code, body = _post_expect_error(
        f"{base}/api/update_integration_branch", {"id": "feat_nope"}
    )
    assert code == HTTPStatus.NOT_FOUND
    assert body["reason"] == "not_found"


def test_merge_task_branch_uses_actionable_conflict_payload(sync_server):
    base, root = sync_server
    run = create_task_worktree(
        "task_001",
        root=root,
        parent_rev=None,
        skills=[],
        base_ref=integration_branch("feature", "feat_001"),
    )
    rel = "merge-conflict.txt"
    _commit_in_worktree(run.worktree, rel, "task side\n", "task side")

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    (feat_wt / rel).write_text("feature side\n", encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=feat_wt, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feature side"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
    )

    code, body = _post_expect_error(f"{base}/api/merge_task_branch", {"id": "task_001"})
    assert code == HTTPStatus.CONFLICT
    assert body["reason"] == "branch_conflict"
    assert body["merge_aborted"] is True
    assert rel in body["conflict_paths"]
    assert "guidance" in body
