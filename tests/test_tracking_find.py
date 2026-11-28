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
        pytest.skip(
            "gh is not installed; external installation is not part of this test"
        )
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
        "state",
        "isDraft",
        "comments",
        "reviews",
        "url",
        "headRefName",
        "baseRefName",
        "commits",
        "body",
        "mergeCommit",
        "mergeable",
        "mergeStateStatus",
        "reviewDecision",
    } <= fields
    assert "headRefOid" not in fields


def test_find_merge_request_reuses_matching_open_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(tracking, "detect_forge", lambda _root: "github")
    rows = [
        {
            "url": "https://github.example/pull/1",
            "number": 1,
            "baseRefName": "other",
            "isDraft": False,
            "state": "OPEN",
        },
        {
            "url": "https://github.example/pull/2",
            "number": 2,
            "baseRefName": "main",
            "isDraft": False,
            "state": "CLOSED",
        },
        {
            "url": "https://github.example/pull/merged",
            "number": 8,
            "baseRefName": "main",
            "isDraft": False,
            "state": "MERGED",
        },
        {
            "url": "https://github.example/pull/3",
            "number": 3,
            "baseRefName": "main",
            "isDraft": True,
            "state": "OPEN",
        },
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
        url="https://github.com/example/project/pull/7",
        number="7",
        forge="github",
        source_branch="epic/epic_001",
        target_branch="main",
        draft=False,
    )
    sha = "a" * 40
    source_sha = "b" * 40
    previous_sha = "c" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        assert root == tmp_path
        if args[:3] == ["gh", "pr", "view"]:
            assert args == [
                "gh",
                "pr",
                "view",
                mr.url,
                "--json",
                (
                    "state,isDraft,comments,reviews,url,headRefName,baseRefName,commits,body,"
                    "mergeCommit,mergeable,mergeStateStatus"
                    ",reviewDecision"
                ),
            ]
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "state": "MERGED",
                        "isDraft": False,
                        "url": mr.url,
                        "headRefName": "epic/epic_001",
                        "baseRefName": "main",
                        "mergeCommit": {"oid": sha},
                        "commits": [
                            {
                                "authoredDate": "2026-11-24T10:00:00Z",
                                "authors": [],
                                "committedDate": "2026-11-24T10:00:00Z",
                                "messageBody": "",
                                "messageHeadline": "First commit",
                                "oid": previous_sha,
                            },
                            {
                                "authoredDate": "2026-11-24T10:01:00Z",
                                "authors": [],
                                "committedDate": "2026-11-24T10:01:00Z",
                                "messageBody": "",
                                "messageHeadline": "PR head commit",
                                "oid": source_sha,
                            },
                        ],
                        "body": "Review description",
                        "mergeable": "MERGEABLE",
                        "mergeStateStatus": "CLEAN",
                        "comments": [{"id": "comment-1", "body": "Looks good"}],
                        "reviews": [{"id": "review-1", "body": "Approved"}],
                    }
                ),
                "",
            )
        if args[-1] == "repos/example/project/branches/main":
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"commit": {"sha": "d" * 40}}), ""
            )
        if args[-1].endswith("/protection/required_status_checks"):
            return subprocess.CompletedProcess(args, 1, "", "Branch is not protected")
        if args[-1].endswith("/check-runs"):
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"check_runs": []}), ""
            )
        if args[-1].endswith("/status"):
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"statuses": []}), ""
            )
        return subprocess.CompletedProcess(args, 0, "[]", "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
    assert snapshot["state"] == "merged"
    assert snapshot["merge_sha"] == sha
    assert snapshot["mergeability"] == "mergeable"
    assert snapshot["description"] == "Review description"
    assert snapshot["source_revision"] == source_sha
    assert snapshot["source_branch"] == "epic/epic_001"
    assert snapshot["target_revision"] == "d" * 40
    assert snapshot["accepted_merge_identity"] == {
        "available": True,
        "review_url": mr.url,
        "source_branch": mr.source_branch,
        "target_branch": mr.target_branch,
        "source_revision": source_sha,
        "merge_sha": sha,
        "observed_target_head": "d" * 40,
    }
    assert snapshot["required_check_policy"]["confirmed_empty"] is True
    assert snapshot["review_identity"]["url"] == mr.url
    assert [row["id"] for row in snapshot["comments"]] == ["comment-1", "review-1"]


@pytest.mark.parametrize(
    "commits",
    [None, [], {}, ["not-an-object"], [{}], [{"oid": ""}], [{"oid": 7}]],
)
def test_github_snapshot_refuses_missing_or_malformed_commits(
    tmp_path: Path,
    commits: object,
) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/9",
        number="9",
        forge="github",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "state": "OPEN",
                        "isDraft": False,
                        "url": mr.url,
                        "headRefName": mr.source_branch,
                        "baseRefName": mr.target_branch,
                        "commits": commits,
                        "body": "",
                        "mergeCommit": None,
                        "mergeable": "MERGEABLE",
                        "mergeStateStatus": "CLEAN",
                        "comments": [],
                        "reviews": [],
                    }
                ),
                "",
            )
        return subprocess.CompletedProcess(args, 0, "[]", "")

    with pytest.raises(tracking.GitError, match="invalid GitHub commits JSON"):
        tracking.merge_request_snapshot(tmp_path, mr, runner=runner)


