"""Epic comment tools (feat_005)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.workspace.doc_root import read_doc_resolved
from cascade.comments import store as comment_store
from cascade.comments.store import CommentNotFound
from cascade.epic.guard import EpicToolDenied
from cascade.epic.registry import register_epic_tool


class EpicToolUnavailable(Exception):
    """Epic tool not implemented in the current feature tier."""

    status_code = 501


def reply_comment(
    comment_id: str,
    body: str,
    *,
    epic_id: str,
    root: Path,
    author: str = "epic_manager",
    doc_id: str | None = None,
) -> str:
    _require_active_epic(epic_id, root)
    target = _target_doc_id(epic_id, doc_id, root=root)
    try:
        rows = comment_store.read_comments(target, root=root)
    except comment_store.CommentStoreError as exc:
        raise EpicToolDenied(str(exc)) from exc
    if not any(row.id == comment_id for row in rows):
        raise CommentNotFound(comment_id)
    return comment_store.reply_comment(
        target,
        comment_id,
        body,
        author=author,
        root=root,
    )


def read_comment(
    comment_id: str, *, epic_id: str, root: Path, doc_id: str | None = None
) -> dict[str, object]:
    """Read the full text of a comment on this epic's plan."""

    _require_active_epic(epic_id, root)
    target = _target_doc_id(epic_id, doc_id, root=root)
    for row in comment_store.read_comments(target, root=root):
        if row.id == comment_id:
            return row.to_dict()
    raise CommentNotFound(comment_id)


def _target_doc_id(epic_id: str, doc_id: str | None, *, root: Path) -> str:
    if doc_id is None or doc_id == epic_id:
        return epic_id
    from cascade.workspace.integration_worktree import merged_board

    meta = merged_board(Path(root).resolve()).by_id.get(doc_id)
    if meta is None or meta.tier != "feature" or meta.parent != epic_id:
        raise EpicToolDenied(
            "epic tools can access only this epic and its feature threads"
        )
    return doc_id


def _require_active_epic(epic_id: str, root: Path) -> None:
    repo = Path(root).resolve()
    try:
        epic = read_doc_resolved(epic_id, root=repo)
    except NotFound:
        raise EpicToolDenied(f"unknown work id {epic_id}") from None
    if epic.meta.tier != "epic":
        raise EpicToolDenied(f"{epic_id} is not an epic")
    if epic.meta.status != "active":
        raise EpicToolDenied(f"epic {epic_id} is not active")


register_epic_tool("reply_comment", reply_comment)
register_epic_tool("read_comment", read_comment)
