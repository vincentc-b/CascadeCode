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

_GITIGNORE_LINES = (".cascade/", "docs/_queue/*.jsonl")


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

    _ensure_runtime_gitignore(path / ".gitignore")

    return WorkspaceRoot(
        path=path,
        trunk=None,
        board=path / "docs",
        config=config_path,
        runtime=path / ".cascade",
    )


def _ensure_runtime_gitignore(gitignore: Path) -> None:
    text = gitignore.read_text(encoding="utf-8") if gitignore.is_file() else ""
    present = {line.strip() for line in text.splitlines()}
    missing = [line for line in _GITIGNORE_LINES if line not in present]
    if not missing:
        return
    suffix = "" if text.endswith("\n") or not text else "\n"
    gitignore.write_text(f"{text}{suffix}" + "\n".join(missing) + "\n", encoding="utf-8")
