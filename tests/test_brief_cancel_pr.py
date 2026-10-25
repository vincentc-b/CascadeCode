"""Backlog brief actions use the approved remote document and review path."""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from cascade.board.parse import parse_text, render_doc
from cascade.brief_cancel_pr import submit_brief_cancel
from cascade.brief_edit_pr import BriefEditError, get_editable_brief
from cascade.tracking import MergeRequest
from cascade.workspace.backlog_snapshot import is_snapshot_only_epic, refresh_remote_backlog_snapshot
from cascade.workspace.integration_worktree import merged_board
from tests.test_backlog_snapshot import _enable_automation, _push_remote_brief, _seed_remote
from tests.support import make_repo
from tests.war_room.test_brief_defaults_api import _post, _post_expect_error
from tests.war_room.test_http_read import war_room_server


def _local_with_remote_brief(tmp_path: Path) -> tuple[Path, Path]:
    upstream, remote = _seed_remote(tmp_path)
    _push_remote_brief(upstream, "epic_024", "Original")
    root = make_repo(tmp_path / "local")
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    _enable_automation(root)
    (root / "operator.txt").write_text("preserve me\n", encoding="utf-8")
    subprocess.run(["git", "add", "operator.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local operator work"], cwd=root, check=True, capture_output=True)
    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    return root, upstream


def test_snapshot_brief_loads_approved_remote_path_and_revision(tmp_path: Path) -> None:
    root, upstream = _local_with_remote_brief(tmp_path)
    payload = get_editable_brief(root, "/api/brief/edit?epic_id=epic_024")
    assert payload["source_path"] == "docs/epics/1_backlog/epic_024_original.md"
    assert payload["source_revision"] == subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", payload["source_path"]],
        cwd=upstream, check=True, capture_output=True, text=True,
    ).stdout.strip()
    assert payload["title"] == "Original"


def test_cancel_creates_review_commit_without_changing_operator_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, _ = _local_with_remote_brief(tmp_path)
    payload = get_editable_brief(root, "/api/brief/edit?epic_id=epic_024")
    head_before = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()
    monkeypatch.setattr("cascade.brief_cancel_pr.forge_ready", lambda _root: True)
    monkeypatch.setattr("cascade.brief_cancel_pr.push_branch", lambda *_args, **_kwargs: None)

    def fake_review(_worktree, *, source_branch, target_branch, **_kwargs):
        return MergeRequest(
            url="https://example.test/review/1", number="1", forge="github",
            source_branch=source_branch, target_branch=target_branch, draft=False,
        )

    monkeypatch.setattr("cascade.brief_cancel_pr.create_merge_request", fake_review)
    review = submit_brief_cancel(root, {**payload, "reason": "No longer needed"})
    old_path = str(payload["source_path"])
    new_path = old_path.replace("/1_backlog/", "/3_completed/")
    shown = subprocess.run(
        ["git", "show", f"{review.source_branch}:{new_path}"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout
    cancelled = parse_text(shown, root / new_path)
    assert cancelled.meta.status == "cancelled"
    assert cancelled.meta.cancellation_reason == "No longer needed"
    assert cancelled.meta.cancelled_at is not None
    assert subprocess.run(
        ["git", "cat-file", "-e", f"{review.source_branch}:{old_path}"],
        cwd=root, capture_output=True,
    ).returncode != 0
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip() == head_before
    assert (root / "operator.txt").read_text(encoding="utf-8") == "preserve me\n"


def test_cancel_rejects_stale_revision_before_branch_creation(tmp_path: Path) -> None:
    root, upstream = _local_with_remote_brief(tmp_path)
    payload = get_editable_brief(root, "/api/brief/edit?epic_id=epic_024")
    source = upstream / str(payload["source_path"])
    source.write_text(source.read_text(encoding="utf-8").replace("Why this exists.", "Changed."), encoding="utf-8")
    subprocess.run(["git", "add", str(payload["source_path"])], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "change brief"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=upstream, check=True, capture_output=True)
    with pytest.raises(BriefEditError) as raised:
        submit_brief_cancel(root, {**payload, "reason": "No longer needed"})
    assert raised.value.code == "stale"
    assert raised.value.reload is True


def test_cancel_route_returns_review_url_and_rejects_blank_reason(
    war_room_server, monkeypatch: pytest.MonkeyPatch
) -> None:
    base, _root, _server = war_room_server
    status, error = _post_expect_error(
        f"{base}/api/brief/cancel", {"epic_id": "epic_024", "reason": " "}
    )
    assert status == 400
    assert error["code"] == "reason_required"

    review = MergeRequest(
        url="https://example.test/review/2", number="2", forge="github",
        source_branch="cascade/brief-cancel/epic_024", target_branch="main", draft=False,
    )
    monkeypatch.setattr("cascade.war_room.brief_edit_routes.submit_brief_cancel", lambda *_args: review)
    status, body = _post(
        f"{base}/api/brief/cancel", {"epic_id": "epic_024", "reason": "No longer needed"}
    )
    assert status == 201
    assert body["merge_request_url"] == review.url


def test_approved_cancellation_hides_stale_local_backlog_copy(tmp_path: Path) -> None:
    root, upstream = _local_with_remote_brief(tmp_path)
    source_path = Path("docs/epics/1_backlog/epic_024_original.md")
    local = root / source_path
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text((upstream / source_path).read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "add", str(source_path)], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local backlog copy"], cwd=root, check=True, capture_output=True)

    approved = parse_text((upstream / source_path).read_text(encoding="utf-8"), upstream / source_path)
    approved.meta.status = "cancelled"
    approved.meta.cancellation_reason = "No longer needed"
    approved.meta.cancelled_at = datetime.now(timezone.utc)
    approved.meta.cancellation_step = "complete"
    target_path = Path("docs/epics/3_completed") / source_path.name
    approved.meta.path = upstream / target_path
    approved.meta.path.parent.mkdir(parents=True, exist_ok=True)
    approved.meta.path.write_text(render_doc(approved), encoding="utf-8")
    (upstream / source_path).unlink()
    subprocess.run(["git", "add", "-A", "docs/epics"], cwd=upstream, check=True)
    subprocess.run(["git", "commit", "-m", "approve cancellation"], cwd=upstream, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=upstream, check=True, capture_output=True)

    refresh_remote_backlog_snapshot(root, remote="origin", trunk_branch="main")
    meta = merged_board(root).by_id["epic_024"]
    assert meta.status == "cancelled"
    assert meta.path.parent.name == "3_completed"
    assert local.is_file()  # The operator checkout was preserved.
    assert not is_snapshot_only_epic("epic_024", trunk=root)
