from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from cascade.board.errors import GitError
from cascade.board.store import move_doc, read_doc
from cascade.boss.merge import merge_task_branch
from cascade.feature.publication import prepare_feature_publication, validate_feature_publication
from cascade.feature.publication import _build_publication_tail
from cascade.review import ensure_feature_review
from cascade.task.git_tools import swe_commit
from cascade.task.worktree import clear_task_runs, get_task_run
from cascade.tracking import MergeRequest
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace.integration_worktree import IntegrationWorktree, get_integration_worktree
from tests.support import add_doc, make_repo, approve_board_feature


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_task_runs()
    yield
    clear_task_runs()


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


def _completed_feature(
    tmp_path: Path, *, remote_state: str = "missing"
) -> tuple[Path, IntegrationWorktree]:
    root = make_repo(tmp_path)
    (root / "README.md").write_text("board\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "init")
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="ready_to_plan")
    add_doc(root, id="feat_001", title="Feature", tier="feature", parent="epic_001")
    add_doc(root, id="task_001", title="Deliver value", tier="task", parent="feat_001")
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    assert dispatch_feature("feat_001", "human", root=root).ok
    feature_entry = get_integration_worktree(root, "feature", "feat_001")
    assert feature_entry is not None
    if remote_state == "prepublication":
        _git(
            feature_entry.path,
            "update-ref",
            "refs/remotes/origin/feat/feat_001",
            "feat/feat_001",
        )
    elif remote_state == "partial":
        checkpoint = feature_entry.path / "docs" / "_war_room" / "checkpoint.txt"
        checkpoint.parent.mkdir(parents=True, exist_ok=True)
        checkpoint.write_text("checkpoint\n", encoding="utf-8")
        _git(feature_entry.path, "add", str(checkpoint.relative_to(feature_entry.path)))
        _git(
            feature_entry.path,
            "commit",
            "-m",
            "partial publication",
            "-m",
            "Cascade-Task: task_001",
        )
        _git(
            feature_entry.path,
            "update-ref",
            "refs/remotes/origin/feat/feat_001",
            "feat/feat_001",
        )
    assert dispatch_task("task_001", "human", root=root).ok
    run = get_task_run("task_001")
    assert run is not None
    deliverable = run.worktree / "product.py"
    deliverable.write_text("VALUE = 1\n", encoding="utf-8")
    swe_commit("implement value", task_id="task_001", task_run=run, root=root)
    assert merge_task_branch("task_001", root=root).ok

    move_doc("feat_001", "completed", root=feature_entry.path)
    return root, feature_entry


def test_prepare_feature_publication_folds_history_to_one_commit_per_task(
    tmp_path: Path,
) -> None:
    root, feature_entry = _completed_feature(tmp_path)
    history = prepare_feature_publication("feat_001", root=root)

    assert history.task_ids == ("task_001",)
    assert len(history.commits) == 1
    assert (feature_entry.path / "product.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    feature = read_doc("feat_001", root=feature_entry.path)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    assert _git(feature_entry.path, "status", "--porcelain", "--untracked-files=no") == ""


def test_publication_reuses_integration_resolution_for_conflicting_task_patch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    worker = root / "worker.py"
    worker.write_text("STATE = 'base'\n", encoding="utf-8")
    _git(root, "add", "worker.py")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")

    _git(root, "checkout", "-b", "task-one", base)
    worker.write_text("STATE = 'one'\n", encoding="utf-8")
    _git(root, "commit", "-am", "task one", "-m", "Cascade-Task: task_001")
    first = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "-b", "feature", base)
    _git(root, "merge", "--no-ff", "task-one", "-m", "integrate one")

    _git(root, "checkout", "-b", "task-two", base)
    worker.write_text("STATE = 'two'\n", encoding="utf-8")
    (root / "second.py").write_text("SECOND = True\n", encoding="utf-8")
    _git(root, "add", "worker.py", "second.py")
    _git(root, "commit", "-m", "task two", "-m", "Cascade-Task: task_002")
    second = _git(root, "rev-parse", "HEAD")
    conflict = subprocess.run(
        ["git", "merge", "--no-ff", "feature", "-m", "resolve both"],
        cwd=root, capture_output=True, text=True,
    )
    assert conflict.returncode != 0
    worker.write_text("STATE = 'one and two'\n", encoding="utf-8")
    _git(root, "add", "worker.py")
    _git(root, "commit", "-m", "resolve both")
    _git(root, "checkout", "feature")
    _git(root, "merge", "--ff-only", "task-two")

    _git(root, "checkout", "-b", "task-three")
    (root / "third.py").write_text("THIRD = True\n", encoding="utf-8")
    _git(root, "add", "third.py")
    _git(root, "commit", "-m", "task three", "-m", "Cascade-Task: task_003")
    third = _git(root, "rev-parse", "HEAD")
    _git(root, "checkout", "feature")
    _git(root, "merge", "--ff-only", "task-three")
    final = _git(root, "rev-parse", "HEAD")
    monkeypatch.setattr(
        "cascade.feature.publication.read_doc",
        lambda task_id, *, root: SimpleNamespace(meta=SimpleNamespace(title=task_id)),
    )

    tip = _build_publication_tail(
        root, base_sha=base, final_tree_ref=final,
        task_ids=["task_001", "task_002", "task_003"],
        task_commits=[first, second, third],
    )
    history = validate_feature_publication(
        "feat_001", source_root=root, source_ref=tip, base_ref=base,
        expected_task_ids=["task_001", "task_002", "task_003"],
    )
    assert len(history.commits) == 3
    assert _git(root, "show", f"{history.commits[1]}:worker.py") == "STATE = 'one and two'"
    assert _git(root, "show", f"{history.commits[1]}:second.py") == "SECOND = True"
    assert _git(root, "rev-parse", f"{tip}^{{tree}}") == _git(root, "rev-parse", f"{final}^{{tree}}")


