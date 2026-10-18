"""War Room resolve_doc_worktree reads (task_067)."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.board.store import write_doc
from cascade.workspace.doc_root import read_doc_resolved
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.workspace.doc_root import resolve_doc_worktree
from cascade.workspace.integration_worktree import integration_worktree_path
from tests.support import add_doc, make_repo


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


def _post_expect_error(url: str, payload: dict) -> tuple[int, dict]:
    try:
        _post(url, payload)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read().decode())


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    )
    return (result.stdout or "").strip()


def _commit_all(root: Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", "docs"],
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


def _seed_active_epic(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    _commit_all(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    add_doc(
        epic_wt,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    add_doc(
        epic_wt,
        id="task_001",
        title="Task",
        tier="task",
        status="backlog",
        parent="feat_001",
    )


def _mark_body(root: Path, work_id: str, marker: str) -> None:
    doc = read_doc_resolved(work_id, root=root)
    doc_root = resolve_doc_worktree(work_id, root=root)
    doc.body = marker + "\n\n" + doc.body
    write_doc(doc, root=doc_root)


@pytest.fixture
def worktree_board(tmp_path: Path):
    root = make_repo(tmp_path, models=True, role_skills=True)
    _seed_active_epic(root)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    trunk_branch_before = _git(root, "symbolic-ref", "--short", "HEAD")
    try:
        yield base, root, trunk_branch_before
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_resolve_backlog_feature_plan_from_epic_worktree(worktree_board) -> None:
    base, root, trunk_branch = worktree_board
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    assert resolve_doc_worktree("feat_001", root=root) == epic_wt.resolve()

    _mark_body(root, "feat_001", "MARKER_EPIC_BRANCH_SPEC")
    status, doc = _get(f"{base}/api/doc/feat_001")
    assert status == HTTPStatus.OK
    assert "MARKER_EPIC_BRANCH_SPEC" in doc["body"]

    code, err = _post_expect_error(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "dispatch the feature to open its room"
    assert _git(root, "symbolic-ref", "--short", "HEAD") == trunk_branch


def test_dispatched_feature_reads_live_feature_worktree(worktree_board) -> None:
    base, root, trunk_branch = worktree_board
    assert dispatch_feature("feat_001", "human", root=root).ok
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    assert resolve_doc_worktree("feat_001", root=root) == feat_wt.resolve()

    _mark_body(root, "feat_001", "MARKER_LIVE_FEATURE_SPEC")
    status, doc = _get(f"{base}/api/doc/feat_001")
    assert status == HTTPStatus.OK
    assert "MARKER_LIVE_FEATURE_SPEC" in doc["body"]

    status, attach = _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK
    assert attach["doc"]["body"].startswith("MARKER_LIVE_FEATURE_SPEC")
    assert _git(root, "symbolic-ref", "--short", "HEAD") == trunk_branch


def test_task_plan_reads_from_feature_worktree(worktree_board) -> None:
    base, root, _trunk_branch = worktree_board
    assert dispatch_feature("feat_001", "human", root=root).ok
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    assert resolve_doc_worktree("task_001", root=root) == feat_wt.resolve()

    _mark_body(root, "task_001", "MARKER_TASK_ON_FEATURE_WT")
    status, doc = _get(f"{base}/api/doc/task_001")
    assert status == HTTPStatus.OK
    assert "MARKER_TASK_ON_FEATURE_WT" in doc["body"]

    plan_req = urllib.request.urlopen(f"{base}/plan/task_001")
    assert plan_req.status == HTTPStatus.OK


def test_active_epic_attach_uses_epic_worktree(worktree_board) -> None:
    base, root, trunk_branch = worktree_board
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    assert resolve_doc_worktree("epic_001", root=root) == epic_wt.resolve()

    _mark_body(root, "epic_001", "MARKER_EPIC_LIVE")
    status, _attach = _post(f"{base}/api/attach", {"graph_id": "epic_001"})
    assert status == HTTPStatus.OK
    status, doc = _get(f"{base}/api/doc/epic_001")
    assert "MARKER_EPIC_LIVE" in doc["body"]
    assert _git(root, "symbolic-ref", "--short", "HEAD") == trunk_branch


def test_backlog_feature_stray_branch_still_refuses_attach(worktree_board) -> None:
    base, root, trunk_branch = worktree_board
    _git(root, "branch", "feat/feat_001")
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    assert not feat_wt.is_dir()

    code, err = _post_expect_error(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "dispatch the feature to open its room"
    assert not feat_wt.is_dir()
    assert _git(root, "symbolic-ref", "--short", "HEAD") == trunk_branch


def test_attach_repairs_missing_feature_worktree(worktree_board) -> None:
    base, root, _trunk_branch = worktree_board
    assert dispatch_feature("feat_001", "human", root=root).ok
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    shutil.rmtree(feat_wt)
    assert not feat_wt.is_dir()

    status, _attach = _post(f"{base}/api/attach", {"graph_id": "feat_001"})
    assert status == HTTPStatus.OK
    assert feat_wt.is_dir()
