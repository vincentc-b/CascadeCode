"""Remove stale ``index.lock`` files after worker exit (stdlib-only, epic dec_007)."""

from __future__ import annotations

import sys
from pathlib import Path

_INDEX_LOCK = "index.lock"
_WORKTREES_DIR = Path(".cascade") / "worktrees"


def _read_gitdir(dot_git: Path) -> Path | None:
    if not dot_git.is_file():
        return None
    try:
        text = dot_git.read_text(encoding="utf-8")
    except OSError:
        return None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("gitdir:"):
            return Path(stripped.removeprefix("gitdir:").strip())
    return None


def _index_lock_candidates(checkout: Path) -> list[Path]:
    dot_git = checkout / ".git"
    candidates: list[Path] = []
    if dot_git.is_dir():
        candidates.append(dot_git / _INDEX_LOCK)
    gitdir = _read_gitdir(dot_git)
    if gitdir is not None:
        candidates.append(gitdir / _INDEX_LOCK)
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def _remove_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        print(
            f"cascade launcher: failed to remove stale git lock {lock_path}: {exc}",
            file=sys.stderr,
        )
        return
    print(f"cascade launcher: removed stale git lock {lock_path}", file=sys.stderr)


def sweep_stale_git_locks(repo_root: Path) -> None:
    """Drop stale ``index.lock`` in Cascade worktrees; warn on product trunk only."""

    root = repo_root.resolve()
    trunk_lock = root / ".git" / _INDEX_LOCK
    if trunk_lock.is_file():
        print(
            f"cascade launcher: warning: product trunk has {_INDEX_LOCK} at {trunk_lock}",
            file=sys.stderr,
        )

    worktrees_root = root / _WORKTREES_DIR
    if not worktrees_root.is_dir():
        return

    for entry in sorted(worktrees_root.iterdir()):
        if not entry.is_dir():
            continue
        for lock_path in _index_lock_candidates(entry):
            if lock_path.is_file():
                _remove_lock(lock_path)
