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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from cascade.board.errors import GitError

Forge = Literal["github", "gitlab"]
Runner = Callable[[list[str], Path], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class MergeRequest:
    url: str
    number: str | None
    forge: Forge
    source_branch: str
    target_branch: str
    draft: bool


def _command(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=root, capture_output=True, text=True, encoding="utf-8")


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
    """Fetch and fast-forward an integration worktree after its MR merges."""

    current = _git(["branch", "--show-current"], root).stdout.strip()
    if current != branch:
        raise GitError(f"integration worktree must be on {branch!r}, not {current!r}")
    fetch = _git(["fetch", remote, branch], root)
    if fetch.returncode != 0:
        raise GitError((fetch.stderr or fetch.stdout).strip() or f"could not fetch {branch}")
    merge = _git(["merge", "--ff-only", f"{remote}/{branch}"], root)
    if merge.returncode != 0:
        raise GitError(
            (merge.stderr or merge.stdout).strip()
            or f"could not fast-forward {branch}"
        )
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
            "gh", "pr", "create", "--title", title, "--body", body,
            "--head", source_branch, "--base", target_branch,
        ]
        if draft:
            args.append("--draft")
    else:
        args = [
            "glab", "mr", "create", "--yes", "--title", title,
            "--description", body, "--source-branch", source_branch,
            "--target-branch", target_branch,
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
            "gh", "pr", "list", "--state", "all", "--head", source_branch,
            "--json", "url,number,baseRefName,isDraft,state",
        ]
    elif forge == "gitlab":
        args = ["glab", "mr", "list", "--all", "--source-branch", source_branch, "--output", "json"]
    else:
        raise GitError("origin is not a recognized GitHub or GitLab remote")
    result = runner(args, root)
    if result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or "review lookup failed")
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
        if base != target_branch or not url or state == "closed":
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
            "gh", "pr", "view", mr.url, "--json",
            "state,isDraft,comments,reviews,url,baseRefName,mergeCommit",
        ]
    else:
        args = ["glab", "mr", "view", mr.url, "--output", "json"]
    result = runner(args, root)
    if result.returncode != 0:
        raise GitError((result.stderr or result.stdout).strip() or "MR poll failed")
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
                    "gh", "api",
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
    else:
        comments = list(raw.get("notes") or raw.get("discussions") or [])
        state = str(raw.get("state") or "").lower()
        if raw.get("merged_at"):
            state = "merged"
        target_branch = str(
            raw.get("target_branch") or raw.get("targetBranch") or ""
        ).strip()
    out: dict[str, object] = {"state": state, "comments": comments, "url": mr.url}
    merge_commit = raw.get("mergeCommit") if mr.forge == "github" else raw.get("merge_commit_sha")
    merge_sha = merge_commit.get("oid") if isinstance(merge_commit, dict) else merge_commit
    if isinstance(merge_sha, str) and merge_sha:
        out["merge_sha"] = merge_sha
    if target_branch:
        out["target_branch"] = target_branch
    return out


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
        if "couldn't find remote ref" in detail or "could not find remote ref" in detail:
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
