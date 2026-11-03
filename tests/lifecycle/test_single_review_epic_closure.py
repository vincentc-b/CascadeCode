"""Lifecycle proof for closing an epic through its implementation review."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.store import read_doc_in_worktree
from cascade.boss.epic_complete import confirm_epic_complete_result
from cascade.review import ensure_epic_review
from cascade.tracking import MergeRequest
from cascade.watchdog import activate_epic
from cascade.watchdog.events import read_events
from cascade.workspace.integration_worktree import integration_worktree_path, merged_board
from tests.support import add_doc, commit_board, make_repo


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=repo, check=check, capture_output=True, text=True
    )


def test_epic_closes_through_one_idempotent_implementation_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path / "operator")
    (root / "README.md").write_text("board\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_worktree = integration_worktree_path("epic", "epic_001", trunk=root)

    remote = tmp_path / "remote.git"
    _git(tmp_path, "init", "--bare", str(remote))
    _git(root, "remote", "add", "origin", str(remote))
    _git(root, "push", "origin", "main", "epic/epic_001")

    review = MergeRequest(
        url="https://github.example/pull/1",
        number="1",
        forge="github",
        source_branch="epic/epic_001",
        target_branch="main",
        draft=False,
    )
    created_reviews: list[MergeRequest] = []

    def find_review(*_args, **_kwargs):
        return created_reviews[0] if created_reviews else None

    def create_review(*_args, **_kwargs):
        created_reviews.append(review)
        return review

    monkeypatch.setattr("cascade.review.find_merge_request", find_review)
    monkeypatch.setattr("cascade.review.create_merge_request", create_review)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.boss.epic_close_review.ensure_epic_close_review",
        lambda *_args, **_kwargs: pytest.fail("must not open a terminal-only review"),
    )

    operator_before = {
        "head": _git(root, "rev-parse", "HEAD").stdout,
        "branch": _git(root, "branch", "--show-current").stdout,
        "index": _git(root, "ls-files", "--stage", "-z").stdout,
        "status": _git(root, "status", "--porcelain").stdout,
    }

    # Preparation is convergent: completion is staged before review creation,
    # and a retry finds the same implementation review.
    assert ensure_epic_review("epic_001", root=root) == review
    assert ensure_epic_review("epic_001", root=root) == review
    prepared = read_doc_in_worktree("epic_001", epic_worktree)
    assert prepared.meta.status == "completed"
    assert prepared.meta.path.parent.name == "3_completed"
    assert created_reviews == [review]

    snapshot = {"state": "open", "merge_sha": None}
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot", lambda *_args, **_kwargs: snapshot
    )
    pending = confirm_epic_complete_result("epic_001", "human", root=root)
    assert not pending.ok and pending.reason == "pending_epic_review"

    implementation_tip = _git(root, "rev-parse", "epic/epic_001").stdout.strip()
    snapshot.update(state="merged", merge_sha=implementation_tip)
    not_landed = confirm_epic_complete_result("epic_001", "human", root=root)
    assert not not_landed.ok and not_landed.reason == "pending_epic_review"

    reviewer = tmp_path / "reviewer"
    _git(tmp_path, "clone", str(remote), str(reviewer))
    _git(reviewer, "checkout", "-B", "main", "origin/main")
    merge = _git(
        reviewer,
        "merge",
        "--no-ff",
        "--no-edit",
        "origin/epic/epic_001",
        check=False,
    )
    assert merge.returncode != 0
    active_path = "docs/epics/2_active/epic_001_epic.md"
    completed_path = "docs/epics/3_completed/epic_001_epic.md"
    # First land the review while retaining the active trunk document. Forge
    # state and ancestry alone must not finalize closure.
    _git(reviewer, "checkout", "--ours", "--", active_path)
    _git(reviewer, "rm", "--", completed_path)
    _git(reviewer, "add", "--", active_path)
    _git(reviewer, "-c", "commit.gpgsign=false", "commit", "--no-edit")
    merge_sha = _git(reviewer, "rev-parse", "HEAD").stdout.strip()
    snapshot["merge_sha"] = merge_sha
    _git(reviewer, "push", "origin", "main")
    missing_completion = confirm_epic_complete_result("epic_001", "human", root=root)
    assert not missing_completion.ok and missing_completion.reason == "pending_epic_review"

    # Reconcile once remote trunk contains the reviewed completed document.
    _git(reviewer, "rm", "--", active_path)
    _git(reviewer, "checkout", "origin/epic/epic_001", "--", completed_path)
    _git(reviewer, "commit", "-m", "complete epic", "--", active_path, completed_path)
    _git(reviewer, "push", "origin", "main")
    assert confirm_epic_complete_result("epic_001", "human", root=root).ok
    assert confirm_epic_complete_result("epic_001", "human", root=root).ok

    assert merged_board(root).by_id["epic_001"].status == "completed"
    events, _ = read_events("war_room", 0, root=root)
    assert len([event for event in events if event.type == "EpicCompleted"]) == 1
    assert created_reviews == [review]
    operator_after = {
        "head": _git(root, "rev-parse", "HEAD").stdout,
        "branch": _git(root, "branch", "--show-current").stdout,
        "index": _git(root, "ls-files", "--stage", "-z").stdout,
        "status": _git(root, "status", "--porcelain").stdout,
    }
    assert operator_after == operator_before
