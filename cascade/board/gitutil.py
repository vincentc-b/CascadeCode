"""Local git via subprocess. Commands are pinned to the given repo root."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.lock import process_lock


def _env(root: Path, *, index_file: str | None = None) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("GIT_INDEX_FILE", None)
    env["GIT_DIR"] = str((root / ".git").resolve())
    env["GIT_WORK_TREE"] = str(root.resolve())
    if index_file is not None:
        env["GIT_INDEX_FILE"] = index_file
    return env


def _run(
    args: list[str],
    root: Path,
    *,
    index_file: str | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        env=_env(root, index_file=index_file),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} failed")
    return result


def has_git(root: Path) -> bool:
    return (root / ".git").exists()


def head_sha(root: Path) -> str | None:
    if not has_git(root):
        return None
    result = _run(["rev-parse", "--verify", "-q", "HEAD"], root, check=False)
    if result.returncode != 0:
        return None
    sha = result.stdout.strip()
    return sha or None


def last_commit_touching(root: Path, rel: Path) -> str | None:
    """SHA of the last commit that touched `rel`, or None if history has no such commit."""

    if head_sha(root) is None:
        return None
    result = _run(["log", "-1", "--format=%H", "--", rel.as_posix()], root, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or "git log failed")
    sha = result.stdout.strip()
    return sha or None


def read_blob(root: Path, rev: str, rel: str) -> str:
    result = _run(["show", f"{rev}:{rel}"], root, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git show {rev}:{rel} failed")
    return result.stdout


def path_for_work_id(root: Path, rev: str, work_id: str) -> str | None:
    """Return `docs/**/{id}_*.md` as stored in `rev`, not the working tree."""

    result = _run(["ls-tree", "-r", "--name-only", rev], root, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git ls-tree {rev} failed")
    pattern = re.compile(
        rf"^docs/(?:epics|features|tasks)/(?:1_backlog|2_active|3_completed)/"
        rf"{re.escape(work_id)}_[^/]+\.md$"
    )
    matches = [line for line in result.stdout.splitlines() if pattern.fullmatch(line)]
    if not matches:
        return None
    if len(matches) > 1:
        raise GitError(f"multiple paths for {work_id} at {rev}: {matches}")
    return matches[0]


def introduced_at(root: Path, rel: Path) -> datetime | None:
    """Committer time of the newest commit that added or renamed `rel` into place."""

    if head_sha(root) is None:
        return None
    result = _run(
        ["log", "-1", "--diff-filter=AR", "--format=%cI", "--", rel.as_posix()],
        root,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or "git log failed")
    stamp = result.stdout.strip()
    if not stamp:
        return None
    parsed = datetime.fromisoformat(stamp)
    if parsed.tzinfo is None:
        raise GitError(f"committer time is not timezone-aware: {stamp}")
    return parsed


def commit_paths(root: Path, paths: list[Path], message: str) -> str | None:
    """Commit only `paths`.

    Returns the new HEAD sha. Returns None when `root` is not a git repo.
    A separate index is used so staged and untracked files outside `paths`
    stay out of the commit and remain in the real index.
    """

    if not has_git(root):
        return None
    with process_lock:
        return _commit_paths(root, paths, message)


def _commit_paths(root: Path, paths: list[Path], message: str) -> str | None:
    root = root.resolve()
    rels: list[str] = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise GitError(f"path is outside the repo: {path}") from exc
        if rel not in rels:
            rels.append(rel)

    with tempfile.TemporaryDirectory(prefix="cascade-index-") as tmp:
        index_file = str(Path(tmp) / "index")
        if head_sha(root) is not None:
            _run(["read-tree", "HEAD"], root, index_file=index_file)
        for rel in rels:
            if (root / rel).exists():
                _run(["add", "--", rel], root, index_file=index_file)
            else:
                _stage_deletion(root, rel, index_file)
        commit = _run(
            ["-c", "commit.gpgsign=false", "commit", "-m", message],
            root,
            index_file=index_file,
            check=False,
        )
        if commit.returncode != 0:
            combined = f"{commit.stdout or ''}{commit.stderr or ''}"
            if "nothing to commit" in combined or "nothing added to commit" in combined:
                return head_sha(root)
            raise GitError(combined.strip() or "git commit failed")

    for rel in rels:
        if (root / rel).exists():
            _run(["add", "--", rel], root)
        else:
            _stage_deletion(root, rel, None)
    return head_sha(root)


def _stage_deletion(root: Path, rel: str, index_file: str | None) -> None:
    result = _run(["add", "-u", "--", rel], root, index_file=index_file, check=False)
    if result.returncode == 0:
        return
    combined = f"{result.stdout or ''}{result.stderr or ''}"
    if "did not match any file" in combined:
        return
    raise GitError(combined.strip() or f"failed to stage deletion of {rel}")