def test_review_force_pushes_normalized_history_with_exact_lease(
    tmp_path: Path, monkeypatch
) -> None:
    root, feature_entry = _completed_feature(tmp_path, remote_state="prepublication")
    remote_tip = _git(feature_entry.path, "rev-parse", "origin/feat/feat_001")
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", str(remote)], check=True, capture_output=True)
    _git(root, "remote", "add", "origin", str(remote))
    _git(
        feature_entry.path,
        "push",
        "origin",
        f"{remote_tip}:refs/heads/feat/feat_001",
    )
    monkeypatch.setattr("cascade.review.review_enabled", lambda _root: True)
    monkeypatch.setattr(
        "cascade.review.create_merge_request",
        lambda _root, **kwargs: MergeRequest(
            url="https://example.test/review/1",
            number="1",
            forge="github",
            source_branch=str(kwargs["source_branch"]),
            target_branch=str(kwargs["target_branch"]),
            draft=False,
        ),
    )

    mr = ensure_feature_review("feat_001", root=root)

    assert mr is not None
    published_tip = _git(feature_entry.path, "rev-parse", "feat/feat_001")
    assert _git(remote, "rev-parse", "refs/heads/feat/feat_001") == published_tip
    assert published_tip != remote_tip
    history = validate_feature_publication(
        "feat_001",
        source_root=feature_entry.path,
        source_ref=published_tip,
        base_ref=feature_entry.base_sha,
        expected_task_ids=["task_001"],
    )
    assert history.task_ids == ("task_001",)


def test_prepare_feature_publication_replaces_ancestor_prepublication_remote(
    tmp_path: Path,
) -> None:
    root, feature_entry = _completed_feature(tmp_path, remote_state="prepublication")

    history = prepare_feature_publication("feat_001", root=root)

    assert history.task_ids == ("task_001",)
    assert len(history.commits) == 1
    assert history.remote_lease_sha is not None
    assert (feature_entry.path / "product.py").read_text(encoding="utf-8") == "VALUE = 1\n"

    retried = prepare_feature_publication("feat_001", root=root)
    assert retried.tip_sha == history.tip_sha
    assert retried.remote_lease_sha == history.remote_lease_sha


def test_prepare_feature_publication_rejects_malformed_partial_remote(
    tmp_path: Path,
) -> None:
    root, _ = _completed_feature(tmp_path, remote_state="partial")

    with pytest.raises(GitError, match="needs exactly one Cascade-Task trailer"):
        prepare_feature_publication("feat_001", root=root)


def test_prepare_feature_publication_rejects_diverged_remote(tmp_path: Path) -> None:
    root, feature_entry = _completed_feature(tmp_path)
    tree = _git(feature_entry.path, "rev-parse", f"{feature_entry.base_sha}^{{tree}}")
    remote_tip = _git(
        feature_entry.path,
        "commit-tree",
        tree,
        "-p",
        feature_entry.base_sha,
        "-m",
        "remote checkpoint",
    )
    _git(
        feature_entry.path,
        "update-ref",
        "refs/remotes/origin/feat/feat_001",
        remote_tip,
    )

    with pytest.raises(GitError, match="has diverged"):
        prepare_feature_publication("feat_001", root=root)


def test_validate_feature_publication_rejects_lifecycle_only_commit(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    (root / "README.md").write_text("base\n", encoding="utf-8")
    _git(root, "add", "README.md")
    _git(root, "commit", "-m", "base")
    base = _git(root, "rev-parse", "HEAD")
    plan = root / "docs" / "tasks" / "3_completed" / "task_001_plan.md"
    plan.parent.mkdir(parents=True, exist_ok=True)
    plan.write_text("done\n", encoding="utf-8")
    _git(root, "add", str(plan.relative_to(root)))
    _git(root, "commit", "-m", "docs only", "-m", "Cascade-Task: task_001")

    with pytest.raises(GitError, match="lifecycle-only"):
        validate_feature_publication(
            "feat_001",
            source_root=root,
            source_ref="HEAD",
            base_ref=base,
            expected_task_ids=["task_001"],
        )
