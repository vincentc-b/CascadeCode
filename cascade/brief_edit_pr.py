"""Stale-safe, isolated PR flow for editing backlog epic briefs."""

from __future__ import annotations

import subprocess
import tempfile
import threading
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from cascade.board.errors import GitError, NotFound, SchemaError
from cascade.board.parse import parse_text, render_doc
from cascade.board.store import read_doc
from cascade.board.types import WorkDoc
from cascade.brief_edit import (
    brief_edit_unchanged,
    load_brief_edit,
    render_brief_edit,
    validate_brief_edit,
)
from cascade.briefs import _fetch_remote_trunk
from cascade.tracking import MergeRequest, create_merge_request, forge_ready, push_branch
from cascade.watchdog.config import read_automation_config
from cascade.workspace.trunk import resolve_product_trunk


class BriefEditError(Exception):
    """An operator-actionable brief edit failure."""

    def __init__(self, message: str, *, code: str, status: int = 409, reload: bool = False):
        super().__init__(message)
        self.code = code
        self.status = status
        self.reload = reload


_in_flight: set[tuple[Path, str]] = set()
_in_flight_lock = threading.Lock()


def _request_id(raw: dict[str, object]) -> str:
    value = raw.get("epic_id") or raw.get("work_id") or raw.get("id")
    if not isinstance(value, str) or not value.strip():
        raise BriefEditError("missing epic_id", code="invalid_request", status=400)
    return value.strip()


def _source_path(raw: dict[str, object]) -> str:
    value = raw.get("source_path")
    if not isinstance(value, str) or not value.strip():
        raise BriefEditError("missing source_path", code="invalid_request", status=400)
    return value.strip().replace("\\", "/")


def get_editable_brief(root: Path, request_path: str) -> dict[str, object]:
    query = parse_qs(urlparse(request_path).query)
    epic_id = (query.get("epic_id") or query.get("work_id") or [""])[0].strip()
    if not epic_id:
        raise BriefEditError("missing epic_id", code="invalid_request", status=400)
    try:
        doc = read_doc(epic_id, root=Path(root).resolve())
    except NotFound as exc:
        raise BriefEditError(f"brief not found: {epic_id}", code="deleted", reload=True) from exc
    if doc.meta.tier != "epic" or doc.meta.status != "backlog" or doc.meta.path.parent.name != "1_backlog":
        raise BriefEditError(
            f"{epic_id} is no longer an editable backlog brief",
            code="not_in_backlog", reload=True,
        )
    repo = Path(root).resolve()
    try:
        trunk = resolve_product_trunk(repo)
        remote = read_automation_config(repo).remote
        base = _fetch_remote_trunk(repo, trunk, remote=remote)
        fetched = _fetched_brief(repo, base, epic_id)
    except (GitError, ValueError, OSError) as exc:
        raise BriefEditError(
            "could not load the approved brief; retry shortly",
            code="retryable", status=503,
        ) from exc
    if fetched is None:
        raise BriefEditError(f"brief not found: {epic_id}", code="deleted", reload=True)
    approved, source_path, source_revision = fetched
    if approved.meta.status != "backlog" or Path(source_path).parent.name != "1_backlog":
        raise BriefEditError(
            f"{epic_id} is no longer an editable backlog brief",
            code="not_in_backlog", reload=True,
        )
    payload = load_brief_edit(approved)
    payload.update({
        "epic_id": epic_id,
        "source_path": source_path,
        "source_revision": source_revision,
    })
    payload.pop("source", None)
    return payload


def _git(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8"
    )


def _fetched_brief(repo: Path, base: str, epic_id: str) -> tuple[WorkDoc, str, str] | None:
    """Find an epic in the fetched trunk and return its doc, path, and revision."""

    listing = _git(["ls-tree", "-r", "--name-only", base, "--", "docs/epics"], repo)
    if listing.returncode != 0:
        raise GitError((listing.stderr or listing.stdout).strip() or "could not inspect fetched trunk")
    for rel in listing.stdout.splitlines():
        if not rel.endswith(".md"):
            continue
        shown = _git(["show", f"{base}:{rel}"], repo)
        if shown.returncode != 0:
            raise GitError((shown.stderr or shown.stdout).strip() or f"could not read {rel}")
        doc = parse_text(shown.stdout, repo / rel)
        if doc.meta.id != epic_id:
            continue
        revision = _git(["log", "-1", "--format=%H", base, "--", rel], repo)
        if revision.returncode != 0 or not revision.stdout.strip():
            raise GitError(
                (revision.stderr or revision.stdout).strip()
                or f"could not resolve revision for {rel}"
            )
        doc.sha = revision.stdout.strip()
        return doc, rel, doc.sha
    return None


