"""Existing forge reviews are reused when an epic close is retried."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import cascade.tracking as tracking


def test_find_merge_request_reuses_matching_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracking, "detect_forge", lambda _root: "github")
    rows = [
        {"url": "https://github.example/pull/1", "number": 1, "baseRefName": "other", "isDraft": False, "state": "OPEN"},
        {"url": "https://github.example/pull/2", "number": 2, "baseRefName": "main", "isDraft": False, "state": "CLOSED"},
        {"url": "https://github.example/pull/3", "number": 3, "baseRefName": "main", "isDraft": True, "state": "OPEN"},
    ]

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert root == tmp_path
        assert args[:6] == ["gh", "pr", "list", "--state", "all", "--head"]
        return subprocess.CompletedProcess(args, 0, json.dumps(rows), "")

    mr = tracking.find_merge_request(
        tmp_path, source_branch="epic/epic_001", target_branch="main", runner=runner
    )
    assert mr is not None
    assert mr.url == "https://github.example/pull/3"
    assert mr.number == "3"
    assert mr.draft is True


def test_merged_review_snapshot_exposes_immutable_merge_commit(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/7", number="7", forge="github",
        source_branch="epic/epic_001", target_branch="main", draft=False,
    )
    sha = "a" * 40
    source_sha = "b" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert root == tmp_path
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "state": "MERGED", "baseRefName": "main", "mergeCommit": {"oid": sha},
                "headRefOid": source_sha, "body": "Review description",
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                "comments": [], "reviews": [],
            }), "")
        return subprocess.CompletedProcess(args, 0, "[]", "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
    assert snapshot["state"] == "merged"
    assert snapshot["merge_sha"] == sha
    assert snapshot["mergeability"] == "mergeable"
    assert snapshot["description"] == "Review description"
    assert snapshot["source_revision"] == source_sha


def test_review_snapshot_exposes_conflicting_mergeability(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/8", number="8", forge="github",
        source_branch="epic/epic_038", target_branch="main", draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "state": "OPEN", "baseRefName": "main", "mergeCommit": None,
                "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY",
                "comments": [], "reviews": [],
            }), "")
        return subprocess.CompletedProcess(args, 0, "[]", "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
    assert snapshot["state"] == "open"
    assert snapshot["mergeability"] == "conflicting"


def test_review_snapshot_distinguishes_missing_review(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/404", number="404", forge="github",
        source_branch="epic/epic_001", target_branch="main", draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "HTTP 404: Not Found")

    with pytest.raises(tracking.ReviewNotFound):
        tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
