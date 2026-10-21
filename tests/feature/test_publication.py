from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.errors import GitError
from cascade.board.store import move_doc, read_doc
from cascade.boss.merge import merge_task_branch
from cascade.feature.publication import prepare_feature_publication, validate_feature_publication
from cascade.task.git_tools import swe_commit
from cascade.task.worktree import clear_task_runs, get_task_run
from cascade.watchdog import activate_epic, dispatch_feature, dispatch_task
from cascade.workspace.integration_worktree import get_integration_worktree
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


def test_prepare_feature_publication_folds_history_to_one_commit_per_task(
    tmp_path: Path,
) -> None:
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
    assert dispatch_task("task_001", "human", root=root).ok
    run = get_task_run("task_001")
    assert run is not None
    deliverable = run.worktree / "product.py"
    deliverable.write_text("VALUE = 1\n", encoding="utf-8")
    swe_commit("implement value", task_id="task_001", task_run=run, root=root)
    assert merge_task_branch("task_001", root=root).ok

    feature_entry = get_integration_worktree(root, "feature", "feat_001")
    assert feature_entry is not None
    move_doc("feat_001", "completed", root=feature_entry.path)
    history = prepare_feature_publication("feat_001", root=root)

    assert history.task_ids == ("task_001",)
    assert len(history.commits) == 1
    assert (feature_entry.path / "product.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    feature = read_doc("feat_001", root=feature_entry.path)
    assert feature.meta.status == "completed"
    assert feature.meta.path.parent.name == "3_completed"
    assert _git(feature_entry.path, "status", "--porcelain", "--untracked-files=no") == ""


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
