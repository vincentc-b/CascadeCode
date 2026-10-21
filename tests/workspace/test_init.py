"""init_workspace and cascade init CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

from cascade.board.gitutil import has_git
from cascade.watchdog import read_providers_config
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend
from cascade.workspace import WorkspaceError, WorkspaceRoot, init_workspace
from tests.support import _WORKSPACE, make_git_repo

_COLUMNS = (
    "docs/epics/1_backlog",
    "docs/epics/2_active",
    "docs/epics/3_completed",
    "docs/features/1_backlog",
    "docs/features/2_active",
    "docs/features/3_completed",
    "docs/tasks/1_backlog",
    "docs/tasks/2_active",
    "docs/tasks/3_completed",
)

_TOOL_MODEL_MARKERS = (
    "claude-opus-5-5",
    "claude-sonnet-5-5",
    "composer-2.5",
)


def test_init_creates_board_columns_gitignore_and_toml(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    ws = init_workspace(root)

    assert isinstance(ws, WorkspaceRoot)
    assert ws.path == root.resolve()
    assert ws.trunk is None
    assert ws.board == root / "docs"
    assert ws.config == root / "cascade.toml"
    assert ws.runtime == root / ".cascade"

    for rel in _COLUMNS:
        assert (root / rel).is_dir()

    gitignore = (root / ".gitignore").read_text(encoding="utf-8")
    assert any(line.strip() == ".cascade/" for line in gitignore.splitlines())
    assert any(line.strip() == "docs/_queue/*.jsonl" for line in gitignore.splitlines())

    with (root / "cascade.toml").open("rb") as handle:
        data = tomllib.load(handle)
    assert data["task_parallelism"] == 4
    assert data["providers"]["default"] == "cursor"
    assert data["providers"]["cursor"]["epic"] == ""
    assert data["providers"]["claude"]["task"] == ""

    cfg = read_providers_config(root)
    assert cfg.default == "cursor"
    assert cfg.tables["cursor"].epic is None
    assert cfg.tables["claude"].task is None
    with pytest.raises(ModelConfigError):
        resolve_backend("swe", None, root=root)


def test_second_init_does_not_overwrite_cascade_toml(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    init_workspace(root)
    edited = "# operator\n\ntask_parallelism = 2\n\n[models]\nepic = \"mine\"\n"
    (root / "cascade.toml").write_text(edited, encoding="utf-8")

    init_workspace(root)
    assert (root / "cascade.toml").read_text(encoding="utf-8") == edited


def test_init_requires_git_repo(tmp_path: Path) -> None:
    root = tmp_path / "not_git"
    root.mkdir()
    with pytest.raises(WorkspaceError, match="not a git repository"):
        init_workspace(root)


def test_init_does_not_copy_tool_model_ids(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    assert root != _WORKSPACE
    init_workspace(root)
    text = (root / "cascade.toml").read_text(encoding="utf-8")
    for marker in _TOOL_MODEL_MARKERS:
        assert marker not in text


def test_cascade_init_cli_success_and_non_git_exit(tmp_path: Path) -> None:
    root = make_git_repo(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "cascade.cli", "init", "--root", str(root)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert has_git(root)
    assert (root / "docs" / "epics" / "1_backlog").is_dir()

    not_git = tmp_path / "plain"
    not_git.mkdir()
    bad = subprocess.run(
        [sys.executable, "-m", "cascade.cli", "init", "--root", str(not_git)],
        capture_output=True,
        text=True,
    )
    assert bad.returncode != 0
    assert "not a git repository" in bad.stderr
