"""Existing forge reviews are reused when an epic close is retried."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import cascade.tracking as tracking


def test_installed_github_cli_supports_snapshot_json_fields(tmp_path: Path) -> None:
    """Ask the real CLI to enumerate fields without contacting GitHub."""

    gh = shutil.which("gh")
    if gh is None:
        pytest.skip("gh is not installed; external installation is not part of this test")
    env = {
        **os.environ,
        "GH_CONFIG_DIR": str(tmp_path / "gh-config"),
        "GH_TOKEN": "local-contract-probe",
    }
    result = subprocess.run(
        [gh, "pr", "view", "--json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    fields = set(result.stderr.split())
    assert {
        "state", "isDraft", "comments", "reviews", "url", "headRefName",
        "baseRefName", "commits", "body", "mergeCommit", "mergeable",
        "mergeStateStatus",
    } <= fields
    assert "headRefOid" not in fields


def test_find_merge_request_reuses_matching_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracking, "detect_forge", lambda _root: "github")
    rows = [
        {"url": "https://github.example/pull/1", "number": 1, "baseRefName": "other", "isDraft": False, "state": "OPEN"},
        {"url": "https://github.example/pull/2", "number": 2, "baseRefName": "main", "isDraft": False, "state": "CLOSED"},
        {"url": "https://github.example/pull/merged", "number": 8, "baseRefName": "main", "isDraft": False, "state": "MERGED"},
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


def test_github_snapshot_uses_supported_query_and_last_commit_as_source_revision(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/7", number="7", forge="github",
        source_branch="epic/epic_001", target_branch="main", draft=False,
    )
    sha = "a" * 40
    source_sha = "b" * 40
    previous_sha = "c" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert root == tmp_path
        if args[:3] == ["gh", "pr", "view"]:
            assert args == [
                "gh", "pr", "view", mr.url, "--json",
                (
                    "state,isDraft,comments,reviews,url,headRefName,baseRefName,commits,body,"
                    "mergeCommit,mergeable,mergeStateStatus"
                ),
            ]
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "state": "MERGED", "isDraft": False,
                "url": mr.url, "headRefName": "epic/epic_001",
                "baseRefName": "main", "mergeCommit": {"oid": sha},
                "commits": [
                    {
                        "authoredDate": "2026-11-24T10:00:00Z", "authors": [],
                        "committedDate": "2026-11-24T10:00:00Z",
                        "messageBody": "", "messageHeadline": "First commit",
                        "oid": previous_sha,
                    },
                    {
                        "authoredDate": "2026-11-24T10:01:00Z", "authors": [],
                        "committedDate": "2026-11-24T10:01:00Z",
                        "messageBody": "", "messageHeadline": "PR head commit",
                        "oid": source_sha,
                    },
                ],
                "body": "Review description",
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                "comments": [{"id": "comment-1", "body": "Looks good"}],
                "reviews": [{"id": "review-1", "body": "Approved"}],
            }), "")
        return subprocess.CompletedProcess(args, 0, "[]", "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
    assert snapshot["state"] == "merged"
    assert snapshot["merge_sha"] == sha
    assert snapshot["mergeability"] == "mergeable"
    assert snapshot["description"] == "Review description"
    assert snapshot["source_revision"] == source_sha
    assert snapshot["source_branch"] == "epic/epic_001"
    assert [row["id"] for row in snapshot["comments"]] == ["comment-1", "review-1"]


@pytest.mark.parametrize(
    "commits",
    [None, [], {}, ["not-an-object"], [{}], [{"oid": ""}], [{"oid": 7}]],
)
def test_github_snapshot_refuses_missing_or_malformed_commits(
    tmp_path: Path, commits: object,
) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/9", number="9", forge="github",
        source_branch="feat/feat_001", target_branch="epic/epic_001", draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "state": "OPEN", "isDraft": False, "url": mr.url,
                "headRefName": mr.source_branch, "baseRefName": mr.target_branch,
                "commits": commits, "body": "", "mergeCommit": None,
                "mergeable": "MERGEABLE", "mergeStateStatus": "CLEAN",
                "comments": [], "reviews": [],
            }), "")
        return subprocess.CompletedProcess(args, 0, "[]", "")

    with pytest.raises(tracking.GitError, match="invalid GitHub commits JSON"):
        tracking.merge_request_snapshot(tmp_path, mr, runner=runner)


def test_review_snapshot_exposes_conflicting_mergeability(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/8", number="8", forge="github",
        source_branch="epic/epic_038", target_branch="main", draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(args, 0, json.dumps({
                "state": "OPEN", "headRefName": "epic/epic_038",
                "baseRefName": "main", "mergeCommit": None,
                "mergeable": "CONFLICTING", "mergeStateStatus": "DIRTY",
                "commits": [{"oid": "d" * 40}],
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


def test_gitlab_snapshot_normalization_is_unchanged(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://gitlab.example/group/project/-/merge_requests/4",
        number="4", forge="gitlab", source_branch="feat/feat_001",
        target_branch="epic/epic_001", draft=False,
    )
    source_sha = "e" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert args == ["glab", "mr", "view", mr.url, "--output", "json"]
        return subprocess.CompletedProcess(args, 0, json.dumps({
            "state": "opened", "web_url": mr.url,
            "source_branch": mr.source_branch, "target_branch": mr.target_branch,
            "sha": source_sha, "merge_commit_sha": "f" * 40,
            "merge_status": "can_be_merged", "detailed_merge_status": "mergeable",
            "description": "GitLab review", "notes": [{"id": 3}],
        }), "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)

    assert snapshot == {
        "state": "opened", "comments": [{"id": 3}], "url": mr.url,
        "mergeability": "mergeable", "merge_sha": "f" * 40,
        "description": "GitLab review", "source_revision": source_sha,
        "target_branch": mr.target_branch, "source_branch": mr.source_branch,
    }