def test_review_snapshot_exposes_conflicting_mergeability(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/8",
        number="8",
        forge="github",
        source_branch="epic/epic_038",
        target_branch="main",
        draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "state": "OPEN",
                        "headRefName": "epic/epic_038",
                        "baseRefName": "main",
                        "mergeCommit": None,
                        "mergeable": "CONFLICTING",
                        "mergeStateStatus": "DIRTY",
                        "commits": [{"oid": "d" * 40}],
                        "comments": [],
                        "reviews": [],
                    }
                ),
                "",
            )
        return subprocess.CompletedProcess(args, 0, "[]", "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)
    assert snapshot["state"] == "open"
    assert snapshot["mergeability"] == "conflicting"


def test_merged_snapshot_marks_missing_actual_merge_sha_unavailable(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/18",
        number="18",
        forge="github",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "state": "MERGED",
                        "url": mr.url,
                        "headRefName": mr.source_branch,
                        "baseRefName": mr.target_branch,
                        "mergeCommit": None,
                        "commits": [{"oid": "a" * 40}],
                        "mergeable": "UNKNOWN",
                        "mergeStateStatus": "UNKNOWN",
                        "comments": [],
                        "reviews": [],
                    }
                ),
                "",
            )
        endpoint = args[-1]
        if endpoint.endswith(f"/branches/{mr.target_branch}"):
            return subprocess.CompletedProcess(
                args, 0, json.dumps({"commit": {"sha": "b" * 40}}), ""
            )
        return subprocess.CompletedProcess(args, 1, "", "unavailable")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)

    assert snapshot["accepted_merge_identity"] == {
        "available": False,
        "reason": "accepted_merge_sha_unavailable",
    }


def test_review_snapshot_distinguishes_missing_review(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        url="https://github.com/example/project/pull/404",
        number="404",
        forge="github",
        source_branch="epic/epic_001",
        target_branch="main",
        draft=False,
    )

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 1, "", "HTTP 404: Not Found")

    with pytest.raises(tracking.ReviewNotFound):
        tracking.merge_request_snapshot(tmp_path, mr, runner=runner)


