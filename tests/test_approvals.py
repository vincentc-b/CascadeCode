"""Feature and epic approval persistence and API."""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from datetime import datetime
from http import HTTPStatus
from pathlib import Path

import pytest

from cascade.approvals import (
    approve_epic_plan,
    approve_feature,
    epic_plan_approved,
    feature_approved,
)
from cascade.board.errors import BoardError, GitError
from cascade.board.store import read_doc
from cascade.watchdog import activate_epic, dispatch_feature
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import integration_worktree_path
from tests.support import add_doc, approve_epic_plan_when_ready, commit_board, make_repo


def test_missing_approval_is_unapproved(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    doc = read_doc("feat_001", root=root)
    assert doc.meta.approved_at is None
    assert feature_approved("feat_001", root=root) is False


def test_approve_feature_persists_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")

    first = approve_feature("feat_001", root=root)
    assert first["newly_approved"] is True
    approved_at = read_doc("feat_001", root=root).meta.approved_at
    assert isinstance(approved_at, datetime)

    second = approve_feature("feat_001", root=root)
    assert second["newly_approved"] is False
    assert read_doc("feat_001", root=root).meta.approved_at == approved_at


def test_epic_approval_snapshots_children_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    add_doc(root, id="feat_002", title="Two", tier="feature", parent="epic_001")

    first = approve_epic_plan_when_ready("epic_001", root=root)
    assert first["features"] == ["feat_001", "feat_002"]
    assert epic_plan_approved("epic_001", root=root) is True
    assert feature_approved("feat_001", root=root) is True
    assert feature_approved("feat_002", root=root) is True
    plan_ts = read_doc("epic_001", root=root).meta.plan_approved_at
    events, _ = read_events("epic_001", 0, root=root)
    assert [event.type for event in events] == ["EpicPlanApproved"]

    second = approve_epic_plan("epic_001", root=root)
    assert second["features"] == ["feat_001", "feat_002"]
    assert read_doc("epic_001", root=root).meta.plan_approved_at == plan_ts
    events_again, _ = read_events("epic_001", 0, root=root)
    assert len(events_again) == 1


def test_child_added_after_epic_approval_stays_unapproved(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="One", tier="feature", parent="epic_001")
    approve_epic_plan_when_ready("epic_001", root=root)

    add_doc(root, id="feat_002", title="Later", tier="feature", parent="epic_001")

    assert feature_approved("feat_001", root=root) is True
    assert feature_approved("feat_002", root=root) is False


def test_epic_approval_commits_docs_in_their_owning_checkouts(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / ".gitignore").write_text(".cascade/\n", encoding="utf-8")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_root = integration_worktree_path("epic", "epic_001", trunk=root)
    trunk_before = _head(root)
    epic_before = _head(epic_root)

    approve_epic_plan_when_ready("epic_001", root=root)

    assert _head(root) != trunk_before
    assert _head(epic_root) != epic_before
    assert feature_approved("feat_001", root=root) is True
    assert epic_plan_approved("epic_001", root=root) is True
    assert _status(root, "docs/epics", "docs/features") == ""
    assert _status(epic_root, "docs/epics", "docs/features") == ""


def test_epic_approval_marks_plan_only_after_all_children_succeed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")

    def fail_child(feature_id: str, *, root: Path) -> bool:
        raise RuntimeError(f"could not approve {feature_id}")

    monkeypatch.setattr("cascade.approvals._set_feature_approved", fail_child)

    from tests.support import sign_off_both_planning_roles

    sign_off_both_planning_roles("epic_001", root=root)
    with pytest.raises(RuntimeError, match="could not approve feat_001"):
        approve_epic_plan("epic_001", root=root)

    assert epic_plan_approved("epic_001", root=root) is False


def _head(root: Path) -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _status(root: Path, *paths: str) -> str:
    return subprocess.run(
        ["git", "status", "--porcelain", "--", *paths],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def test_approve_feature_enables_dispatch_when_automation_off(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    refused = dispatch_feature("feat_001", "human", root=root)
    assert refused.reason == "not_approved"

    approve_feature("feat_001", root=root)
    started = dispatch_feature("feat_001", "human", root=root)
    assert started.ok is True


def test_approve_feature_api(tmp_path: Path) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    from cascade.war_room.server import serve

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/approve_feature",
            method="POST",
            data=json.dumps({"id": "feat_001"}).encode(),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            payload = json.loads(resp.read().decode())
        assert resp.status == HTTPStatus.OK
        assert payload["newly_approved"] is True
        assert feature_approved("feat_001", root=root) is True

        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/board") as resp:
            board = json.loads(resp.read().decode())
        feature = board["features"]["1_backlog"][0]
        assert feature["id"] == "feat_001"
        assert feature["approved"] is True
        assert "approved_at" in feature
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_apis_return_conflict_for_board_failures(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    from cascade.war_room.server import serve

    def fail_epic(*args: object, **kwargs: object) -> None:
        raise GitError("epic approval commit failed")

    def fail_feature(*args: object, **kwargs: object) -> None:
        raise BoardError("feature approval failed")

    monkeypatch.setattr("cascade.approvals.approve_epic_plan", fail_epic)
    monkeypatch.setattr("cascade.approvals.approve_feature", fail_feature)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cases = (
            ("approve_epic_plan", "epic_001", "epic approval commit failed"),
            ("approve_feature", "feat_001", "feature approval failed"),
        )
        for endpoint, work_id, message in cases:
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/{endpoint}",
                method="POST",
                data=json.dumps({"id": work_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                urllib.request.urlopen(req)
            assert exc_info.value.code == HTTPStatus.CONFLICT
            assert json.loads(exc_info.value.read().decode()) == {"error": message}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_approval_apis_can_finish_after_generic_request_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket
    import threading

    root = make_repo(tmp_path, git=False)
    from cascade.war_room.server import serve

    def slow_approval(*args: object, **kwargs: object) -> dict[str, bool]:
        time.sleep(0.1)
        return {"newly_approved": True}

    monkeypatch.setattr("cascade.approvals.approve_epic_plan", slow_approval)
    monkeypatch.setattr("cascade.approvals.approve_feature", slow_approval)
    monkeypatch.setattr("cascade.war_room.server.REQUEST_DEADLINE_S", 0.05)
    monkeypatch.setattr("cascade.war_room.server.APPROVAL_DEADLINE_S", 0.5)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    server = serve(root=root, host="127.0.0.1", port=port)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        for endpoint, work_id in (
            ("approve_epic_plan", "epic_001"),
            ("approve_feature", "feat_001"),
        ):
            req = urllib.request.Request(
                f"http://127.0.0.1:{port}/api/{endpoint}",
                method="POST",
                data=json.dumps({"id": work_id}).encode(),
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                payload = json.loads(resp.read().decode())
            assert resp.status == HTTPStatus.OK
            assert payload == {"newly_approved": True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
