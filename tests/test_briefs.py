from __future__ import annotations

import subprocess
import json
from pathlib import Path

import pytest

from cascade.briefs import build_brief_doc, create_brief, validate_brief
from cascade.approvals import approve_epic_plan, epic_plan_approved
from cascade.tracking import (
    MergeRequest,
    _unsafe_tracked_changes,
    create_merge_request,
    detect_forge,
    fast_forward_trunk,
)
from cascade.watchdog.config import read_automation_config
from cascade.watchdog.events import read_events
from cascade.review import poll_feature_reviews
from cascade.task_rollup import queue_task_merge, retry_pending_task_merges
from cascade.automation import _stale_parent_failures
from cascade.boss.merge import MergeResult
from tests.support import add_doc, make_repo


def _request() -> dict[str, object]:
    return {
        "title": "Search experience",
        "intent": "Help operators find active work.",
        "success_criteria": "Search returns matching epics and features.",
        "constraints": "No hosted index.",
        "provider": "codex",
        "manager_model": "gpt-manager",
        "architect_model": "gpt-architect",
    }


def test_brief_doc_carries_role_models_and_template_sections(tmp_path: Path) -> None:
    request = validate_brief(_request())
    path = tmp_path / "docs/epics/1_backlog/epic_004_search_experience.md"
    doc = build_brief_doc(request, "epic_004", path)

    assert doc.meta.provider == "codex"
    assert doc.meta.models == {
        "epic_manager": "gpt-manager",
        "epic_architect": "gpt-architect",
    }
    assert "## Intent" in doc.body
    assert "## Feature breakdown" in doc.body


def test_validate_brief_requires_both_team_models() -> None:
    raw = _request()
    raw["architect_model"] = ""
    with pytest.raises(ValueError, match="architect model"):
        validate_brief(raw)