def test_gitlab_snapshot_preserves_existing_fields_and_adds_evidence(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        url="https://gitlab.example/group/project/-/merge_requests/4",
        number="4",
        forge="gitlab",
        source_branch="feat/feat_001",
        target_branch="epic/epic_001",
        draft=False,
    )
    source_sha = "e" * 40
    target_sha = "d" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["glab", "mr", "view"]:
            return subprocess.CompletedProcess(
                args,
                0,
                json.dumps(
                    {
                        "state": "opened",
                        "web_url": mr.url,
                        "source_branch": mr.source_branch,
                        "target_branch": mr.target_branch,
                        "sha": source_sha,
                        "merge_commit_sha": "f" * 40,
                        "merge_status": "can_be_merged",
                        "detailed_merge_status": "mergeable",
                        "description": "GitLab review",
                        "notes": [{"id": 3}],
                    }
                ),
                "",
            )
        endpoint = args[-1]
        if "/repository/branches/" in endpoint:
            payload = {"commit": {"sha": target_sha}}
        elif endpoint == "projects/group%2Fproject":
            payload = {"only_allow_merge_if_pipeline_succeeds": False}
        elif endpoint.endswith("/pipelines"):
            payload = []
        elif endpoint.endswith("/approval_state"):
            payload = {"rules": []}
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)

    assert snapshot["state"] == "opened"
    assert snapshot["comments"] == [{"id": 3}]
    assert snapshot["merge_sha"] == "f" * 40
    assert snapshot["source_revision"] == source_sha
    assert snapshot["target_revision"] == target_sha
    assert snapshot["required_check_policy"]["required"] == []
    assert snapshot["required_check_policy"]["confirmed_empty"] is True
    assert snapshot["review_health"]["state"] == "green"


def _github_evidence_runner(
    mr: tracking.MergeRequest,
    *,
    policy: object,
    checks: list[dict[str, object]],
    statuses: list[dict[str, object]] | None = None,
    target_sha: str = "t" * 40,
    policy_error: str | None = None,
    review_decision: str = "APPROVED",
    reviews: list[dict[str, object]] | None = None,
):
    source_sha = "s" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["gh", "pr", "view"]:
            payload = {
                "state": "OPEN",
                "url": mr.url,
                "headRefName": mr.source_branch,
                "baseRefName": mr.target_branch,
                "commits": [{"oid": source_sha}],
                "mergeable": "MERGEABLE",
                "mergeStateStatus": "CLEAN",
                "comments": [],
                "reviews": reviews or [],
                "reviewDecision": review_decision,
            }
            return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")
        endpoint = args[-1]
        if endpoint.endswith("/comments"):
            payload = []
        elif endpoint.endswith(f"/branches/{mr.target_branch}"):
            payload = {"commit": {"sha": target_sha}}
        elif endpoint.endswith("/protection/required_status_checks"):
            if policy_error:
                return subprocess.CompletedProcess(args, 1, "", policy_error)
            payload = policy
        elif endpoint.endswith("/check-runs"):
            payload = {"check_runs": checks}
        elif endpoint.endswith("/status"):
            payload = {"statuses": statuses or []}
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    return runner


def test_github_zero_listed_checks_does_not_invent_empty_policy(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        "https://github.com/example/project/pull/10",
        "10",
        "github",
        "feat/x",
        "main",
        False,
    )
    snapshot = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(
            mr, policy={}, checks=[], policy_error="service unavailable"
        ),
    )

    assert snapshot["required_check_policy"]["available"] is False
    assert snapshot["required_check_results"]["available"] is True
    assert snapshot["review_health"] == {
        "state": "transient_outage",
        "reason": "required_check_policy_unavailable",
    }


def test_github_required_result_is_missing_and_stale_heads_are_distinct(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        "https://github.com/example/project/pull/11",
        "11",
        "github",
        "feat/x",
        "main",
        False,
    )
    missing = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(mr, policy={"contexts": ["tests"]}, checks=[]),
    )
    stale = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(
            mr,
            policy={"contexts": ["tests"]},
            checks=[
                {"id": 2, "name": "tests", "head_sha": "old", "conclusion": "success"}
            ],
        ),
    )

    assert missing["review_health"] == {"state": "missing", "checks": ["tests"]}
    assert stale["required_check_results"]["checks"]["tests"]["source_head"] == "old"
    assert stale["review_health"] == {
        "state": "conflict_or_moving_target",
        "reason": "stale_check_generation",
    }


