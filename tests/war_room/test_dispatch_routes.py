"""Human dispatch POST routes on the War Room server."""

from __future__ import annotations

import json
import socket
from datetime import date
import subprocess
import threading
import urllib.error
import urllib.request
from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import pytest

from cascade.board import read_doc
from cascade.comments.store import comment
from cascade.boss.epic_complete import reset_epic_close_prompt_surfaces
from cascade.boss.rollup import write_closeout
from cascade.task.worktree import clear_task_runs, create_task_worktree, get_task_run
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task, read_events
from cascade.watchdog.hooks import clear_hooks
from cascade.board.parse import render_doc
from cascade.board.paths import column_dir, column_for_status, slugify
from cascade.board.types import WorkDoc, WorkMeta
from tests.support import FEATURE_BODY, add_doc, make_repo


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _post(url: str, payload: dict | None = None, *, raw: bytes | None = None) -> tuple[int, dict]:
    data = raw if raw is not None else json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        method="POST",
        data=data,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        body = json.loads(resp.read().decode())
        return resp.status, body


def _get(url: str) -> tuple[int, dict]:
    with urllib.request.urlopen(url) as resp:
        body = json.loads(resp.read().decode())
        return resp.status, body


def _post_expect_error(url: str, payload: dict | None = None, *, raw: bytes | None = None) -> tuple[int, dict]:
    try:
        _post(url, payload, raw=raw)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode())
    raise AssertionError("expected HTTP error")


@pytest.fixture
def dispatch_board(tmp_path):
    root = make_repo(tmp_path, git=True, parallelism=4)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="feat_004", title="Open dep", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Blocked feature",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_004"],
    )
    add_doc(root, id="task_001", title="Task one", tier="task", parent="feat_001")
    add_doc(root, id="task_002", title="Task two", tier="task", parent="feat_001")
    _initial_commit(root)
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


