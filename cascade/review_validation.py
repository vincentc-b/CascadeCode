"""Bounded repository checks for review publication, without shell evaluation."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import tempfile
import tomllib


def review_validation_timeout(root: Path) -> float:
    path = root / 'cascade.toml'
    config = tomllib.loads(path.read_text()) if path.exists() else {}
    value = config.get('validation', {}).get('review_timeout_seconds', 300)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not 1 <= value <= 3600:
        raise ValueError('validation.review_timeout_seconds must be between 1 and 3600')
    return float(value)


def run_review_validation(command: tuple[str, ...], *, cwd: Path, timeout: float) -> subprocess.CompletedProcess:
    # Files avoid unbounded in-memory capture; report only bounded diagnostic tails.
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except BaseException:
            # Kill the whole check group, including children that outlive the
            # initial command. Never leave validators mutating a preserved checkout.
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        def tail(handle):
            handle.seek(max(0, handle.tell() - 65536))
            return handle.read(65536).decode('utf-8', errors='replace')
        return subprocess.CompletedProcess(command, process.returncode, tail(stdout), tail(stderr))


def validate_publication_board(worktree: Path) -> None:
    """Validate physical documents being published, without split-root redirection.

    Normal board scans intentionally skip malformed drafts; publication must
    reject those and duplicate IDs rather than hide them from the live board.
    """
    from cascade.board.parse import parse_doc
    from cascade.board.errors import SchemaError
    seen = {}
    for tier in ('epics', 'features', 'tasks'):
        for column in ('1_backlog', '2_active', '3_completed', '4_cancelled'):
            for path in sorted((worktree / 'docs' / tier / column).glob('*.md')):
                if path.is_symlink():
                    raise SchemaError(f'publication board symlink: {path}')
                doc = parse_doc(path)
                if doc.meta.id in seen:
                    raise SchemaError(f'duplicate id {doc.meta.id} at {path} and {seen[doc.meta.id]}')
                seen[doc.meta.id] = path
