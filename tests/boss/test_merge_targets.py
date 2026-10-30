"""Stacked merge targets: task→feat, feature→epic, epic→trunk (task_069)."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import cascade.boss.epic_complete as epic_complete_module
import cascade.boss.rollup as rollup_module
from cascade.board.store import move_doc, read_doc, read_doc_in_worktree
from cascade.board.parse import render_doc
from cascade.boss.epic_complete import confirm_epic_complete
from cascade.boss.epic_complete import confirm_epic_complete_result
from cascade.boss import merge as merge_module
from cascade.boss.merge import merge_feature_branch, merge_task_branch, promote_epic_to_trunk
from cascade.boss.rollup import try_complete_feature, write_closeout
from cascade.completion_reconcile import reconcile_completion
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace.doc_root import read_doc_resolved, resolve_doc_worktree
from cascade.workspace.integration_worktree import (
    integration_branch,
    integration_worktree_path,
    load_registry,
    merged_board,
    save_registry,
)
from cascade.tracking import MergeRequest
from cascade.watchdog.events import read_events
from tests.support import add_doc, commit_board, make_repo, approve_board_feature


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_task_runs()
    yield
    clear_task_runs()


def test_terminal_worktree_cleanup_is_best_effort(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    root = make_repo(tmp_path)

    def cleanup_failed(*args, **kwargs) -> bool:
        raise OSError("worktree disappeared during cleanup")

    monkeypatch.setattr(
        "cascade.workspace.integration_worktree.retire_integration_worktree",
        cleanup_failed,
    )

    rollup_module._retire_feature_worktree("feat_001", "epic_001", root)
    epic_complete_module._retire_epic_worktree("epic_001", root)

    assert "could not retire completed feature worktree feat_001" in caplog.text
    assert "could not retire completed epic worktree epic_001" in caplog.text


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def _commit_in_worktree(worktree: Path, rel: str, content: str, message: str) -> None:
    path = worktree / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    subprocess.run(["git", "add", rel], cwd=worktree, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", message], cwd=worktree, check=True, capture_output=True)


def _reviewed_epic_with_remote(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    root = make_repo(tmp_path / "operator")
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", status="completed", parent="epic_001")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "remote", "add", "origin", str(remote)], cwd=root, check=True)
    subprocess.run(["git", "push", "origin", "main", "epic/epic_001"], cwd=root, check=True, capture_output=True)
    review = MergeRequest(
        url="https://github.example/pull/1", number="1", forge="github",
        source_branch="epic/epic_001", target_branch="main", draft=False,
    )
    monkeypatch.setattr("cascade.review.ensure_epic_review", lambda *_a, **_k: review)
    accepted_tip = subprocess.run(
        ["git", "rev-parse", "epic/epic_001"],
        cwd=root, check=True, capture_output=True, text=True,
    ).stdout.strip()
    monkeypatch.setattr(
        "cascade.review.merge_request_snapshot",
        lambda *_a, **_k: {"state": "merged", "merge_sha": accepted_tip},
    )
    return root, epic_wt


def test_merged_epic_close_preserves_dirty_operator_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, epic_wt = _reviewed_epic_with_remote(tmp_path, monkeypatch)
    reviewer = tmp_path / "reviewer"
    subprocess.run(["git", "clone", str(tmp_path / "remote.git"), str(reviewer)], check=True, capture_output=True)
    subprocess.run(["git", "checkout", "-B", "main", "origin/main"], cwd=reviewer, check=True, capture_output=True)
    merged = subprocess.run(
        ["git", "merge", "--no-ff", "--no-edit", "origin/epic/epic_001"],
        cwd=reviewer, capture_output=True,
    )
    assert merged.returncode != 0  # activation's expected pointer conflict
    epic_path = "docs/epics/2_active/epic_001_epic.md"
    subprocess.run(["git", "checkout", "--theirs", "--", epic_path], cwd=reviewer, check=True, capture_output=True)
    subprocess.run(["git", "add", "--", epic_path], cwd=reviewer, check=True, capture_output=True)
    subprocess.run(["git", "-c", "commit.gpgsign=false", "commit", "--no-edit"], cwd=reviewer, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=reviewer, check=True, capture_output=True)

    tracked = root / "README.md"
    tracked.write_text("operator edit\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    # The operator may also have a stale full active spec instead of a stub.
    # Closing must still prefer the completed integration copy without writing
    # over this tracked local file.
    local_epic = read_doc_in_worktree("epic_001", root)
    live_epic = read_doc_in_worktree("epic_001", epic_wt)
    local_epic.body = live_epic.body
    local_epic.meta.integration_branch = None
    local_epic.meta.integration_worktree = None
    local_epic.meta.path.write_text(render_doc(local_epic), encoding="utf-8")
    untracked = root / "untracked.txt"
    untracked.write_text("keep me\n", encoding="utf-8")
    from cascade.workspace.closeout import create_verified_trunk_workspace

    closeout_resources: list[Path] = []

    def capture_closeout_workspace(*args, **kwargs):
        workspace = create_verified_trunk_workspace(*args, **kwargs)
        closeout_resources.extend((workspace.path, workspace._temporary_root))
        return workspace

    monkeypatch.setattr(
        "cascade.workspace.closeout.create_verified_trunk_workspace",
        capture_closeout_workspace,
    )
    monkeypatch.setattr(
        "cascade.boss.epic_close_review.create_verified_trunk_workspace",
        capture_closeout_workspace,
    )
    operator_snapshot = {
        "tracked": {
            "README.md": tracked.read_bytes(),
            epic_path: local_epic.meta.path.read_bytes(),
        },
        "untracked": {untracked.name: untracked.read_bytes()},
        "head": subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "branch": subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "index": subprocess.run(
            ["git", "ls-files", "--stage", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout,
        "status": subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout,
    }

    monkeypatch.setattr("cascade.boss.epic_close_review.find_merge_request", lambda *_a, **_k: None)
    close_review = MergeRequest(
        url="https://github.example/pull/2", number="2", forge="github",
        source_branch="cascade/epic-close/epic_001", target_branch="main", draft=False,
    )
    monkeypatch.setattr("cascade.boss.epic_close_review.create_merge_request", lambda *_a, **_k: close_review)
    pending = confirm_epic_complete_result("epic_001", "human", root=root)
    assert not pending.ok and pending.reason == "pending_close_review"
    assert pending.review_url == close_review.url
    assert read_doc("epic_001", root=root).meta.status == "active"
    assert not [event for event in read_events("war_room", 0, root=root)[0] if event.type == "EpicCompleted"]
    monkeypatch.setattr(
        "cascade.boss.epic_close_review.find_merge_request", lambda *_a, **_k: close_review
    )
    monkeypatch.setattr(
        "cascade.boss.epic_close_review.create_merge_request",
        lambda *_a, **_k: pytest.fail("existing closeout review must be reused"),
    )
    repeated = confirm_epic_complete_result("epic_001", "human", root=root)
    assert repeated.reason == "pending_close_review"
    assert repeated.review_url == close_review.url
    subprocess.run(["git", "fetch", "origin"], cwd=reviewer, check=True, capture_output=True)
    subprocess.run(["git", "merge", "--no-ff", "--no-edit", "origin/cascade/epic-close/epic_001"], cwd=reviewer, check=True, capture_output=True)
    subprocess.run(["git", "push", "origin", "main"], cwd=reviewer, check=True, capture_output=True)

    import cascade.review as review_module

    merged_snapshot = review_module.merge_request_snapshot
    monkeypatch.setattr(
        review_module,
        "merge_request_snapshot",
        lambda repo, review: (
            {"state": "open"}
            if review.source_branch.startswith("cascade/epic-close/")
            else merged_snapshot(repo, review)
        ),
    )
    assert confirm_epic_complete_result("epic_001", "human", root=root).reason == "pending_close_review"
    monkeypatch.setattr(review_module, "merge_request_snapshot", merged_snapshot)
    assert confirm_epic_complete_result("epic_001", "human", root=root).ok
    assert confirm_epic_complete_result("epic_001", "human", root=root).ok
    assert merged_board(root).by_id["epic_001"].status == "completed"
    assert read_doc_in_worktree("epic_001", root).meta.status == "active"
    assert epic_wt.is_dir()
    assert tracked.read_bytes() == operator_snapshot["tracked"]["README.md"]
    assert local_epic.meta.path.read_bytes() == operator_snapshot["tracked"][epic_path]
    assert untracked.read_bytes() == operator_snapshot["untracked"][untracked.name]
    assert subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip() == operator_snapshot["head"]
    assert subprocess.run(
        ["git", "branch", "--show-current"], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip() == operator_snapshot["branch"]
    assert subprocess.run(
        ["git", "ls-files", "--stage", "-z"], cwd=root, check=True, capture_output=True
    ).stdout == operator_snapshot["index"]
    assert closeout_resources
    assert all(not resource.exists() for resource in closeout_resources)
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout == operator_snapshot["status"]
    events, _ = read_events("war_room", 0, root=root)
    assert len([event for event in events if event.type == "EpicCompleted"]) == 1


def test_merged_review_state_without_landed_tip_waits_without_touching_operator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, _ = _reviewed_epic_with_remote(tmp_path, monkeypatch)
    (root / "README.md").write_text("operator edit\n", encoding="utf-8")
    before = subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout
    result = confirm_epic_complete_result("epic_001", "human", root=root)
    assert not result.ok and result.reason == "pending_epic_review"
    assert result.review_url == "https://github.example/pull/1"
    assert read_doc("epic_001", root=root).meta.status == "active"
    assert subprocess.run(
        ["git", "status", "--porcelain"], cwd=root, check=True, capture_output=True, text=True
    ).stdout == before


def _stacked_board(root: Path) -> None:
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Task", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    assert dispatch_task("task_001", "human", root=root).ok


def test_task_merge_lands_on_feature_branch_not_trunk(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    trunk_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    run = create_task_worktree("task_001", root=root, parent_rev=None, skills=[])
    _commit_in_worktree(run.worktree, "code.txt", "task change\n", "task work")

    result = merge_task_branch("task_001", root=root)
    assert result.ok is True
    assert result.target_branch == integration_branch("feature", "feat_001")

    trunk_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert trunk_after == trunk_before

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    assert (feat_wt / "code.txt").read_text(encoding="utf-8") == "task change\n"


def test_try_complete_feature_merges_feat_into_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    epic_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=epic_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    _commit_in_worktree(feat_wt, "feature_code.txt", "feature unit\n", "feature work")
    from cascade.board.store import move_doc

    move_doc("task_001", "completed", root=root)
    # The last completed child is sufficient for the deterministic closeout;
    # no additional Feature Team model turn is required.
    assert try_complete_feature("feat_001", root=root) is True

    epic_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=epic_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert epic_after != epic_before
    assert (epic_wt / "feature_code.txt").is_file()
    assert not feat_wt.exists()
    assert all(entry.work_id != "feat_001" for entry in load_registry(root))
    assert subprocess.run(
        ["git", "show-ref", "--verify", "refs/heads/feat/feat_001"],
        cwd=root,
        capture_output=True,
    ).returncode == 0

    merge_only = merge_feature_branch("feat_001", root=root)
    assert merge_only.ok is True


def test_synthesized_closeout_from_trunk_commits_on_feature_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    move_doc("task_001", "completed", root=root)
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr("cascade.review.ensure_feature_review", lambda *_args, **_kwargs: None)

    assert try_complete_feature("feat_001", root=root) is False

    feature = read_doc("feat_001", root=root)
    assert feature.meta.path.is_relative_to(feat_wt)
    assert "Completed child work: `task_001` (Task)." in feature.body
    subject = subprocess.run(
        ["git", "log", "-1", "--format=%s", "--", feature.meta.path],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert subject == "docs: feat_001 Feature"
    status = subprocess.run(
        ["git", "status", "--short", "--", feature.meta.path],
        cwd=feat_wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert status == ""


def test_rollup_uses_live_feature_when_trunk_has_stale_backlog_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    move_doc("task_001", "completed", root=root)
    write_closeout("feat_001", "All child work is complete.", root=root)
    # A trunk copy can outlive activation. It must not override the live spec.
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    assert read_doc("feat_001", root=root).meta.status == "backlog"
    assert read_doc_resolved("feat_001", root=root).meta.status == "active"

    opened: list[str] = []
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)

    def open_review(feature_id: str, *, root: Path) -> object:
        opened.append(feature_id)
        state_path = root / ".cascade" / "reviews.json"
        state_path.write_text(json.dumps({feature_id: {
            "url": "https://example.test/pull/1",
            "source_branch": "feat/feat_001",
            "target_branch": "epic/epic_001",
        }}), encoding="utf-8")
        return object()

    monkeypatch.setattr(
        "cascade.review.ensure_feature_review", open_review,
    )

    assert try_complete_feature("feat_001", root=root) is False
    assert opened == ["feat_001"]
    live = read_doc_in_worktree("feat_001", feat_wt)
    assert live.meta.status == "completed"
    assert "All child work is complete." in live.body


def test_promote_epic_to_trunk_fails_when_epic_branch_absent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    promote = promote_epic_to_trunk("epic_001", root=root)
    assert promote.ok is False
    assert promote.reason == "branch_missing"
    assert promote.branch == integration_branch("epic", "epic_001")


def test_confirm_epic_complete_without_epic_branch_when_epic_not_on_worktree(
    tmp_path: Path,
) -> None:
    """Epic lived on product trunk only (no ``epic/{id}`` integration branch)."""

    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    commit_board(root)

    assert confirm_epic_complete("epic_001", "human", root=root) is True
    assert read_doc("epic_001", root=root).meta.status == "completed"


def test_promote_epic_to_trunk_lands_epic_branch_on_main(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    epic_branch = integration_branch("epic", "epic_001")
    from cascade.workspace.integration_worktree import ensure_integration_worktree

    ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=epic_branch,
        base_ref="HEAD",
        trunk=root,
    )
    commit_board(root, message="integration worktree registry")
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_in_worktree(epic_wt, "promote_me.txt", "epic payload\n", "epic commit")

    trunk_before = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()

    promote = promote_epic_to_trunk("epic_001", root=root)
    assert promote.ok is True
    assert promote.target_branch == "main"
    assert promote.branch == epic_branch

    trunk_after = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert trunk_after != trunk_before
    assert (root / "promote_me.txt").read_text(encoding="utf-8") == "epic payload\n"


def test_confirm_epic_complete_promotes_before_moving_doc(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)

    epic_branch = integration_branch("epic", "epic_001")
    from cascade.workspace.integration_worktree import ensure_integration_worktree

    ensure_integration_worktree(
        "epic",
        "epic_001",
        branch=epic_branch,
        base_ref="HEAD",
        trunk=root,
    )
    commit_board(root, message="integration worktree registry")
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_in_worktree(epic_wt, "promote_me.txt", "epic payload\n", "epic commit")

    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    commit_board(root)

    assert confirm_epic_complete("epic_001", "human", root=root) is True
    assert (root / "promote_me.txt").is_file()
    epic = read_doc("epic_001", root=root)
    assert epic.meta.status == "completed"


def test_activated_epic_closes_through_real_git_promotion(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    epic = add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="ready_to_plan",
    )
    epic.body += "\nFull live epic content must reach trunk.\n"
    epic.meta.path.write_text(render_doc(epic), encoding="utf-8")
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
    pointer = read_doc_in_worktree("epic_001", root)
    assert "Live epic spec is on branch" in pointer.body

    assert confirm_epic_complete("epic_001", "human", root=root) is True

    completed = read_doc("epic_001", root=root)
    assert completed.meta.status == "completed"
    assert completed.meta.path.parent.name == "3_completed"
    assert "Full live epic content must reach trunk." in completed.body
    assert "Live epic spec is on branch" not in completed.body
    assert not integration_worktree_path("epic", "epic_001", trunk=root).exists()
    assert all(entry.work_id != "epic_001" for entry in load_registry(root))
    assert subprocess.run(
        ["git", "show-ref", "--verify", "refs/heads/epic/epic_001"],
        cwd=root,
        capture_output=True,
    ).returncode == 0
    assert subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""


def test_epic_close_opens_review_and_preserves_other_epics_docs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="epic_999", title="Other epic", tier="epic", status="active")
    add_doc(root, id="feat_001", title="Own feature", tier="feature", status="completed", parent="epic_001")
    unrelated = add_doc(root, id="feat_999", title="Other feature", tier="feature", status="completed", parent="epic_999")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok

    import cascade.review as review_module
    from cascade.tracking import MergeRequest

    opened = []
    monkeypatch.setattr(review_module, "review_enabled", lambda _root: True)
    monkeypatch.setattr(review_module, "push_branch", lambda *_a, **_k: None)
    monkeypatch.setattr(review_module, "find_merge_request", lambda *_a, **_k: None)

    def create_review(_root, **kwargs):
        opened.append(kwargs)
        return MergeRequest(
            url="https://github.example/pull/1", number="1", forge="github",
            source_branch=kwargs["source_branch"], target_branch=kwargs["target_branch"], draft=False,
        )

    monkeypatch.setattr(review_module, "create_merge_request", create_review)
    result = confirm_epic_complete_result("epic_001", "human", root=root)
    assert result.reason == "pending_epic_review"
    assert result.review_url == "https://github.example/pull/1"
    assert len(opened) == 1
    assert opened[0]["source_branch"] == "epic/epic_001"
    assert opened[0]["target_branch"] == "main"
    assert unrelated.meta.path.exists()


def test_ready_epic_auto_closes_with_runtime_comment_sidecar(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root, id="feat_001", title="Feature", tier="feature",
        status="completed", parent="epic_001",
    )
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok

    sidecar = root / "docs/_comments/epic_099.jsonl"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    sidecar.write_text('{"author":"human"}\n', encoding="utf-8")

    assert reconcile_completion(root)["epics"] == ["epic_001"]
    assert read_doc("epic_001", root=root).meta.status == "completed"
    assert sidecar.read_text(encoding="utf-8") == '{"author":"human"}\n'
    assert reconcile_completion(root)["epics"] == []


def test_epic_promotion_refuses_preexisting_staged_changes(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    epic_branch = integration_branch("epic", "epic_001")
    from cascade.workspace.integration_worktree import ensure_integration_worktree

    ensure_integration_worktree(
        "epic", "epic_001", branch=epic_branch, base_ref="HEAD", trunk=root
    )
    staged = root / "staged.txt"
    staged.write_text("do not merge\n", encoding="utf-8")
    subprocess.run(["git", "add", "staged.txt"], cwd=root, check=True, capture_output=True)

    promote = promote_epic_to_trunk("epic_001", root=root)

    assert promote.ok is False
    assert promote.reason == "dirty_index"
    assert subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip() == "staged.txt"


def test_epic_promotion_does_not_resolve_unrelated_conflicts(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok

    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_in_worktree(epic_wt, "collision.txt", "epic branch\n", "epic collision")
    _commit_in_worktree(root, "collision.txt", "product trunk\n", "trunk collision")

    promote = promote_epic_to_trunk("epic_001", root=root)

    assert promote.ok is False
    assert promote.reason == "branch_conflict"
    assert "collision.txt" in promote.conflict_paths
    assert (root / "collision.txt").read_text(encoding="utf-8") == "product trunk\n"
    assert not (root / ".git" / "MERGE_HEAD").exists()
    pointer = read_doc_in_worktree("epic_001", root)
    assert "Live epic spec is on branch" in pointer.body


def test_merge_repairs_checkout_when_branch_exists_without_registry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)

    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    _commit_in_worktree(feat_wt, "feature_code.txt", "feature unit\n", "feature work")

    save_registry(
        root,
        [e for e in load_registry(root) if e.work_id not in ("feat_001", "epic_001")],
    )
    shutil.rmtree(feat_wt)
    shutil.rmtree(epic_wt)
    assert not feat_wt.is_dir()
    assert not epic_wt.is_dir()

    feature_checkout = merge_module._feature_merge_checkout(root, "feat_001")
    assert feature_checkout is not None
    assert feature_checkout.is_dir()

    feat_merge = merge_feature_branch("feat_001", root=root)
    assert feat_merge.ok is True
    assert feat_merge.reason != "merge_target_missing"
    assert integration_worktree_path("epic", "epic_001", trunk=root).is_dir()


def test_merge_feature_branch_missing_source_branch_fails(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)
    subprocess.run(
        ["git", "update-ref", "-d", "refs/heads/feat/feat_001"],
        cwd=root,
        check=True,
        capture_output=True,
    )

    result = merge_feature_branch("feat_001", root=root)
    assert result.ok is False
    assert result.reason == "branch_missing"


def test_try_complete_feature_does_not_complete_when_feat_branch_missing(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    _stacked_board(root)
    feat_wt = integration_worktree_path("feature", "feat_001", trunk=root)
    _commit_in_worktree(feat_wt, "feature_code.txt", "feature unit\n", "feature work")
    move_doc("task_001", "completed", root=root)
    write_closeout("feat_001", "All tasks done.", root=root)

    subprocess.run(
        ["git", "update-ref", "-d", "refs/heads/feat/feat_001"],
        cwd=root,
        check=True,
        capture_output=True,
    )

    assert try_complete_feature("feat_001", root=root) is False
    feature = read_doc("feat_001", root=root)
    assert feature.meta.status == "active"
    assert feature.meta.path.parent.name == "2_active"


def test_confirm_epic_complete_updates_trunk_pointer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    from tests.support import commit_board

    commit_board(root)
    assert activate_epic("epic_001", "human", root=root).ok
    epic_wt = integration_worktree_path("epic", "epic_001", trunk=root)
    add_doc(
        epic_wt,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    move_doc("feat_001", "completed", root=root)
    commit_board(epic_wt, message="feature completed on epic branch")
    commit_board(root, message="trunk pointer and board")

    from cascade.boss.merge import MergeResult

    monkeypatch.setattr(
        "cascade.boss.merge.promote_epic_to_trunk",
        lambda *_a, **_k: MergeResult(ok=True, branch="epic/epic_001"),
    )

    assert confirm_epic_complete("epic_001", "human", root=root) is True
    pointer_path = root / "docs" / "epics" / "3_completed"
    pointers = list(pointer_path.glob("epic_001_*.md"))
    assert len(pointers) == 1
    text = pointers[0].read_text(encoding="utf-8")
    assert "status: completed" in text
    assert "integration_branch:" not in text
    assert not list((root / "docs" / "epics" / "2_active").glob("epic_001_*.md"))

    # Retained integration worktrees can have a pre-close active copy (for
    # example, a feature/task checkout forked before the epic was closed).
    # It must not resurrect the epic in the supervisor board or plan API.
    stale = read_doc_in_worktree("epic_001", epic_wt)
    completed_path = stale.meta.path
    stale.meta.status = "active"
    stale.meta.path = epic_wt / "docs/epics/2_active" / completed_path.name
    stale.meta.path.parent.mkdir(parents=True, exist_ok=True)
    stale.meta.path.write_text(render_doc(stale), encoding="utf-8")
    completed_path.unlink()
    assert stale.meta.status == "active"
    visible = merged_board(root).by_id["epic_001"]
    assert visible.status == "completed"
    assert visible.path.parent.name == "3_completed"
    assert resolve_doc_worktree("epic_001", root=root) == root.resolve()
    assert read_doc_resolved("epic_001", root=root).meta.status == "completed"