def test_create_brief_uses_remote_trunk_and_commits_only_markdown(
    tmp_path: Path, monkeypatch
) -> None:
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    root = make_repo(tmp_path)
    (root / "README.md").write_text("remote trunk\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=root, check=True, capture_output=True)
    remote_sha = subprocess.run(
        ["git", "rev-parse", "origin/main"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()

    (root / "local-only.txt").write_text("must not enter the brief PR\n", encoding="utf-8")
    subprocess.run(["git", "add", "local-only.txt"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-m", "local ahead"], cwd=root, check=True, capture_output=True)

    observed: dict[str, object] = {}

    def inspect_push(worktree: Path, branch: str) -> None:
        observed["branch"] = branch
        observed["parent"] = subprocess.run(
            ["git", "rev-parse", "HEAD^"], cwd=worktree, check=True, capture_output=True, text=True
        ).stdout.strip()
        observed["files"] = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=worktree,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.splitlines()

    monkeypatch.setattr("cascade.briefs.forge_ready", lambda _repo: True)
    monkeypatch.setattr("cascade.briefs.push_branch", inspect_push)
    monkeypatch.setattr(
        "cascade.briefs.create_merge_request",
        lambda _root, **kwargs: MergeRequest(
            url="https://example.test/pull/1",
            number="1",
            forge="github",
            source_branch=str(kwargs["source_branch"]),
            target_branch=str(kwargs["target_branch"]),
            draft=False,
        ),
    )

    epic_id, _mr = create_brief(root, _request())

    assert observed == {
        "branch": f"cascade/brief/{epic_id}",
        "parent": remote_sha,
        "files": [f"docs/epics/1_backlog/{epic_id}_search_experience.md"],
    }


def test_github_merge_request_command_returns_link(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cascade.tracking.remote_url", lambda root, remote="origin": "git@github.com:o/r.git")
    captured: list[str] = []

    def runner(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        captured.extend(args)
        return subprocess.CompletedProcess(args, 0, "https://github.com/o/r/pull/42\n", "")

    mr = create_merge_request(
        tmp_path,
        title="Brief",
        body="body",
        source_branch="cascade/brief/epic_004",
        target_branch="main",
        runner=runner,
    )

    assert mr.url.endswith("/pull/42")
    assert mr.number == "42"
    assert captured[:3] == ["gh", "pr", "create"]


def test_detects_gitlab_remote(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("cascade.tracking.remote_url", lambda root, remote="origin": "https://gitlab.example/acme/repo.git")
    assert detect_forge(tmp_path) == "gitlab"


def test_epic_plan_approval_requires_feature_plan_and_persists(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    with pytest.raises(ValueError, match="no feature plans"):
        approve_epic_plan("epic_001", root=root)
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")

    result = approve_epic_plan("epic_001", root=root)

    assert result["features"] == ["feat_001"]
    assert epic_plan_approved("epic_001", root=root) is True


def test_existing_workspace_must_opt_into_automation(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    assert read_automation_config(root).enabled is False
    (root / "cascade.toml").write_text(
        "[automation]\nenabled = true\npoll_seconds = 9\nremote = \"upstream\"\n",
        encoding="utf-8",
    )
    config = read_automation_config(root)
    assert config.enabled is True
    assert config.poll_seconds == 9
    assert config.remote == "upstream"


def test_feature_review_comment_is_queued_for_feature_team(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    monkeypatch.setattr("cascade.review.locate_trunk", lambda value: Path(value))
    state_path = root / ".cascade" / "reviews.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "feat_001": {
                    "url": "https://github.com/o/r/pull/7",
                    "number": "7",
                    "forge": "github",
                    "source_branch": "feat/feat_001",
                    "target_branch": "epic/epic_001",
                    "draft": True,
                    "seen_comments": [],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda root, mr: {
            "state": "open",
            "comments": [{"id": 81, "body": "Handle the empty state", "author": {"login": "reviewer"}}],
        },
    )

    poll_feature_reviews(root)

    events, _ = read_events("feat_001", 0, root=root)
    assert [event.type for event in events] == ["MergeRequestComment"]
    assert events[0].payload["comment_id"] == "81"
    assert "fixer tasks" in events[0].payload["instruction"]


def test_pull_guard_allows_runtime_sidecars_but_refuses_product_edits() -> None:
    assert _unsafe_tracked_changes(" M docs/_queue/war_room.jsonl\n") == []
    assert _unsafe_tracked_changes(" M docs/_comments/feat_001.jsonl\n") == []
    assert _unsafe_tracked_changes(" M cascade/task/graph.py\n") == ["cascade/task/graph.py"]


def test_pull_already_current_does_not_reject_tracked_edits(
    tmp_path: Path, monkeypatch
) -> None:
    calls: list[list[str]] = []

    def git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args, 0, "main\n", "")
        if args == ["fetch", "origin", "main"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        if args == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "abc\n", "")
        raise AssertionError(args)

    monkeypatch.setattr("cascade.tracking._git", git)
    assert fast_forward_trunk(tmp_path, "main") == "abc"
    assert not [args for args in calls if args and args[0] == "status"]
    assert not [args for args in calls if args and args[0] == "merge"]


def test_pull_delegates_nonconflicting_dirty_fast_forward_to_git(
    tmp_path: Path, monkeypatch
) -> None:
    heads = iter(["old\n", "new\n"])
    calls: list[list[str]] = []

    def git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        calls.append(args)
        if args == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args, 0, "main\n", "")
        if args == ["fetch", "origin", "main"]:
            return subprocess.CompletedProcess(args, 0, "", "")
        if args == ["rev-parse", "HEAD"]:
            return subprocess.CompletedProcess(args, 0, next(heads), "")
        if args == ["rev-parse", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "new\n", "")
        if args == ["merge", "--ff-only", "origin/main"]:
            return subprocess.CompletedProcess(args, 0, "Updating old..new\n", "")
        raise AssertionError(args)

    monkeypatch.setattr("cascade.tracking._git", git)
    assert fast_forward_trunk(tmp_path, "main") == "new"
    assert ["merge", "--ff-only", "origin/main"] in calls


def test_pull_reports_missing_remote_trunk_clearly(tmp_path: Path, monkeypatch) -> None:
    def git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
        if args == ["branch", "--show-current"]:
            return subprocess.CompletedProcess(args, 0, "main\n", "")
        if args == ["fetch", "origin", "main"]:
            return subprocess.CompletedProcess(
                args, 128, "", "fatal: couldn't find remote ref main\n"
            )
        raise AssertionError(args)

    monkeypatch.setattr("cascade.tracking._git", git)
    from cascade.board.errors import GitError

    with pytest.raises(GitError, match="origin has no branch 'main'"):
        fast_forward_trunk(tmp_path, "main")


def test_pending_task_merge_retries_without_an_operator_click(tmp_path: Path, monkeypatch) -> None:
    root = make_repo(tmp_path, git=False)
    merged: list[str] = []
    monkeypatch.setattr(
        "cascade.boss.merge.merge_task_branch",
        lambda task_id, root: MergeResult(ok=True, reason=None, branch="task/" + task_id, merge_sha="abc"),
    )
    monkeypatch.setattr(
        "cascade.boss.rollup.on_task_merged",
        lambda task_id, root: merged.append(task_id),
    )
    queue_task_merge("task_001", root=root)

    assert retry_pending_task_merges(root) == ["task_001"]
    assert merged == ["task_001"]
    assert retry_pending_task_merges(root) == []


def test_only_latest_stale_parent_failure_is_automatically_recoverable(tmp_path: Path) -> None:
    root = make_repo(tmp_path, git=False)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        parent="epic_001",
        status="active",
    )
    add_doc(
        root,
        id="task_001",
        title="Stale child",
        tier="task",
        parent="feat_001",
        status="blocked",
    )
    from cascade.watchdog.events import append_event
    from cascade.watchdog.types import Event
    from datetime import datetime, timezone
    from cascade.workspace.integration_worktree import merged_board

    append_event(
        "feat_001",
        Event(
            type="TaskFailed",
            ts=datetime.now(timezone.utc),
            payload={"task_id": "task_001", "reason": "stale_parent_rev"},
            dest="feat_001",
        ),
        root=root,
    )
    board = merged_board(root)
    assert _stale_parent_failures(["task_001"], board=board, root=root) == ["task_001"]

    append_event(
        "feat_001",
        Event(
            type="TaskActivated",
            ts=datetime.now(timezone.utc),
            payload={"task_id": "task_001", "feature_id": "feat_001"},
            dest="feat_001",
        ),
        root=root,
    )
    assert _stale_parent_failures(["task_001"], board=board, root=root) == []
