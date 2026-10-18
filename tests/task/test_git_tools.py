"""swe_run_tests and swe_commit on task branch only (task_034)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.board.store import read_doc
from cascade.task.git_tools import register_task_git_tools, swe_commit, swe_run_tests
from cascade.task.guard import TaskToolDenied
from cascade.task.registry import clear_task_tools, task_tools
from cascade.task.worktree import clear_task_runs, create_task_worktree
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _git_tools_isolation() -> None:
    clear_task_runs()
    clear_task_tools()
    yield
    clear_task_runs()
    clear_task_tools()


def _initial_commit(root: Path) -> str:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return sha.stdout.strip()


@pytest.fixture
def board(tmp_path: Path):
    root = make_repo(tmp_path)
    _initial_commit(root)
    add_doc(
        root,
        id="epic_001",
        title="Epic",
        tier="epic",
        status="active",
    )
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_034",
        title="Git tools task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    run = create_task_worktree(
        "task_034",
        root=root,
        parent_rev=read_doc("task_034", root=root).meta.parent_rev,
        skills=[],
    )
    return {"root": root, "run": run}


def test_swe_run_tests_rejects_git_or_push_in_cmd(board) -> None:
    run = board["run"]
    root = board["root"]
    with pytest.raises(TaskToolDenied, match="forbidden"):
        swe_run_tests(
            task_id="task_034",
            task_run=run,
            root=root,
            cmd=["git", "status"],
        )
    with pytest.raises(TaskToolDenied, match="forbidden"):
        swe_run_tests(
            task_id="task_034",
            task_run=run,
            root=root,
            cmd=["python3", "-m", "pytest", "-q", "push"],
        )


def test_swe_commit_happy_path_on_task_branch(board) -> None:
    root = board["root"]
    run = board["run"]
    wt = run.worktree
    patch = wt / "cascade" / "patch.py"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("value = 1\n", encoding="utf-8")

    sha = swe_commit("task work", task_id="task_034", task_run=run, root=root)

    assert len(sha) == 40
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert head == sha
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=wt,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert branch == "task/task_034"
    assert patch.read_text(encoding="utf-8") == "value = 1\n"


def test_swe_commit_refused_wrong_branch(board) -> None:
    root = board["root"]
    run = board["run"]
    wt = run.worktree
    subprocess.run(["git", "checkout", "-b", "wrong-branch"], cwd=wt, check=True, capture_output=True)
    (wt / "note.txt").write_text("x\n", encoding="utf-8")

    with pytest.raises(TaskToolDenied, match="commit refused"):
        swe_commit("nope", task_id="task_034", task_run=run, root=root)


def test_swe_commit_refused_epic_path(board) -> None:
    root = board["root"]
    run = board["run"]
    wt = run.worktree
    epic = read_doc("epic_001", root=root)
    rel = epic.meta.path.relative_to(root)
    target = wt / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# hacked\n", encoding="utf-8")

    with pytest.raises(TaskToolDenied, match="commit refused"):
        swe_commit("bad epic", task_id="task_034", task_run=run, root=root)


def test_swe_commit_refused_feature_path(board) -> None:
    root = board["root"]
    run = board["run"]
    wt = run.worktree
    feature = read_doc("feat_001", root=root)
    rel = feature.meta.path.relative_to(root)
    target = wt / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# hacked\n", encoding="utf-8")

    with pytest.raises(TaskToolDenied, match="commit refused"):
        swe_commit("bad feature", task_id="task_034", task_run=run, root=root)


def test_swe_run_tests_uses_worktree_cwd(board, monkeypatch: pytest.MonkeyPatch) -> None:
    import cascade.task.git_tools as git_tools_mod

    run = board["run"]
    wt = run.worktree.resolve()
    seen: list[Path | None] = []
    real_run = subprocess.run

    def capture_run(
        args: list[str] | tuple[str, ...],
        *a: object,
        **kw: object,
    ) -> subprocess.CompletedProcess[str]:
        seen.append(kw.get("cwd"))  # type: ignore[arg-type]
        return real_run(args, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(git_tools_mod.subprocess, "run", capture_run)

    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    result = swe_run_tests(
        task_id="task_034",
        task_run=run,
        root=board["root"],
        cmd=["python3", "-m", "pytest", "-q", "test_ok.py"],
    )

    assert seen == [wt]
    assert result["exit_code"] == 0
    assert "passed" in str(result["output"])


def test_no_git_push(monkeypatch: pytest.MonkeyPatch, board) -> None:
    import cascade.task.git_tools as git_tools_mod

    pushes: list[list[str]] = []
    real_run = subprocess.run

    def guarded_run(
        args: list[str] | tuple[str, ...],
        *a: object,
        **kw: object,
    ) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "git" and "push" in args:
            pushes.append(list(args))
        return real_run(args, *a, **kw)  # type: ignore[arg-type]

    monkeypatch.setattr(git_tools_mod.subprocess, "run", guarded_run)

    wt = board["run"].worktree
    patch = wt / "cascade" / "demo.py"
    patch.parent.mkdir(parents=True, exist_ok=True)
    patch.write_text("x = 1\n", encoding="utf-8")
    swe_commit("local only", task_id="task_034", task_run=board["run"], root=board["root"])
    (wt / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    swe_run_tests(
        task_id="task_034",
        task_run=board["run"],
        root=board["root"],
        cmd=["python3", "-m", "pytest", "-q", "test_ok.py"],
    )

    assert pushes == []


def test_register_task_git_tools_idempotent() -> None:
    register_task_git_tools()
    names = task_tools()
    assert "swe_run_tests" in names
    assert "swe_commit" in names
    register_task_git_tools()
    assert len([n for n in task_tools() if n.startswith("swe_")]) == 2
