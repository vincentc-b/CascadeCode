"""End-to-end late-minted feature approval via War Room HTTP (feat_020_002 / task_020_002_002)."""

from __future__ import annotations

import json
import subprocess
import threading
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.approvals import feature_approved
from tests.support import approve_epic_plan_when_ready
from cascade.automation import reset_automation_memory
from cascade.board.store import move_doc, read_doc
from cascade.war_room.server import serve
from cascade.watchdog import activate_epic, dispatch_feature, read_events
from cascade.workspace.integration_worktree import get_integration_worktree
from cascade.workspace.kickoff import install_kickoff, wait_for_background_kickoffs
from tests.support import add_doc, commit_board, make_repo
from tests.war_room.test_board_feature_readiness import _feature_row, _has_blocker
from tests.war_room.test_dispatch_routes import _get, _post
from tests.war_room.test_http_read import _free_port


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


def _enable_automation(root: Path) -> None:
    root.joinpath("cascade.toml").write_text(
        "[automation]\nenabled = true\n",
        encoding="utf-8",
    )


def _ready_to_plan_events(feature_id: str, *, root: Path) -> list[object]:
    events, _ = read_events(feature_id, 0, root=root)
    return [event for event in events if event.type == "FeatureReadyToPlan"]


def _assert_war_room_feature_approve_action() -> None:
    js_path = (
        Path(__file__).resolve().parents[2] / "cascade" / "war_room" / "static" / "war_room.js"
    )
    source = js_path.read_text(encoding="utf-8")
    assert "featureApproveActionButton" in source
    assert 'dispatch("/api/approve_feature", { id: item.id })' in source
    assert "Awaiting feature approval" in source


def _approve_initial_epic_plan(root: Path) -> None:
    add_doc(root, id="epic_001", title="Active epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Initial child", tier="feature", parent="epic_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_epic_plan_when_ready("epic_001", root=root)
    assert feature_approved("feat_001", root=root)
    reset_automation_memory()


def _start_war_room(root: Path) -> tuple[str, object, threading.Thread]:
    port = _free_port()
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{port}", server, thread


def _shutdown(server, thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def test_late_minted_feature_approval_and_single_dispatch_e2e(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)

    kickoff_work_ids: list[str] = []

    def stub_run_kickoff(reason, repo):  # type: ignore[no-untyped-def]
        kickoff_work_ids.append(reason.work_id)

    monkeypatch.setattr("cascade.workspace.kickoff._run_kickoff", stub_run_kickoff)

    late_ok_dispatches: list[str] = []
    real_dispatch = dispatch_feature

    def counting_dispatch(work_id: str, by: str, *, root=None):  # type: ignore[no-untyped-def]
        result = real_dispatch(work_id, by, root=root)
        if work_id == "feat_002" and result.ok:
            late_ok_dispatches.append(by)
        return result

    monkeypatch.setattr("cascade.automation.dispatch_feature", counting_dispatch)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(root)
    move_doc("feat_001", "completed", root=root)
    commit_board(root)
    add_doc(root, id="feat_002", title="Late mint", tier="feature", parent="epic_001")
    commit_board(root)
    assert not feature_approved("feat_002", root=root)

    base, server, thread = _start_war_room(root)
    install_kickoff(root)
    kickoff_work_ids.clear()
    try:
        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        assert late_row["readiness"]["approved"] is False
        assert _has_blocker(late_row["readiness"]["blockers"], "not_approved")
        _assert_war_room_feature_approve_action()

        request_thread = threading.current_thread()
        inline_kickoffs: list[str] = []

        def track_request_thread_kickoff(reason, repo):  # type: ignore[no-untyped-def]
            if threading.current_thread() is request_thread:
                inline_kickoffs.append(reason.work_id)
            kickoff_work_ids.append(reason.work_id)

        monkeypatch.setattr(
            "cascade.workspace.kickoff._run_kickoff",
            track_request_thread_kickoff,
        )

        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is True
        assert inline_kickoffs == []
        assert wait_for_background_kickoffs(timeout=15)
        assert kickoff_work_ids.count("feat_002") >= 1

        assert feature_approved("feat_002", root=root)
        assert len(late_ok_dispatches) == 1, "expected one successful feat_002 dispatch"
        assert read_doc("feat_002", root=root).meta.path.parent.name == "2_active"
        assert len(_ready_to_plan_events("feat_002", root=root)) == 1
        assert get_integration_worktree(root, "feature", "feat_002") is not None

        kickoff_work_ids.clear()
        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is False
        assert wait_for_background_kickoffs(timeout=15)
        assert kickoff_work_ids.count("feat_002") == 0
        assert len(late_ok_dispatches) == 1
        assert len(_ready_to_plan_events("feat_002", root=root)) == 1

        _status, board = _get(f"{base}/api/board")
        active_ids = {row["id"] for row in board["features"]["2_active"]}
        assert "feat_002" in active_ids
        assert "readiness" not in _feature_row(board, "feat_002")
    finally:
        _shutdown(server, thread)


def test_late_mint_approval_blocked_by_unmerged_dependency_sibling(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(root)
    add_doc(root, id="feat_003", title="Open sibling", tier="feature", parent="epic_001")
    add_doc(
        root,
        id="feat_002",
        title="Late mint",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_003"],
    )
    commit_board(root)

    base, server, thread = _start_war_room(root)
    try:
        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        assert late_row["readiness"]["approved"] is False

        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is True
        assert feature_approved("feat_002", root=root)
        assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"
        assert len(_ready_to_plan_events("feat_002", root=root)) == 0

        _status, board = _get(f"{base}/api/board")
        late_row = _feature_row(board, "feat_002")
        blockers = late_row["readiness"]["blockers"]
        assert _has_blocker(blockers, "unmet_deps")
        assert any(item.startswith("unmet_deps:feat_003") for item in blockers)
    finally:
        _shutdown(server, thread)


def test_late_mint_approval_blocked_when_dependency_sibling_in_review(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("cascade.watchdog.dispatch.invoke_boot", lambda *_args: None)
    monkeypatch.setattr("cascade.workspace.kickoff.kickoff_turn", lambda *_args: None)

    root = make_repo(tmp_path, git=True)
    _enable_automation(root)
    _initial_commit(root)
    _approve_initial_epic_plan(root)
    add_doc(
        root,
        id="feat_003",
        title="Sibling in review",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    state = root / ".cascade" / "reviews.json"
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text(
        json.dumps(
            {
                "feat_003": {
                    "url": "https://github.example/pull/9",
                    "closed": False,
                }
            }
        ),
        encoding="utf-8",
    )
    add_doc(
        root,
        id="feat_002",
        title="Late mint",
        tier="feature",
        parent="epic_001",
        depends_on=["feat_003"],
    )
    commit_board(root)

    base, server, thread = _start_war_room(root)
    try:
        status, body = _post(f"{base}/api/approve_feature", {"id": "feat_002"})
        assert status == HTTPStatus.OK
        assert body["newly_approved"] is True
        assert read_doc("feat_002", root=root).meta.path.parent.name == "1_backlog"

        _status, board = _get(f"{base}/api/board")
        blockers = _feature_row(board, "feat_002")["readiness"]["blockers"]
        assert _has_blocker(blockers, "feature_awaiting_merge") or _has_blocker(
            blockers, "sibling_blocked"
        )
    finally:
        _shutdown(server, thread)
