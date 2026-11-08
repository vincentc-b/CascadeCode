"""Local git via subprocess. Commands are pinned to the given repo root."""

from __future__ import annotations

import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from contextlib import contextmanager, suppress
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.lock import process_lock


_git_io_budget: ContextVar[tuple[float, threading.Event | None] | None] = ContextVar(
    "git_io_budget", default=None
)
_git_new_session: ContextVar[bool] = ContextVar("git_new_session", default=True)


@contextmanager
def bounded_git_io(
    timeout: float, cancel_event: threading.Event | None = None
):
    """Apply one finite budget to all Git calls in the current call chain."""

    if timeout <= 0:
        raise subprocess.TimeoutExpired("git audit I/O", timeout)
    deadline = time.monotonic() + timeout
    current = _git_io_budget.get()
    if current is not None:
        deadline = min(deadline, current[0])
        cancel_event = cancel_event or current[1]
    token = _git_io_budget.set((deadline, cancel_event))
    try:
        yield
    finally:
        _git_io_budget.reset(token)


@contextmanager
def inherited_git_process_group():
    """Keep audit Git descendants in their killable observer process group.

    Ordinary callers continue to isolate each Git invocation in its own session.
    A bounded audit observer is itself a session leader, however, so retaining
    its group lets the coordinating parent reap helpers even if the observer is
    forcibly killed during cooperative Git cleanup.
    """

    token = _git_new_session.set(False)
    try:
        yield
    finally:
        _git_new_session.reset(token)


def _effective_io_limits(
    timeout: float | None, cancel_event: threading.Event | None
) -> tuple[float | None, threading.Event | None]:
    budget = _git_io_budget.get()
    if budget is None:
        return timeout, cancel_event
    remaining = budget[0] - time.monotonic()
    timeout = remaining if timeout is None else min(timeout, remaining)
    return timeout, cancel_event or budget[1]


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
    timeout: float | None = None,
    cancel_event: threading.Event | None = None,
) -> subprocess.CompletedProcess[str]:
    command = ["git", *args]
    timeout, cancel_event = _effective_io_limits(timeout, cancel_event)
    if timeout is None and cancel_event is None:
        result = subprocess.run(
            command,
            cwd=root,
            env=_env(root, index_file=index_file),
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    else:
        if timeout is not None and timeout <= 0:
            raise subprocess.TimeoutExpired(command, timeout)
        process = subprocess.Popen(
            command,
            cwd=root,
            env=_env(root, index_file=index_file),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            start_new_session=_git_new_session.get(),
        )
        started = time.monotonic()
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise InterruptedError(f"git {' '.join(args)} cancelled")
                remaining = (
                    None if timeout is None else timeout - (time.monotonic() - started)
                )
                if remaining is not None and remaining <= 0:
                    raise subprocess.TimeoutExpired(command, timeout)
                try:
                    stdout, stderr = process.communicate(
                        timeout=0.1 if remaining is None else min(0.1, remaining)
                    )
                    result = subprocess.CompletedProcess(
                        command, process.returncode, stdout, stderr
                    )
                    break
                except subprocess.TimeoutExpired:
                    continue
        except (InterruptedError, subprocess.TimeoutExpired):
            _stop_process_group(process, isolated=_git_new_session.get())
            raise
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitError(detail or f"git {' '.join(args)} failed")
    return result


def _stop_process_group(
    process: subprocess.Popen[str], *, isolated: bool = True
) -> None:
    """Best-effort finite cleanup that never masks the triggering exception.

    Git hooks and credential helpers may leave descendants holding captured
    stdout/stderr open after the Git parent exits.  Signal the whole session,
    bound both cleanup waits, and finally close our pipe handles so such a
    descendant cannot keep ``communicate`` blocked indefinitely.
    """

    def signal_group(sig: signal.Signals, fallback: str) -> None:
        if isolated:
            try:
                os.killpg(process.pid, sig)
                return
            except (AttributeError, ProcessLookupError, PermissionError, OSError):
                pass
        with suppress(AttributeError, ProcessLookupError, PermissionError, OSError):
            getattr(process, fallback)()

    signal_group(signal.SIGTERM, "terminate")
    try:
        process.communicate(timeout=0.25)
        return
    except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
        pass

    signal_group(signal.SIGKILL, "kill")
    try:
        process.communicate(timeout=0.25)
    except (subprocess.TimeoutExpired, ProcessLookupError, OSError):
        for pipe_name in ("stdout", "stderr", "stdin"):
            pipe = getattr(process, pipe_name, None)
            if pipe is not None:
                with suppress(OSError, ValueError):
                    pipe.close()
        with suppress(
            AttributeError,
            subprocess.TimeoutExpired,
            ProcessLookupError,
            OSError,
        ):
            process.wait(timeout=0.05)


def has_git(root: Path) -> bool:
    return (root / ".git").exists()


def head_sha(
    root: Path,
    *,
    timeout: float | None = None,
    cancel_event: threading.Event | None = None,
) -> str | None:
    if not has_git(root):
        return None
    result = _run(
        ["rev-parse", "--verify", "-q", "HEAD"],
        root,
        check=False,
        timeout=timeout,
        cancel_event=cancel_event,
    )
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
        # A column move that commits the new copy before deleting the old one leaves
        # both in one commit; the furthest-along column is the live doc.
        furthest = max(_column_rank(path) for path in matches)
        live = [path for path in matches if _column_rank(path) == furthest]
        if len(live) > 1:
            raise GitError(f"multiple paths for {work_id} at {rev}: {matches}")
        return live[0]
    return matches[0]


def _column_rank(rel: str) -> int:
    return ("1_backlog", "2_active", "3_completed").index(rel.split("/")[2])


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
        sha = _commit_paths(root, paths, message)
        _synchronize_tracking_commit(root)
        return sha


def _synchronize_tracking_commit(root: Path) -> None:
    """Push remote-backed planning commits after local persistence."""

    from cascade.board.context import get_project_context
    from cascade.workspace.repository_resolver import synchronize_tracking_repository

    project = get_project_context()
    if project is None or not project.tracking.synchronize_remote:
        return
    if root.resolve() != project.tracking.root.resolve():
        return
    synchronize_tracking_repository(project.tracking)


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
