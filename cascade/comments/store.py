"""Append/read comment sidecars at docs/_comments/{doc_id}.jsonl."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.errors import NotFound
from cascade.workspace.doc_root import resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk, merged_board
from cascade.comments.types import AGENT_AUTHORS, Comment
from cascade.watchdog import append_event
from cascade.watchdog.lock import process_lock
from cascade.watchdog.types import Event

_COMMENT_ID_RE = re.compile(r"^cmt_(\d+)$")
_SIDECAR_DIR = Path("docs") / "_comments"


class CommentStoreError(Exception):
    """Invalid comment operation."""


class BlockingNotAllowed(CommentStoreError):
    """Only the human may set blocking=true on create."""


class CommentNotFound(CommentStoreError):
    """No comment with this id in the doc sidecar."""


class ResolveNotAllowed(CommentStoreError):
    """Only the human may resolve a thread."""


class NotARoot(CommentStoreError):
    """Resolve applies to open root comments only."""


def comment(
    doc_id: str,
    section: str,
    body: str,
    anchor: str | None = None,
    blocking: bool = False,
    *,
    line_start: int | None = None,
    line_end: int | None = None,
    doc_sha: str | None = None,
    blocks: list[str] | None = None,
    author: str,
    root: Path,
    is_attached: Callable[[str], bool] | None = None,
) -> str:
    """Append a root comment and notify the owning graph."""

    if blocking and author != "human":
        raise BlockingNotAllowed("blocking=true is allowed only when author=human")
    if author in AGENT_AUTHORS and blocking:
        raise BlockingNotAllowed("agents cannot set blocking=true")

    trunk = locate_trunk(resolve_root(root))
    repo = _comment_repo(doc_id, root=root)
    owning = _owning_graph(doc_id, trunk)
    text = body.strip()
    if not text:
        raise CommentStoreError("empty body")
    if not section.strip():
        raise CommentStoreError("empty section")

    record = _append_comment(
        doc_id=doc_id,
        section=section.strip(),
        anchor=anchor,
        line_start=line_start,
        line_end=line_end,
        doc_sha=doc_sha,
        blocks=tuple(blocks) if blocks else (),
        author=author,
        body=text,
        parent=None,
        blocking=blocking,
        root=repo,
    )
    _emit_comment_posted(record, owning, trunk=trunk)
    if author == "human" and is_attached is not None and not is_attached(owning):
        _enqueue_comment_toast(doc_id, trunk)
    return record.id


def reply_comment(
    doc_id: str,
    comment_id: str,
    body: str,
    *,
    author: str,
    root: Path,
) -> str:
    """Reply in-thread; new line stays open with parent set."""

    trunk = locate_trunk(resolve_root(root))
    repo = _comment_repo(doc_id, root=root)
    parent = _require_comment(doc_id, comment_id, root=repo)
    text = body.strip()
    if not text:
        raise CommentStoreError("empty body")
    owning = _owning_graph(doc_id, trunk)
    record = _append_comment(
        doc_id=doc_id,
        section=parent.section,
        anchor=parent.anchor,
        author=author,
        body=text,
        parent=comment_id,
        blocking=False,
        root=repo,
    )
    append_event(
        owning,
        Event(
            type="CommentReplied",
            ts=datetime.now(timezone.utc),
            payload={
                "doc_id": doc_id,
                "comment_id": record.id,
                "author": author,
            },
            dest=owning,
        ),
        root=repo,
    )
    return record.id


def resolve_comment(
    doc_id: str,
    comment_id: str,
    *,
    author: str,
    root: Path,
    resolution: str = "resolved",
) -> None:
    """Mark a root thread resolved; cascade to all descendants."""

    if author != "human":
        raise ResolveNotAllowed("resolve is allowed only when author=human")

    trunk = locate_trunk(resolve_root(root))
    repo = _comment_repo(doc_id, root=root)
    owning = _owning_graph(doc_id, trunk)
    changed = False

    def mutate(comments: list[Comment]) -> None:
        nonlocal changed
        root_row: Comment | None = None
        for row in comments:
            if row.id == comment_id:
                root_row = row
                break
        if root_row is None:
            raise CommentNotFound(comment_id)
        if root_row.parent is not None:
            raise NotARoot(comment_id)

        targets = _thread_ids(comments, comment_id)
        for index, row in enumerate(comments):
            if row.id not in targets or row.state == "resolved":
                continue
            comments[index] = Comment(
                id=row.id,
                doc_id=row.doc_id,
                section=row.section,
                anchor=row.anchor,
                line_start=row.line_start,
                line_end=row.line_end,
                doc_sha=row.doc_sha,
                blocks=row.blocks,
                author=row.author,
                body=row.body,
                parent=row.parent,
                state="resolved",
                blocking=row.blocking,
                created=row.created,
            )
            changed = True

    _update_sidecar(doc_id, mutate, root=repo)
    if not changed:
        return
    append_event(
        owning,
        Event(
            type="CommentResolved",
            ts=datetime.now(timezone.utc),
            payload={
                "doc_id": doc_id,
                "comment_id": comment_id,
                "resolution": resolution,
            },
            dest=owning,
        ),
        root=trunk,
    )


def read_comments(doc_id: str, *, root: Path) -> list[Comment]:
    repo = _comment_repo(doc_id, root=root)
    return _load_sidecar(doc_id, repo)


def sidecar_path(doc_id: str, *, root: Path) -> Path:
    repo = _comment_repo(doc_id, root=root)
    return _sidecar_path(repo, doc_id)


def _comment_repo(doc_id: str, *, root: Path) -> Path:
    trunk = locate_trunk(resolve_root(root))
    try:
        return resolve_doc_worktree(doc_id, root=trunk)
    except NotFound:
        return trunk


def _owning_graph(doc_id: str, trunk: Path) -> str:
    from cascade.workspace.doc_root import read_doc_resolved

    try:
        doc = read_doc_resolved(doc_id, root=trunk)
    except NotFound as exc:
        raise CommentStoreError(f"unknown work id {doc_id}") from exc
    if doc.meta.tier not in ("feature", "epic"):
        raise CommentStoreError(f"comments not supported for tier {doc.meta.tier}")
    return doc_id


def _append_comment(
    *,
    doc_id: str,
    section: str,
    anchor: str | None,
    line_start: int | None = None,
    line_end: int | None = None,
    doc_sha: str | None = None,
    blocks: tuple[str, ...] = (),
    author: str,
    body: str,
    parent: str | None,
    blocking: bool,
    root: Path,
) -> Comment:
    comment_id = _allocate_id(doc_id, root=root)
    record = Comment(
        id=comment_id,
        doc_id=doc_id,
        section=section,
        anchor=anchor,
        line_start=line_start,
        line_end=line_end,
        doc_sha=doc_sha,
        blocks=blocks,
        author=author,
        body=body,
        parent=parent,
        state="open",
        blocking=blocking,
        created=datetime.now(timezone.utc),
    )
    line = (json.dumps(record.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )
    path = _sidecar_path(root, doc_id)
    with process_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as handle:
            handle.write(line)
    return record


def _update_sidecar(
    doc_id: str,
    mutate: Callable[[list[Comment]], None],
    *,
    root: Path,
) -> None:
    path = _sidecar_path(root, doc_id)
    with process_lock:
        comments = _load_sidecar_unlocked(doc_id, root)
        mutate(comments)
        path.parent.mkdir(parents=True, exist_ok=True)
        encoded = b"".join(
            (json.dumps(c.to_dict(), ensure_ascii=False, separators=(",", ":")) + "\n").encode(
                "utf-8"
            )
            for c in comments
        )
        path.write_bytes(encoded)


def _load_sidecar(doc_id: str, root: Path) -> list[Comment]:
    with process_lock:
        return _load_sidecar_unlocked(doc_id, root)


def _load_sidecar_unlocked(doc_id: str, root: Path) -> list[Comment]:
    path = _sidecar_path(root, doc_id)
    if not path.is_file():
        return []
    comments: list[Comment] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
            if isinstance(raw, dict):
                comments.append(Comment.from_dict(raw))
        except (ValueError, TypeError, json.JSONDecodeError):
            continue
    return comments


def _thread_ids(comments: list[Comment], root_id: str) -> set[str]:
    by_parent: dict[str | None, list[str]] = {}
    for row in comments:
        by_parent.setdefault(row.parent, []).append(row.id)
    targets = {root_id}
    queue = [root_id]
    while queue:
        parent_id = queue.pop()
        for child_id in by_parent.get(parent_id, []):
            if child_id not in targets:
                targets.add(child_id)
                queue.append(child_id)
    return targets


def _require_comment(doc_id: str, comment_id: str, *, root: Path) -> Comment:
    for row in _load_sidecar(doc_id, root):
        if row.id == comment_id:
            return row
    raise CommentNotFound(comment_id)


def _allocate_id(doc_id: str, *, root: Path) -> str:
    highest = 0
    for row in _load_sidecar(doc_id, root):
        match = _COMMENT_ID_RE.match(row.id)
        if match:
            highest = max(highest, int(match.group(1)))
    return f"cmt_{highest + 1:03d}"


def _sidecar_path(root: Path, doc_id: str) -> Path:
    if not _valid_doc_id(doc_id):
        raise ValueError(f"invalid doc_id: {doc_id!r}")
    return root / _SIDECAR_DIR / f"{doc_id}.jsonl"


def _valid_doc_id(doc_id: str) -> bool:
    if not doc_id or doc_id in {".", ".."}:
        return False
    if any(sep in doc_id for sep in ("/", "\\", "\x00")):
        return False
    return Path(doc_id).name == doc_id


def _emit_comment_posted(record: Comment, owning: str, *, trunk: Path) -> None:
    """Queue on the product trunk so the supervisor watchdog ingests one graph."""

    append_event(
        owning,
        Event(
            type="CommentPosted",
            ts=datetime.now(timezone.utc),
            payload={
                "doc_id": record.doc_id,
                "section": record.section,
                "comment_id": record.id,
                "author": record.author,
            },
            dest=owning,
        ),
        root=trunk,
    )


def _enqueue_comment_toast(doc_id: str, repo: Path) -> None:
    append_event(
        "war_room",
        Event(
            type="Toast",
            ts=datetime.now(timezone.utc),
            payload={
                "kind": "comment",
                "id": doc_id,
                "message": f"New comment on {doc_id}",
                "body": f"New comment on {doc_id}",
            },
            dest="war_room",
        ),
        root=repo,
    )


def work_tier(doc_id: str, *, root: Path) -> str:
    """Return board tier for doc_id or raise CommentStoreError."""

    trunk = locate_trunk(resolve_root(root))
    board = merged_board(trunk)
    meta = board.by_id.get(doc_id)
    if meta is None:
        raise CommentStoreError(f"unknown work id {doc_id}")
    return meta.tier
