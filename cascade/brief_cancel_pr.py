"""Review-backed cancellation for approved backlog epic briefs."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

from cascade.board.errors import GitError
from cascade.board.parse import render_doc
from cascade.brief_edit_pr import BriefEditError, _fetched_brief, _request_id, _source_path
from cascade.briefs import _fetch_remote_trunk
from cascade.tracking import MergeRequest, create_merge_request, forge_ready, push_branch
from cascade.watchdog.config import read_automation_config
from cascade.workspace.trunk import resolve_product_trunk

_in_flight: set[tuple[Path, str]] = set()
_lock = threading.Lock()


def _git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8"
    )


def submit_brief_cancel(root: Path, raw: dict[str, object]) -> MergeRequest:
    """Open a PR that cancels one still-approved backlog epic."""

    repo = Path(root).resolve()
    epic_id = _request_id(raw)
    reason = raw.get("reason")
    reason = reason.strip() if isinstance(reason, str) else ""
    if not reason:
        raise BriefEditError("cancellation reason must not be blank", code="reason_required", status=400)
    source_path = _source_path(raw)
    key = (repo, epic_id)
    with _lock:
        if key in _in_flight:
            raise BriefEditError("cancellation is already being submitted", code="duplicate")
        _in_flight.add(key)
    try:
        return _submit(repo, epic_id, source_path, raw.get("source_revision"), reason)
    finally:
        with _lock:
            _in_flight.discard(key)


def _submit(
    repo: Path, epic_id: str, source_path: str, source_revision: object, reason: str
) -> MergeRequest:
    trunk = resolve_product_trunk(repo)
    remote = read_automation_config(repo).remote
    base = _fetch_remote_trunk(repo, trunk, remote=remote)
    fetched = _fetched_brief(repo, base, epic_id)
    if fetched is None:
        raise BriefEditError(f"brief {epic_id} was deleted; reload", code="deleted", reload=True)
    current, actual_path, revision = fetched
    if actual_path != source_path or source_revision != revision:
        raise BriefEditError("brief changed; reload before cancelling", code="stale", reload=True)
    if current.meta.tier != "epic" or current.meta.status != "backlog" or Path(actual_path).parent.name != "1_backlog":
        raise BriefEditError(f"{epic_id} is no longer in the backlog", code="not_in_backlog", reload=True)
    if current.meta.children:
        raise BriefEditError("cancel child work items first", code="live_children")
    if not forge_ready(repo):
        raise BriefEditError("review forge is not ready", code="forge_unavailable", status=503)

    branch = f"cascade/brief-cancel/{epic_id}-{uuid.uuid4().hex[:8]}"
    target_path = str(Path("docs/epics/3_completed") / Path(actual_path).name)
    with tempfile.TemporaryDirectory(prefix=f"cascade-{epic_id}-cancel-") as temp:
        worktree = Path(temp) / "worktree"
        added = _git(["worktree", "add", "-b", branch, str(worktree), base], repo)
        if added.returncode != 0:
            raise GitError((added.stderr or added.stdout).strip() or "cancel worktree creation failed")
        try:
            current.meta.status = "cancelled"
            current.meta.cancellation_reason = reason
            current.meta.cancelled_at = datetime.now(timezone.utc)
            current.meta.cancellation_step = "complete"
            current.meta.cancellation_error = None
            current.meta.updated = date.today()
            current.meta.path = worktree / target_path
            target = current.meta.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render_doc(current), encoding="utf-8")
            (worktree / actual_path).unlink()
            staged = _git(["add", "--", actual_path, target_path], worktree)
            if staged.returncode != 0:
                raise GitError((staged.stderr or staged.stdout).strip() or "cancel staging failed")
            committed = _git(
                ["-c", "commit.gpgsign=false", "commit", "-m", f"brief: cancel {epic_id}"], worktree
            )
            if committed.returncode != 0:
                raise GitError((committed.stderr or committed.stdout).strip() or "cancel commit failed")
            push_branch(worktree, branch, remote=remote)
            return create_merge_request(
                worktree,
                title=f"Cancel brief: {current.meta.title}",
                body=f"Cancels backlog epic `{epic_id}`. Reason: {reason}",
                source_branch=branch,
                target_branch=trunk,
                remote=remote,
            )
        finally:
            _git(["worktree", "remove", "--force", str(worktree)], repo)