def test_activate_epic_human_success(dispatch_board):
    base, root = dispatch_board
    status, body = _post(f"{base}/api/activate_epic", {"id": "epic_001", "by": "boss"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["reason"] is None
    assert body["event"]["type"] == "EpicActivated"
    assert body["event"]["payload"]["by"] == "human"
    assert "T" in body["event"]["ts"]
    assert read_doc("epic_001", root=root).meta.path.parent.name == "2_active"


def test_dispatch_feature_success(dispatch_board):
    base, root = dispatch_board
    assert activate_epic("epic_001", "human", root=root).ok
    status, body = _post(f"{base}/api/dispatch_feature", {"id": "feat_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["event"]["payload"]["by"] == "human"
    assert read_doc("feat_001", root=root).meta.status == "active"


def test_dispatch_task_success_and_skills_unchanged_when_null(dispatch_board):
    base, root = dispatch_board
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok
    before = read_doc("task_001", root=root)
    status, body = _post(f"{base}/api/dispatch_task", {"id": "task_001", "skills": None})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["event"]["type"] == "TaskDispatched"
    assert body["event"]["payload"]["by"] == "human"
    after = read_doc("task_001", root=root)
    assert after.meta.path.parent.name == "2_active"
    assert after.meta.skills == before.meta.skills


def test_dispatch_refusal_unmet_deps_still_200(dispatch_board):
    base, root = dispatch_board
    status, body = _post(f"{base}/api/dispatch_feature", {"id": "feat_002"})
    assert status == HTTPStatus.OK
    assert body["ok"] is False
    assert body["reason"] == "unmet_deps"
    assert body["event"] is None
    assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"


def test_dispatch_feature_refused_open_blocking_comment(dispatch_board):
    base, root = dispatch_board
    assert activate_epic("epic_001", "human", root=root).ok
    cmt_id = comment(
        "epic_001",
        "Scope",
        "Block dispatch",
        blocking=True,
        author="human",
        blocks=["feat_001"],
        root=root,
    )
    status, body = _post(f"{base}/api/dispatch_feature", {"id": "feat_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is False
    assert cmt_id in body["reason"]
    assert "/plan/epic_001#plan-comments" in body["reason"]
    assert body["event"] is None
    assert read_doc("feat_001", root=root).meta.path.parent.name == "1_backlog"


def test_bad_request_invalid_json_and_missing_id(dispatch_board):
    base, _root = dispatch_board
    code, err = _post_expect_error(f"{base}/api/dispatch_task", raw=b"not-json")
    assert code == HTTPStatus.BAD_REQUEST
    assert "error" in err

    code, err = _post_expect_error(f"{base}/api/dispatch_task", {})
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "missing id"


def _initial_commit(root: Path) -> None:
    subprocess.run(
        ["git", "config", "init.defaultBranch", "main"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


@pytest.fixture
def merge_server(tmp_path):
    clear_hooks()
    clear_task_runs()
    root = make_repo(tmp_path, parallelism=4)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_001", title="Task one", tier="task", status="active", parent="feat_001")
    from cascade.workspace.integration_worktree import ensure_integration_worktree, integration_branch

    feat_branch = integration_branch("feature", "feat_001")
    ensure_integration_worktree(
        "feature", "feat_001", branch=feat_branch, base_ref="HEAD", trunk=root
    )
    run = create_task_worktree(
        "task_001", root=root, parent_rev=None, skills=[], base_ref=feat_branch
    )
    _commit_in_worktree(run.worktree, "feature.txt", "task work\n", "task commit")
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
        clear_hooks()
        clear_task_runs()


def test_merge_task_branch_refused_open_blocking_comment(merge_server):
    base, root = merge_server
    cmt_id = comment(
        "feat_001",
        "Scope",
        "Block merge",
        blocking=True,
        author="human",
        root=root,
    )
    code, body = _post_expect_error(f"{base}/api/merge_task_branch", {"id": "task_001"})
    assert code == HTTPStatus.BAD_REQUEST
    assert body["ok"] is False
    assert cmt_id in body["reason"]
    assert "/plan/feat_001#plan-comments" in body["reason"]
    assert read_doc("task_001", root=root).meta.status == "active"


def test_merge_task_branch_success_200(merge_server):
    base, root = merge_server
    status, body = _post(f"{base}/api/merge_task_branch", {"id": "task_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True
    assert body["task_id"] == "task_001"
    assert body["branch"] == "task/task_001"
    assert body["merge_sha"]
    task = read_doc("task_001", root=root)
    assert task.meta.status == "completed"
    assert task.meta.path.parent.name == "3_completed"

    feature_events, _ = read_events("feat_001", 0, root=root)
    merged = [event for event in feature_events if event.type == "TaskMerged"]
    assert len(merged) == 1
    assert merged[0].payload == {
        "task_id": "task_001",
        "branch": "task/task_001",
        "merge_sha": body["merge_sha"],
        "target_branch": "feat/feat_001",
    }

    war_events, _ = read_events("war_room", 0, root=root)
    toasts = [
        event
        for event in war_events
        if event.type == "Toast" and event.payload.get("kind") == "task_merged"
    ]
    assert len(toasts) == 1
    assert toasts[0].payload["id"] == "task_001"


@pytest.fixture
def merge_rollup_server(tmp_path):
    clear_hooks()
    clear_task_runs()
    root = make_repo(tmp_path, parallelism=4)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        children=["task_001"],
    )
    add_doc(root, id="task_001", title="Task one", tier="task", parent="feat_001")
    write_closeout("feat_001", "All tasks merged; feature complete.", root=root)
    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    run = create_task_worktree(
        "task_001", root=root, parent_rev=None, skills=[], base_ref="feat/feat_001"
    )
    _commit_in_worktree(run.worktree, "feature.txt", "task work\n", "task commit")
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
        clear_hooks()
        clear_task_runs()


def test_merge_task_branch_rollup_completes_feature_and_surfaces_epic_close(merge_rollup_server):
    base, root = merge_rollup_server
    reset_epic_close_prompt_surfaces()
    status, body = _post(f"{base}/api/merge_task_branch", {"id": "task_001"})
    assert status == HTTPStatus.OK
    assert body["ok"] is True

    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"

    epic_events, _ = read_events("epic_001", 0, root=root)
    assert any(event.type == "FeatureCompleted" for event in epic_events)

    war_events, _ = read_events("war_room", 0, root=root)
    epic_toasts = [
        event
        for event in war_events
        if event.type == "Toast" and event.payload.get("kind") == "epic_ready_to_close"
    ]
    assert len(epic_toasts) == 1
    assert epic_toasts[0].payload["epic_id"] == "epic_001"


def test_merge_task_branch_conflict_409_leaves_task_active(merge_server):
    base, root = merge_server
    run = get_task_run("task_001")
    assert run is not None
    rel = "conflict.txt"
    _commit_in_worktree(run.worktree, rel, "from task branch\n", "task side")

    from cascade.workspace.integration_worktree import integration_worktree_path

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    path = feat_wt / rel
    path.write_text("from feature line\n", encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=feat_wt, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "feature line change"],
        cwd=feat_wt,
        check=True,
        capture_output=True,
    )

    code, body = _post_expect_error(f"{base}/api/merge_task_branch", {"id": "task_001"})
    assert code == HTTPStatus.CONFLICT
    assert body["ok"] is False
    assert body["reason"] == "merge_conflict"

    task = read_doc("task_001", root=root)
    assert task.meta.status == "active"
    assert task.meta.path.parent.name == "2_active"

    feature_events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskMerged" for event in feature_events)


def test_merge_task_branch_unknown_task_404(merge_server):
    base, _root = merge_server
    code, body = _post_expect_error(f"{base}/api/merge_task_branch", {"id": "task_nope"})
    assert code == HTTPStatus.NOT_FOUND
    assert body["ok"] is False
    assert body["reason"] == "task_not_found"


def test_merge_task_branch_missing_branch_400(tmp_path):
    root = make_repo(tmp_path / "no_branch", parallelism=4)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Root epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="active", parent="epic_001")
    add_doc(root, id="task_099", title="No branch", tier="task", status="active", parent="feat_001")
    from cascade.workspace.integration_worktree import ensure_integration_worktree, integration_branch

    feat_branch = integration_branch("feature", "feat_001")
    ensure_integration_worktree(
        "feature", "feat_001", branch=feat_branch, base_ref="HEAD", trunk=root
    )
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        code, body = _post_expect_error(f"{base}/api/merge_task_branch", {"id": "task_099"})
        assert code == HTTPStatus.BAD_REQUEST
        assert body["ok"] is False
        assert body["reason"] == "branch_missing"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_confirm_epic_complete_success_and_refusal(dispatch_board, tmp_path):
    base, _root = dispatch_board
    ready_root = make_repo(tmp_path / "ready", git=False)
    add_doc(ready_root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        ready_root,
        id="feat_001",
        title="One",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        ready_root,
        id="feat_002",
        title="Two",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    port = _free_port()
    server = serve(root=ready_root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    ready_base = f"http://127.0.0.1:{port}"
    try:
        reset_epic_close_prompt_surfaces()
        code, body = _post(f"{ready_base}/api/confirm_epic_complete", {"id": "epic_002"})
        assert code == HTTPStatus.OK
        assert body["ok"] is False
        assert body["reason"] == "not_ready"

        status, ok_body = _post(
            f"{ready_base}/api/confirm_epic_complete",
            {"id": "epic_001", "by": "boss"},
        )
        assert status == HTTPStatus.OK
        assert ok_body == {"ok": True, "epic_id": "epic_001"}
        assert read_doc("epic_001", root=ready_root).meta.status == "completed"

        war_events, _ = read_events("war_room", 0, root=ready_root)
        completed = [event for event in war_events if event.type == "EpicCompleted"]
        assert len(completed) == 1
        assert completed[0].payload == {"epic_id": "epic_001"}
        assert completed[0].dest == "war_room"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)

    code, body = _post(f"{base}/api/confirm_epic_complete", {"id": "epic_001"})
    assert code == HTTPStatus.OK
    assert body["ok"] is False
    assert body["reason"] == "not_ready"


def test_boss_drain_appends_without_dispatch(dispatch_board):
    base, root = dispatch_board
    with patch("cascade.boss.orders.dispatch_task") as mock_task:
        status, body = _post(f"{base}/api/boss_drain", {"feature_id": "feat_001"})
        assert status == HTTPStatus.ACCEPTED
        assert body["ok"] is True
        assert body["event"]["type"] == "BossDrainRequested"
        assert body["event"]["payload"] == {"feature_id": "feat_001", "by": "human"}
        mock_task.assert_not_called()
    queued, _offset = read_events("boss", 0, root=root)
    assert len(queued) == 1
    assert queued[0].type == "BossDrainRequested"


def test_get_boss_view_and_orphans(dispatch_board):
    base, root = dispatch_board
    status, body = _get(f"{base}/api/boss_view")
    assert status == HTTPStatus.OK
    assert "slots_free" in body
    assert "dispatchable_features" in body
    assert "dispatchable_tasks" in body
    assert "failed_tasks" in body
    assert "feat_001" in body["dispatchable_features"]
    assert "task_001" in body["dispatchable_tasks"]

    status, orphans_body = _get(f"{base}/api/orphans")
    assert status == HTTPStatus.OK
    assert orphans_body["orphans"] == []

    assert activate_epic("epic_001", "human", root=root).ok
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok
    blocked = read_doc("task_001", root=root)
    blocked.meta.status = "blocked"
    from cascade.board.store import write_doc

    write_doc(blocked, root=root)
    status, view = _get(f"{base}/api/boss_view")
    assert status == HTTPStatus.OK
    assert "task_001" in view["failed_tasks"]


def _write_unvalidated_orphan(root: Path, doc: WorkDoc) -> None:
    path = doc.meta.path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_doc(doc), encoding="utf-8")


def test_orphans_lists_feature_without_parent(tmp_path):
    root = make_repo(tmp_path, git=False)
    column = column_for_status("active")
    orphan = WorkDoc(
        meta=WorkMeta(
            id="feat_099",
            title="Lonely feature",
            tier="feature",
            status="active",
            parent=None,
            children=[],
            depends_on=[],
            owners=["tester"],
            skills=[],
            parent_rev=None,
            created=date(2026, 10, 9),
            updated=date(2026, 10, 9),
            path=root / column_dir("feature", column) / f"feat_099_{slugify('Lonely feature')}.md",
        ),
        body=FEATURE_BODY,
    )
    _write_unvalidated_orphan(root, orphan)
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        status, body = _get(f"{base}/api/orphans")
        assert status == HTTPStatus.OK
        assert len(body["orphans"]) == 1
        record = body["orphans"][0]
        assert record["kind"] == "feature_without_parent"
        assert record["work_id"] == "feat_099"
        assert "feat_099" in record["message"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ask_boss_dispatch_appends_event_without_move(dispatch_board):
    base, root = dispatch_board
    before = read_doc("feat_001", root=root)
    status, body = _post(
        f"{base}/api/ask_boss_dispatch",
        {"kind": "feature", "id": "feat_001", "by": "boss"},
    )
    assert status == HTTPStatus.ACCEPTED
    assert body["ok"] is True
    assert body["event"]["type"] == "BossDispatchRequested"
    assert body["event"]["dest"] == "boss"
    assert body["event"]["payload"] == {"kind": "feature", "id": "feat_001", "by": "human"}
    after = read_doc("feat_001", root=root)
    assert after.meta.path == before.meta.path
    queued, _offset = read_events("boss", 0, root=root)
    assert len(queued) == 1
    assert queued[0].type == "BossDispatchRequested"


def test_ask_boss_invalid_kind(dispatch_board):
    base, _root = dispatch_board
    code, err = _post_expect_error(
        f"{base}/api/ask_boss_dispatch",
        {"kind": "epic", "id": "epic_001"},
    )
    assert code == HTTPStatus.BAD_REQUEST
    assert err["error"] == "invalid kind"


def test_non_post_route_still_method_not_allowed(dispatch_board):
    base, _root = dispatch_board
    req = urllib.request.Request(f"{base}/api/board", method="POST", data=b"{}")
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        urllib.request.urlopen(req)
    assert exc_info.value.code == HTTPStatus.METHOD_NOT_ALLOWED