def test_github_newer_failed_check_generation_wins_over_old_green(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        "https://github.com/example/project/pull/12",
        "12",
        "github",
        "feat/x",
        "main",
        False,
    )
    snapshot = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(
            mr,
            policy={"checks": [{"context": "tests"}]},
            checks=[
                {
                    "id": 1,
                    "name": "tests",
                    "head_sha": "s" * 40,
                    "conclusion": "success",
                    "completed_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": 2,
                    "name": "tests",
                    "head_sha": "s" * 40,
                    "conclusion": "failure",
                    "completed_at": "2026-01-02T00:00:00Z",
                },
            ],
        ),
    )

    assert snapshot["required_check_results"]["checks"]["tests"]["generation"] == 2
    assert snapshot["review_health"] == {"state": "failed", "checks": ["tests"]}


def test_github_feedback_distinguishes_approval_wait_and_actionable_change(
    tmp_path: Path,
) -> None:
    mr = tracking.MergeRequest(
        "https://github.com/example/project/pull/13",
        "13",
        "github",
        "feat/x",
        "main",
        False,
    )
    waiting = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(
            mr, policy={"contexts": []}, checks=[], review_decision="REVIEW_REQUIRED"
        ),
    )
    actionable = tracking.merge_request_snapshot(
        tmp_path,
        mr,
        runner=_github_evidence_runner(
            mr,
            policy={"contexts": []},
            checks=[],
            review_decision="CHANGES_REQUESTED",
            reviews=[
                {
                    "id": "review-2",
                    "author": {"login": "reviewer"},
                    "state": "CHANGES_REQUESTED",
                }
            ],
        ),
    )

    assert waiting["review_health"] == {
        "state": "approval_only_wait",
        "reason": "approval_pending",
    }
    assert actionable["review_health"] == {
        "state": "actionable_human_feedback",
        "reason": "changes_requested",
    }
    assert actionable["review_feedback"]["actionable_feedback"] == [
        {"id": "review-2", "reviewer": "reviewer", "submitted_at": None}
    ]


def test_gitlab_latest_pipeline_generation_and_approval_wait(tmp_path: Path) -> None:
    mr = tracking.MergeRequest(
        "https://gitlab.example/group/project/-/merge_requests/5",
        "5",
        "gitlab",
        "feat/x",
        "main",
        False,
    )
    source_sha = "s" * 40

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args[:3] == ["glab", "mr", "view"]:
            payload = {
                "state": "opened",
                "web_url": mr.url,
                "source_branch": mr.source_branch,
                "target_branch": mr.target_branch,
                "sha": source_sha,
                "merge_status": "can_be_merged",
                "notes": [],
            }
        elif "/repository/branches/" in args[-1]:
            payload = {"commit": {"sha": "t" * 40}}
        elif args[-1] == "projects/group%2Fproject":
            payload = {"only_allow_merge_if_pipeline_succeeds": True}
        elif args[-1].endswith("/pipelines"):
            payload = [
                {
                    "id": 9,
                    "sha": source_sha,
                    "status": "success",
                    "updated_at": "2026-01-01T00:00:00Z",
                },
                {
                    "id": 10,
                    "sha": source_sha,
                    "status": "failed",
                    "updated_at": "2026-01-02T00:00:00Z",
                },
            ]
        elif args[-1].endswith("/pipelines/10/jobs"):
            payload = [{"id": 100, "name": "tests", "status": "failed"}]
        elif args[-1].endswith("/approval_state"):
            payload = {"rules": [{"name": "maintainers", "approved": False}]}
        else:
            raise AssertionError(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(payload), "")

    snapshot = tracking.merge_request_snapshot(tmp_path, mr, runner=runner)

    assert snapshot["required_check_results"]["checks"]["pipeline"]["generation"] == 10
    assert snapshot["required_check_results"]["checks"]["tests"]["generation"] == {
        "pipeline_id": 10,
        "job_id": 100,
    }
    assert snapshot["review_health"] == {"state": "failed", "checks": ["pipeline"]}
