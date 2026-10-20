"""Scaffold a Cascade board in a git workspace without starting agents."""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.gitutil import has_git
from cascade.workspace.errors import WorkspaceError
from cascade.workspace.types import WorkspaceRoot

_BOARD_TIERS = ("epics", "features", "tasks")
_BOARD_COLUMNS = ("1_backlog", "2_active", "3_completed")

_DEFAULT_CASCADE_TOML = """\
# Workspace supervisor config.

task_parallelism = 4

[automation]
enabled = true
poll_seconds = 15
remote = "origin"

[providers]
default = "cursor"

[providers.cursor]
epic = ""
feature = ""
task = ""

[providers.claude]
epic = ""
feature = ""
task = ""

[providers.codex]
epic = ""
feature = ""
task = ""
"""

_GITIGNORE_LINE = ".cascade/"


def init_workspace(root: Path) -> WorkspaceRoot:
    """Create board columns and optional config in a git repo; idempotent."""

    path = resolve_root(root)
    if not has_git(path):
        raise WorkspaceError(f"not a git repository: {path}")

    for tier in _BOARD_TIERS:
        for column in _BOARD_COLUMNS:
            (path / "docs" / tier / column).mkdir(parents=True, exist_ok=True)

    config_path = path / "cascade.toml"
    if not config_path.is_file():
        config_path.write_text(_DEFAULT_CASCADE_TOML, encoding="utf-8")

    _ensure_gitignore_cascade(path / ".gitignore")

    return WorkspaceRoot(
        path=path,
        trunk=None,
        board=path / "docs",
        config=config_path,
        runtime=path / ".cascade",
    )


def _ensure_gitignore_cascade(gitignore: Path) -> None:
    if gitignore.is_file():
        text = gitignore.read_text(encoding="utf-8")
        for line in text.splitlines():
            if line.strip() == _GITIGNORE_LINE:
                return
        suffix = "" if text.endswith("\n") or not text else "\n"
        gitignore.write_text(f"{text}{suffix}{_GITIGNORE_LINE}\n", encoding="utf-8")
    else:
        gitignore.write_text(f"{_GITIGNORE_LINE}\n", encoding="utf-8")
