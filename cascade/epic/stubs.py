"""Epic comment tools (feat_005)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
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
) -> None:
    _require_active_epic(epic_id, root)
    doc_id = epic_id
    try:
        rows = comment_store.read_comments(doc_id, root=root)
    except comment_store.CommentStoreError as exc:
        raise EpicToolDenied(str(exc)) from exc
    if not any(row.id == comment_id for row in rows):
        raise CommentNotFound(comment_id)
    comment_store.reply_comment(
        doc_id,
        comment_id,
        body,
        author=author,
        root=root,
    )


def read_comment(comment_id: str, *, epic_id: str, root: Path) -> dict[str, object]:
    """Read the full text of a comment on this epic's plan."""

    _require_active_epic(epic_id, root)
    for row in comment_store.read_comments(epic_id, root=root):
        if row.id == comment_id:
            return row.to_dict()
    raise CommentNotFound(comment_id)


def _require_active_epic(epic_id: str, root: Path) -> None:
    repo = Path(root).resolve()
    try:
        epic = read_doc(epic_id, root=repo)
    except NotFound:
        raise EpicToolDenied(f"unknown work id {epic_id}") from None
    if epic.meta.tier != "epic":
        raise EpicToolDenied(f"{epic_id} is not an epic")
    if epic.meta.status != "active":
        raise EpicToolDenied(f"epic {epic_id} is not active")


register_epic_tool("reply_comment", reply_comment)
register_epic_tool("read_comment", read_comment)