def submit_brief_edit(root: Path, raw: dict[str, object]) -> MergeRequest:
    repo = Path(root).resolve()
    epic_id = _request_id(raw)
    key = (repo, epic_id)
    with _in_flight_lock:
        if key in _in_flight:
            raise BriefEditError(
                "an edit for this brief is already being submitted; retry shortly",
                code="duplicate",
            )
        _in_flight.add(key)
    try:
        return _submit(repo, epic_id, raw)
    finally:
        with _in_flight_lock:
            _in_flight.discard(key)


def _submit(repo: Path, epic_id: str, raw: dict[str, object]) -> MergeRequest:
    source_path = _source_path(raw)
    trunk = resolve_product_trunk(repo)
    remote = read_automation_config(repo).remote
    base = _fetch_remote_trunk(repo, trunk, remote=remote)
    fetched = _fetched_brief(repo, base, epic_id)
    if fetched is None:
        raise BriefEditError(
            f"brief {epic_id} was deleted; reload it", code="deleted", reload=True
        )
    current, actual_path, revision = fetched
    if actual_path != source_path:
        raise BriefEditError("brief path changed; reload the brief", code="stale", reload=True)
    if (
        current.meta.tier != "epic"
        or current.meta.status != "backlog"
        or Path(actual_path).parent.name != "1_backlog"
    ):
        raise BriefEditError(
            f"{epic_id} is no longer in the backlog; reload the brief",
            code="not_in_backlog", reload=True,
        )
    if raw.get("source_revision") != revision:
        raise BriefEditError(
            "brief changed since it was loaded; reload it and reapply your edits",
            code="stale", reload=True,
        )
    try:
        edit = validate_brief_edit(raw, current, root=repo)
    except (ValueError, SchemaError) as exc:
        raise BriefEditError(str(exc), code="invalid", status=400) from exc
    if brief_edit_unchanged(edit):
        raise BriefEditError("no changes to submit", code="no_op", status=400)
    if not forge_ready(repo):
        raise BriefEditError(
            "review forge is not ready; fix authentication and retry",
            code="forge_unavailable", status=503,
        )

    branch = f"cascade/brief-edit/{epic_id}-{uuid.uuid4().hex[:8]}"
    with tempfile.TemporaryDirectory(prefix=f"cascade-{epic_id}-") as temp:
        worktree = Path(temp) / "worktree"
        add = _git(["worktree", "add", "-b", branch, str(worktree), base], repo)
        if add.returncode != 0:
            raise GitError((add.stderr or add.stdout).strip() or "brief edit worktree creation failed")
        try:
            target = worktree / source_path
            target.parent.mkdir(parents=True, exist_ok=True)
            changed = render_brief_edit(edit)
            changed.meta.path = target
            target.write_text(render_doc(changed), encoding="utf-8")
            commit = _git(["add", "--", source_path], worktree)
            if commit.returncode == 0:
                commit = _git([
                    "-c", "commit.gpgsign=false", "commit", "--only",
                    "-m", f"brief: edit {epic_id}", "--", source_path,
                ], worktree)
            if commit.returncode != 0:
                raise GitError((commit.stderr or commit.stdout).strip() or "brief edit commit failed")
            push_branch(worktree, branch, remote=remote)
            return create_merge_request(
                worktree,
                title=f"Brief: {changed.meta.title}",
                body=f"Updates {epic_id} at {source_path}. Merge to approve the edited backlog brief.",
                source_branch=branch,
                target_branch=trunk,
                remote=remote,
            )
        finally:
            _git(["worktree", "remove", "--force", str(worktree)], repo)
