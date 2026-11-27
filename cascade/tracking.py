"""GitHub/GitLab integration used by briefs and feature review.

The integration deliberately shells out to the authenticated ``gh`` or ``glab``
CLI.  Cascade never stores a second forge token and the command boundary is easy
to replace in tests.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal
from urllib.parse import quote

from cascade.board.errors import GitError

Forge = Literal["github", "gitlab"]
Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


class ReviewNotFound(GitError):
    """The forge confirmed that a requested review no longer exists."""


@dataclass(frozen=True)
class MergeRequest:
    url: str
    number: str | None
    forge: Forge
    source_branch: str
    target_branch: str
    draft: bool


def _command(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=root, capture_output=True, text=True, encoding="utf-8"
    )


def _git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return _command(["git", *args], root)


def remote_url(root: Path, remote: str = "origin") -> str | None:
    result = _git(["remote", "get-url", remote], root)
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def detect_forge(root: Path, remote: str = "origin") -> Forge | None:
    url = (remote_url(root, remote) or "").lower()
    if "github.com" in url:
        return "github"
    if "gitlab" in url:
        return "gitlab"
    return None


def _strip_git_suffix(name: str) -> str:
    return name[:-4] if name.endswith(".git") else name


def remote_repo_web_base(url: str, *, forge: Forge) -> str | None:
    """Normalize an origin remote URL to a forge web repo root."""

    raw = url.strip()
    if forge == "github":
        match = re.match(r"git@github\.com:(?P<owner>[^/]+)/(?P<repo>.+)$", raw)
        if match:
            repo = _strip_git_suffix(match.group("repo"))
            return f"https://github.com/{match.group('owner')}/{repo}"
        match = re.match(r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)", raw)
        if match:
            repo = _strip_git_suffix(match.group("repo"))
            return f"https://github.com/{match.group('owner')}/{repo}"
        return None

    match = re.match(r"git@(?P<host>[^:]+):(?P<path>.+)$", raw)
    if match:
        path = _strip_git_suffix(match.group("path"))
        return f"https://{match.group('host')}/{path}"
    match = re.match(r"https?://(?P<host>[^/]+)/(?P<path>.+)$", raw)
    if match:
        path = _strip_git_suffix(match.group("path").rstrip("/"))
        return f"https://{match.group('host')}/{path}"
    return None


def completed_epics_history_url(
    root: Path,
    *,
    remote: str = "origin",
    rel_path: str = "docs/epics/3_completed",
) -> str | None:
    """Web URL for browsing all completed epic documents, when origin metadata allows."""

    from cascade.board.gitutil import has_git
    from cascade.workspace.errors import WorkspaceError
    from cascade.workspace.trunk import resolve_product_trunk

    if not has_git(root):
        return None
    raw_url = remote_url(root, remote)
    if not raw_url:
        return None
    forge = detect_forge(root, remote)
    if forge is None:
        return None
    base = remote_repo_web_base(raw_url, forge=forge)
    if base is None:
        return None
    try:
        branch = resolve_product_trunk(root)
    except WorkspaceError:
        return None
    if forge == "github":
        return f"{base}/tree/{branch}/{rel_path}"
    return f"{base}/-/tree/{branch}/{rel_path}"


def forge_ready(root: Path, remote: str = "origin") -> bool:
    forge = detect_forge(root, remote)
    command = "gh" if forge == "github" else "glab" if forge == "gitlab" else None
    return command is not None and shutil.which(command) is not None


def push_branch(
    root: Path,
    branch: str,
    *,
    remote: str = "origin",
    force_with_lease: str | None = None,
) -> None:
    args = ["push", "-u"]
    if force_with_lease is not None:
        args.append(f"--force-with-lease=refs/heads/{branch}:{force_with_lease}")
    result = _git([*args, remote, branch], root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GitError(detail or f"could not push {branch}")


def fast_forward_branch(
    root: Path,
    branch: str,
    *,
    remote: str = "origin",
) -> str:
    """Sync an accepted review while preserving clean local target history.

    Epic Teams may commit planning decisions after a Feature review opens.  A
    human can then merge that review before those target-side commits have been
    published, leaving the durable Epic checkout both ahead of and behind its
    remote.  Preserve both sides with a normal merge when Git can do so without
    conflicts.  Dirty worktrees and semantic conflicts remain fail-closed.
    """

    current = _git(["branch", "--show-current"], root).stdout.strip()
    if current != branch:
        raise GitError(f"integration worktree must be on {branch!r}, not {current!r}")
    fetch = _git(["fetch", remote, branch], root)
    if fetch.returncode != 0:
        raise GitError(
            (fetch.stderr or fetch.stdout).strip() or f"could not fetch {branch}"
        )
    remote_ref = f"{remote}/{branch}"
    clean = _git(["status", "--porcelain", "--untracked-files=all"], root)
    if clean.returncode != 0 or clean.stdout.strip():
        raise GitError(
            f"cannot synchronize {branch}: integration worktree has local changes"
        )
    merge = _git(["merge", "--ff-only", remote_ref], root)
    if merge.returncode != 0:
        local_head = _git(["rev-parse", "HEAD"], root).stdout.strip()
        remote_head = _git(["rev-parse", remote_ref], root).stdout.strip()
        base = _git(["merge-base", local_head, remote_head], root)
        if (
            not local_head
            or not remote_head
            or base.returncode != 0
            or not base.stdout.strip()
        ):
            raise GitError(
                f"could not find shared history while synchronizing {branch}"
            )
        recovered = _git(
            ["-c", "commit.gpgsign=false", "merge", "--no-edit", remote_ref], root
        )
        if recovered.returncode != 0:
            detail = (recovered.stderr or recovered.stdout).strip()
            aborted = _git(["merge", "--abort"], root)
            restored = _git(["rev-parse", "HEAD"], root).stdout.strip()
            if aborted.returncode != 0 or restored != local_head:
                raise GitError(f"could not safely abort divergent merge for {branch}")
            raise GitError(
                detail or f"could not reconcile divergent local commits on {branch}"
            )
        merged_head = _git(["rev-parse", "HEAD"], root).stdout.strip()
        local_landed = _git(
            ["merge-base", "--is-ancestor", local_head, merged_head], root
        )
        remote_landed = _git(
            ["merge-base", "--is-ancestor", remote_head, merged_head], root
        )
        clean_after = _git(["status", "--porcelain", "--untracked-files=all"], root)
        if (
            not merged_head
            or local_landed.returncode != 0
            or remote_landed.returncode != 0
            or clean_after.returncode != 0
            or clean_after.stdout.strip()
        ):
            raise GitError(f"could not verify synchronized history for {branch}")
    return _git(["rev-parse", "HEAD"], root).stdout.strip()


def create_merge_request(
    root: Path,
    *,
    title: str,
    body: str,
    source_branch: str,
    target_branch: str,
    draft: bool = False,
    remote: str = "origin",
    runner: Runner = _command,
) -> MergeRequest:
    """Open a merge request and return its web URL."""

    forge = detect_forge(root, remote)
    if forge is None:
        raise GitError("origin is not a recognized GitHub or GitLab remote")
    if forge == "github":
        args = [
            "gh",
            "pr",
            "create",
            "--title",
            title,
            "--body",
            body,
            "--head",
            source_branch,
            "--base",
            target_branch,
        ]
        if draft:
            args.append("--draft")
    else:
        args = [
            "glab",
            "mr",
            "create",
            "--yes",
            "--title",
            title,
            "--description",
            body,
            "--source-branch",
            source_branch,
            "--target-branch",
            target_branch,
        ]
        if draft:
            args.append("--draft")
    result = runner(args, root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise GitError(detail or "merge request creation failed")
    match = re.search(r"https?://[^\s]+", result.stdout + "\n" + result.stderr)
    if match is None:
        raise GitError("forge did not return a merge request URL")
    url = match.group(0).rstrip(".,)")
    number_match = re.search(r"/(?:pull|merge_requests)/(\d+)(?:\D|$)", url)
    return MergeRequest(
        url=url,
        number=number_match.group(1) if number_match else None,
        forge=forge,
        source_branch=source_branch,
        target_branch=target_branch,
        draft=draft,
    )


def find_merge_request(
    root: Path,
    *,
    source_branch: str,
    target_branch: str,
    runner: Runner = _command,
) -> MergeRequest | None:
    """Find an existing review for a branch so publication survives retries."""

    forge = detect_forge(root)
    if forge == "github":
        args = [
            "gh",
            "pr",
            "list",
            "--state",
            "all",
            "--head",
            source_branch,
            "--json",
            "url,number,baseRefName,isDraft,state",
        ]
    elif forge == "gitlab":
        args = [
            "glab",
            "mr",
            "list",
            "--all",
            "--source-branch",
            source_branch,
            "--output",
            "json",
        ]
    else:
        raise GitError("origin is not a recognized GitHub or GitLab remote")
    result = runner(args, root)
    if result.returncode != 0:
        raise GitError(
            (result.stderr or result.stdout).strip() or "review lookup failed"
        )
    try:
        rows = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GitError("forge returned invalid review list JSON") from exc
    if not isinstance(rows, list):
        raise GitError("forge returned invalid review list JSON")
    for row in rows:
        if not isinstance(row, dict):
            continue
        base = str(row.get("baseRefName") or row.get("target_branch") or "")
        url = str(row.get("url") or row.get("web_url") or "")
        state = str(row.get("state") or "").lower()
        # This helper is an idempotent *open review* lookup.  Returning a
        # merged row makes a later repair generation accidentally reuse an
        # already-accepted review URL instead of opening its follow-up.
        if base != target_branch or not url or state not in {"open", "opened"}:
            continue
        number = row.get("number") or row.get("iid")
        return MergeRequest(
            url=url,
            number=str(number) if number is not None else None,
            forge=forge,
            source_branch=source_branch,
            target_branch=base,
            draft=bool(row.get("isDraft", row.get("draft", False))),
        )
    return None


def merge_request_snapshot(
    root: Path,
    mr: MergeRequest,
    *,
    runner: Runner = _command,
) -> dict[str, object]:
    """Return normalized state and discussion rows for one MR/PR."""

    if mr.forge == "github":
        args = [
            "gh",
            "pr",
            "view",
            mr.url,
            "--json",
            "state,isDraft,comments,reviews,url,headRefName,baseRefName,commits,body,mergeCommit,mergeable,mergeStateStatus,reviewDecision",
        ]
    else:
        args = ["glab", "mr", "view", mr.url, "--output", "json"]
    result = runner(args, root)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        if re.search(
            r"(?:\b404\b|not found|could not resolve.*pullrequest)", detail, re.I
        ):
            raise ReviewNotFound(detail or mr.url)
        raise GitError(detail or "MR poll failed")
    try:
        raw = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise GitError("forge returned invalid MR JSON") from exc
    if not isinstance(raw, dict):
        raise GitError("forge returned invalid MR JSON")
    if mr.forge == "github":
        comments = list(raw.get("comments") or []) + list(raw.get("reviews") or [])
        match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", mr.url)
        if match:
            inline = runner(
                [
                    "gh",
                    "api",
                    f"repos/{match.group(1)}/{match.group(2)}/pulls/{match.group(3)}/comments",
                ],
                root,
            )
            if inline.returncode == 0:
                try:
                    rows = json.loads(inline.stdout)
                    if isinstance(rows, list):
                        comments.extend(rows)
                except json.JSONDecodeError:
                    pass
        state = str(raw.get("state") or "").lower()
        target_branch = str(raw.get("baseRefName") or "").strip()
        source_branch = str(raw.get("headRefName") or "").strip()
        mergeable = str(raw.get("mergeable") or "").lower()
        merge_state = str(raw.get("mergeStateStatus") or "").lower()
    else:
        comments = list(raw.get("notes") or raw.get("discussions") or [])
        state = str(raw.get("state") or "").lower()
        if raw.get("merged_at"):
            state = "merged"
        target_branch = str(
            raw.get("target_branch") or raw.get("targetBranch") or ""
        ).strip()
        source_branch = str(
            raw.get("source_branch") or raw.get("sourceBranch") or ""
        ).strip()
        mergeable = str(raw.get("merge_status") or raw.get("mergeStatus") or "").lower()
        merge_state = str(
            raw.get("detailed_merge_status") or raw.get("detailedMergeStatus") or ""
        ).lower()
    observed_url = str(raw.get("url") or raw.get("web_url") or mr.url).strip()
    out: dict[str, object] = {
        "state": state,
        "comments": comments,
        "url": observed_url,
        "source_revision": None,
        "target_revision": None,
        "review_identity": {
            "forge": mr.forge,
            "url": mr.url,
            "number": mr.number,
            "source_branch": mr.source_branch,
            "target_branch": mr.target_branch,
        },
    }
    if mergeable in {
        "conflicting",
        "cannot_be_merged",
        "cannot_be_merged_recheck",
    } or merge_state in {"dirty", "conflict", "conflicts", "cannot_be_merged"}:
        out["mergeability"] = "conflicting"
    elif mergeable in {"mergeable", "can_be_merged"}:
        out["mergeability"] = "mergeable"
    else:
        out["mergeability"] = "unknown"
    merge_commit = (
        raw.get("mergeCommit") if mr.forge == "github" else raw.get("merge_commit_sha")
    )
    merge_sha = (
        merge_commit.get("oid") if isinstance(merge_commit, dict) else merge_commit
    )
    if isinstance(merge_sha, str) and merge_sha:
        out["merge_sha"] = merge_sha
    description = raw.get("body") if mr.forge == "github" else raw.get("description")
    if isinstance(description, str):
        out["description"] = description
    if mr.forge == "github":
        commits = raw.get("commits")
        if (
            not isinstance(commits, list)
            or not commits
            or not isinstance(commits[-1], dict)
            or not isinstance(commits[-1].get("oid"), str)
            or not commits[-1]["oid"].strip()
        ):
            raise GitError("forge returned invalid GitHub commits JSON")
        source_revision = commits[-1]["oid"].strip()
    else:
        source_revision = raw.get("sha")
    diff_refs = raw.get("diff_refs")
    if not source_revision and isinstance(diff_refs, dict):
        source_revision = diff_refs.get("head_sha")
    if isinstance(source_revision, str) and source_revision:
        out["source_revision"] = source_revision
    if target_branch:
        out["target_branch"] = target_branch
    if source_branch:
        out["source_branch"] = source_branch
    if mr.forge == "github":
        _add_github_review_evidence(root, mr, raw, out, runner=runner)
    else:
        _add_gitlab_review_evidence(root, mr, raw, out, runner=runner)
    out["review_health"] = _review_health(out)
    return out


def _run_json(
    runner: Runner, args: list[str], root: Path
) -> tuple[object | None, str | None, int]:
    """Run a fixed forge query and retain unavailable evidence without executing output."""

    result = runner(args, root)
    if result.returncode != 0:
        return (
            None,
            (result.stderr or result.stdout).strip() or "forge query failed",
            result.returncode,
        )
    try:
        return json.loads(result.stdout), None, 0
    except json.JSONDecodeError:
        return None, "forge returned invalid JSON", 0


def _unavailable(reason: str) -> dict[str, object]:
    return {"available": False, "reason": reason}


def _github_location(url: str) -> tuple[str, str, str] | None:
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", url)
    return match.groups() if match else None


def _head_from_branch_payload(payload: object) -> str | None:
    if not isinstance(payload, Mapping):
        return None
    commit = payload.get("commit")
    if isinstance(commit, Mapping) and isinstance(commit.get("sha"), str):
        return str(commit["sha"]).strip() or None
    obj = payload.get("object")
    if isinstance(obj, Mapping) and isinstance(obj.get("sha"), str):
        return str(obj["sha"]).strip() or None
    return None


def _github_required_names(payload: object) -> list[str] | None:
    if not isinstance(payload, Mapping):
        return None
    if "contexts" not in payload and "checks" not in payload:
        return None
    names: list[str] = []
    contexts = payload.get("contexts")
    if isinstance(contexts, list):
        names.extend(str(item) for item in contexts if isinstance(item, str) and item)
    checks = payload.get("checks")
    if isinstance(checks, list):
        names.extend(
            str(item.get("context"))
            for item in checks
            if isinstance(item, Mapping) and isinstance(item.get("context"), str)
        )
    return sorted(set(names))


def _github_check_results(
    check_payload: object,
    status_payload: object,
    *,
    source_head: str,
    target_head: str | None,
) -> dict[str, object]:
    rows: dict[str, dict[str, object]] = {}
    if not isinstance(check_payload, Mapping) or not isinstance(
        status_payload, Mapping
    ):
        return _unavailable("check_results_unavailable")
    check_runs = check_payload.get("check_runs")
    statuses = status_payload.get("statuses")
    if not isinstance(check_runs, list) or not isinstance(statuses, list):
        return _unavailable("check_results_malformed")
    for item in [*check_runs, *statuses]:
        if not isinstance(item, Mapping):
            continue
        name = item.get("name") or item.get("context")
        if not isinstance(name, str) or not name:
            continue
        generation = item.get("id") or item.get("external_id") or item.get("updated_at")
        conclusion = str(
            item.get("conclusion")
            or item.get("state")
            or item.get("status")
            or "unknown"
        ).lower()
        status = {
            "success": "success",
            "passed": "success",
            "neutral": "success",
            "skipped": "success",
            "failure": "failure",
            "failed": "failure",
            "error": "failure",
            "cancelled": "failure",
            "timed_out": "failure",
            "action_required": "failure",
            "pending": "pending",
            "queued": "pending",
            "in_progress": "pending",
            "requested": "pending",
            "waiting": "pending",
        }.get(conclusion, "unknown")
        order = str(
            item.get("completed_at")
            or item.get("started_at")
            or item.get("updated_at")
            or ""
        )
        numeric = generation if isinstance(generation, int) else -1
        candidate = {
            "status": status,
            "generation": generation,
            "source_head": str(item.get("head_sha") or source_head),
            "observed_at": order or None,
            "_order": (order, numeric),
        }
        if name not in rows or candidate["_order"] >= rows[name]["_order"]:
            rows[name] = candidate
    normalized = {
        name: {key: value for key, value in row.items() if key != "_order"}
        for name, row in sorted(rows.items())
    }
    return {
        "available": True,
        "source_head": source_head,
        "target_head": target_head,
        "statuses": {name: row["status"] for name, row in normalized.items()},
        "checks": normalized,
    }


def _github_feedback(raw: Mapping[str, object], comments: object) -> dict[str, object]:
    reviews = raw.get("reviews")
    if not isinstance(reviews, list):
        return _unavailable("review_feedback_malformed")
    latest: dict[str, Mapping[str, object]] = {}
    for review in reviews:
        if not isinstance(review, Mapping):
            continue
        author = review.get("author")
        login = author.get("login") if isinstance(author, Mapping) else author
        if isinstance(login, str) and login:
            latest[login] = review
    approvals = sorted(
        login
        for login, review in latest.items()
        if str(review.get("state") or "").upper() == "APPROVED"
    )
    changes = sorted(
        login
        for login, review in latest.items()
        if str(review.get("state") or "").upper() == "CHANGES_REQUESTED"
    )
    actionable_feedback = [
        {
            "id": latest[login].get("id"),
            "reviewer": login,
            "submitted_at": latest[login].get("submittedAt")
            or latest[login].get("submitted_at"),
        }
        for login in changes
    ]
    decision = str(raw.get("reviewDecision") or "").lower() or "unknown"
    return {
        "available": True,
        "approval_state": "approved"
        if decision == "approved"
        else "changes_requested"
        if changes
        else "waiting",
        "decision": decision,
        "approvals": approvals,
        "actionable": bool(changes),
        "actionable_reviewers": changes,
        "actionable_feedback": actionable_feedback,
    }


def _add_github_review_evidence(
    root: Path,
    mr: MergeRequest,
    raw: Mapping[str, object],
    out: dict[str, object],
    *,
    runner: Runner,
) -> None:
    location = _github_location(mr.url)
    source_head = out.get("source_revision")
    if location is None or not isinstance(source_head, str):
        out["required_check_policy"] = _unavailable("review_identity_unavailable")
        out["required_check_results"] = _unavailable("review_identity_unavailable")
        out["review_feedback"] = _unavailable("review_identity_unavailable")
        return
    owner, repo, _number = location
    target_branch = str(out.get("target_branch") or mr.target_branch)
    target_path = quote(target_branch, safe="")
    branch, branch_error, _ = _run_json(
        runner, ["gh", "api", f"repos/{owner}/{repo}/branches/{target_path}"], root
    )
    target_head = _head_from_branch_payload(branch)
    if target_head:
        out["target_revision"] = target_head
    policy_payload, policy_error, policy_code = _run_json(
        runner,
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/branches/{target_path}/protection/required_status_checks",
        ],
        root,
    )
    required = _github_required_names(policy_payload)
    if required is not None:
        policy: dict[str, object] = {
            "available": True,
            "source_head": source_head,
            "target_head": target_head,
            "required": required,
            "confirmed_empty": not required,
        }
    elif (
        policy_code != 0
        and policy_error
        and re.search(r"branch (?:is )?not protected", policy_error, re.I)
    ):
        policy = {
            "available": True,
            "source_head": source_head,
            "target_head": target_head,
            "required": [],
            "confirmed_empty": True,
        }
    else:
        policy = _unavailable(policy_error or "required_check_policy_malformed")
        policy.update(source_head=source_head, target_head=target_head)
    if branch_error or not target_head:
        policy = _unavailable(branch_error or "target_head_unavailable")
        policy.update(source_head=source_head, target_head=None)
    out["required_check_policy"] = policy
    check_payload, check_error, _ = _run_json(
        runner,
        ["gh", "api", f"repos/{owner}/{repo}/commits/{source_head}/check-runs"],
        root,
    )
    status_payload, status_error, _ = _run_json(
        runner,
        ["gh", "api", f"repos/{owner}/{repo}/commits/{source_head}/status"],
        root,
    )
    results = _github_check_results(
        check_payload, status_payload, source_head=source_head, target_head=target_head
    )
    if check_error or status_error:
        results = _unavailable(
            check_error or status_error or "check_results_unavailable"
        )
        results.update(source_head=source_head, target_head=target_head)
    out["required_check_results"] = results
    out["review_feedback"] = _github_feedback(raw, out.get("comments"))


def _gitlab_location(url: str) -> tuple[str, str] | None:
    match = re.match(r"https?://[^/]+/(.+)/-/merge_requests/(\d+)", url)
    return match.groups() if match else None


def _add_gitlab_review_evidence(
    root: Path,
    mr: MergeRequest,
    raw: Mapping[str, object],
    out: dict[str, object],
    *,
    runner: Runner,
) -> None:
    location = _gitlab_location(mr.url)
    source_head = out.get("source_revision")
    if location is None or not isinstance(source_head, str):
        for key in (
            "required_check_policy",
            "required_check_results",
            "review_feedback",
        ):
            out[key] = _unavailable("review_identity_unavailable")
        return
    project, iid = location
    project_id = quote(project, safe="")
    target_branch = str(out.get("target_branch") or mr.target_branch)
    branch, branch_error, _ = _run_json(
        runner,
        [
            "glab",
            "api",
            f"projects/{project_id}/repository/branches/{quote(target_branch, safe='')}",
        ],
        root,
    )
    target_head = _head_from_branch_payload(branch)
    if target_head:
        out["target_revision"] = target_head
    project_payload, project_error, _ = _run_json(
        runner, ["glab", "api", f"projects/{project_id}"], root
    )
    if (
        isinstance(project_payload, Mapping)
        and isinstance(
            project_payload.get("only_allow_merge_if_pipeline_succeeds"), bool
        )
        and target_head
    ):
        required = (
            ["pipeline"]
            if project_payload["only_allow_merge_if_pipeline_succeeds"]
            else []
        )
        out["required_check_policy"] = {
            "available": True,
            "source_head": source_head,
            "target_head": target_head,
            "required": required,
            "confirmed_empty": not required,
        }
    else:
        out["required_check_policy"] = {
            **_unavailable(
                branch_error or project_error or "required_check_policy_malformed"
            ),
            "source_head": source_head,
            "target_head": target_head,
        }
    pipelines, pipeline_error, _ = _run_json(
        runner,
        ["glab", "api", f"projects/{project_id}/merge_requests/{iid}/pipelines"],
        root,
    )
    matching = (
        [
            item
            for item in pipelines
            if isinstance(item, Mapping) and item.get("sha") == source_head
        ]
        if isinstance(pipelines, list)
        else []
    )
    matching.sort(
        key=lambda item: (
            str(item.get("updated_at") or item.get("created_at") or ""),
            int(item.get("id") or 0),
        )
    )
    if pipeline_error:
        results = {
            **_unavailable(pipeline_error),
            "source_head": source_head,
            "target_head": target_head,
        }
    elif matching:
        latest = matching[-1]
        raw_status = str(latest.get("status") or "unknown").lower()
        status = (
            "success"
            if raw_status in {"success", "passed"}
            else "failure"
            if raw_status in {"failed", "failure", "canceled", "cancelled"}
            else "pending"
            if raw_status
            in {
                "created",
                "pending",
                "running",
                "waiting_for_resource",
                "preparing",
                "scheduled",
            }
            else "unknown"
        )
        pipeline_id = latest.get("id")
        jobs, jobs_error, _ = _run_json(
            runner,
            ["glab", "api", f"projects/{project_id}/pipelines/{pipeline_id}/jobs"],
            root,
        )
        checks: dict[str, dict[str, object]] = {
            "pipeline": {
                "status": status,
                "generation": pipeline_id,
                "source_head": source_head,
                "observed_at": latest.get("updated_at") or latest.get("created_at"),
            }
        }
        if jobs_error is None and isinstance(jobs, list):
            for job in jobs:
                if not isinstance(job, Mapping) or not isinstance(job.get("name"), str):
                    continue
                job_status = str(job.get("status") or "unknown").lower()
                normalized_status = (
                    "success"
                    if job_status in {"success", "passed", "skipped"}
                    else "failure"
                    if job_status in {"failed", "failure", "canceled", "cancelled"}
                    else "pending"
                    if job_status
                    in {
                        "created",
                        "pending",
                        "running",
                        "waiting_for_resource",
                        "preparing",
                        "scheduled",
                    }
                    else "unknown"
                )
                checks[str(job["name"])] = {
                    "status": normalized_status,
                    "generation": {"pipeline_id": pipeline_id, "job_id": job.get("id")},
                    "source_head": source_head,
                    "observed_at": job.get("finished_at") or job.get("started_at"),
                }
        results = {
            "available": True,
            "source_head": source_head,
            "target_head": target_head,
            "statuses": {name: check["status"] for name, check in checks.items()},
            "checks": checks,
        }
    else:
        results = {
            "available": True,
            "source_head": source_head,
            "target_head": target_head,
            "statuses": {},
            "checks": {},
        }
    out["required_check_results"] = results
    approvals, approval_error, _ = _run_json(
        runner,
        ["glab", "api", f"projects/{project_id}/merge_requests/{iid}/approval_state"],
        root,
    )
    if isinstance(approvals, Mapping):
        rules = approvals.get("rules")
        rules = rules if isinstance(rules, list) else []
        approved = (
            all(
                bool(rule.get("approved"))
                for rule in rules
                if isinstance(rule, Mapping)
            )
            if rules
            else True
        )
        notes = out.get("comments")
        actionable = (
            [
                note
                for note in notes
                if isinstance(note, Mapping)
                and note.get("resolvable") is True
                and note.get("resolved") is not True
            ]
            if isinstance(notes, list)
            else []
        )
        out["review_feedback"] = {
            "available": True,
            "approval_state": "approved" if approved else "waiting",
            "actionable": bool(actionable),
            "actionable_feedback": actionable,
            "rules": rules,
        }
    else:
        out["review_feedback"] = _unavailable(
            approval_error or "review_feedback_malformed"
        )


def _review_health(snapshot: Mapping[str, object]) -> dict[str, object]:
    state = str(snapshot.get("state") or "unknown").lower()
    if state not in {"open", "opened"}:
        return {"state": "terminal", "reason": state}
    identity = snapshot.get("review_identity")
    if not isinstance(identity, Mapping) or any(
        snapshot.get(observed) != identity.get(expected)
        for observed, expected in (
            ("url", "url"),
            ("source_branch", "source_branch"),
            ("target_branch", "target_branch"),
        )
    ):
        return {
            "state": "conflict_or_moving_target",
            "reason": "review_identity_changed",
        }
    if snapshot.get("mergeability") == "conflicting":
        return {"state": "conflict_or_moving_target", "reason": "merge_conflict"}
    feedback = snapshot.get("review_feedback")
    if isinstance(feedback, Mapping) and feedback.get("actionable") is True:
        return {"state": "actionable_human_feedback", "reason": "changes_requested"}
    if snapshot.get("mergeability") == "unknown":
        return {"state": "transient_outage", "reason": "mergeability_unknown"}
    policy = snapshot.get("required_check_policy")
    results = snapshot.get("required_check_results")
    if not isinstance(policy, Mapping) or policy.get("available") is not True:
        return {
            "state": "transient_outage",
            "reason": "required_check_policy_unavailable",
        }
    if policy.get("source_head") != snapshot.get("source_revision") or policy.get(
        "target_head"
    ) != snapshot.get("target_revision"):
        return {"state": "conflict_or_moving_target", "reason": "stale_head_pair"}
    if not isinstance(results, Mapping) or results.get("available") is not True:
        return {
            "state": "transient_outage",
            "reason": "required_check_results_unavailable",
        }
    if results.get("source_head") != snapshot.get("source_revision"):
        return {
            "state": "conflict_or_moving_target",
            "reason": "stale_check_generation",
        }
    required = policy.get("required")
    statuses = results.get("statuses")
    if not isinstance(required, list) or not isinstance(statuses, Mapping):
        return {"state": "transient_outage", "reason": "check_evidence_malformed"}
    missing = [name for name in required if name not in statuses]
    if missing:
        return {"state": "missing", "checks": missing}
    checks = results.get("checks")
    if isinstance(checks, Mapping) and any(
        not isinstance(checks.get(name), Mapping)
        or checks[name].get("source_head") != snapshot.get("source_revision")
        for name in required
    ):
        return {
            "state": "conflict_or_moving_target",
            "reason": "stale_check_generation",
        }
    failed = [name for name in required if statuses.get(name) == "failure"]
    if failed:
        return {"state": "failed", "checks": failed}
    pending = [name for name in required if statuses.get(name) != "success"]
    if pending:
        return {"state": "pending", "checks": pending}
    if isinstance(feedback, Mapping) and feedback.get("approval_state") == "waiting":
        return {"state": "approval_only_wait", "reason": "approval_pending"}
    return {"state": "green", "checks": required}


def reply_to_merge_request(
    root: Path,
    mr_url: str,
    body: str,
    *,
    runner: Runner = _command,
) -> None:
    forge = detect_forge(root)
    if forge == "github":
        args = ["gh", "pr", "comment", mr_url, "--body", body]
    elif forge == "gitlab":
        args = ["glab", "mr", "note", mr_url, "--message", body]
    else:
        raise GitError("origin is not a recognized GitHub or GitLab remote")
    result = runner(args, root)
    if result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or "MR reply failed")


def fast_forward_trunk(
    root: Path,
    trunk: str,
    *,
    remote: str = "origin",
) -> str:
    """Fetch and safely fast-forward the checked-out trunk.

    Git itself rejects a merge that would overwrite local tracked changes.  A
    blanket dirty-tree check is too strict: it prevents an already-current
    pull and fast-forwards whose incoming paths do not overlap local edits.
    """

    branch = _git(["branch", "--show-current"], root).stdout.strip()
    if branch != trunk:
        raise GitError(f"workspace must be on {trunk!r} to pull briefs")
    fetch = _git(["fetch", remote, trunk], root)
    if fetch.returncode != 0:
        detail = (fetch.stderr or fetch.stdout).strip()
        if (
            "couldn't find remote ref" in detail
            or "could not find remote ref" in detail
        ):
            raise GitError(
                f"{remote} has no branch {trunk!r}; push or configure the product "
                "trunk before pulling briefs"
            )
        raise GitError(detail or "fetch failed")
    local_sha = _git(["rev-parse", "HEAD"], root).stdout.strip()
    remote_sha_result = _git(["rev-parse", f"{remote}/{trunk}"], root)
    if remote_sha_result.returncode != 0:
        raise GitError(
            (remote_sha_result.stderr or remote_sha_result.stdout).strip()
            or f"remote branch {remote}/{trunk} is unavailable"
        )
    remote_sha = remote_sha_result.stdout.strip()
    if local_sha == remote_sha:
        return local_sha
    merge = _git(["merge", "--ff-only", f"{remote}/{trunk}"], root)
    if merge.returncode != 0:
        raise GitError((merge.stderr or merge.stdout).strip() or "fast-forward failed")
    return _git(["rev-parse", "HEAD"], root).stdout.strip()


_RUNTIME_PREFIXES = (
    "docs/_queue/",
    "docs/_comments/",
    "docs/_amendments/",
    "docs/_war_room/",
)


def _unsafe_tracked_changes(porcelain: str) -> list[str]:
    """Return tracked edits outside append-only/runtime sidecar directories."""

    unsafe: list[str] = []
    for line in porcelain.splitlines():
        if len(line) < 4:
            continue
        value = line[3:]
        # Rename porcelain is ``old -> new``; both paths must be runtime paths.
        paths = [part.strip().strip('"') for part in value.split(" -> ")]
        if not paths or any(not path.startswith(_RUNTIME_PREFIXES) for path in paths):
            unsafe.extend(paths or [value])
    return unsafe
