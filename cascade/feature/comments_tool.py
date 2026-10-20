"""Feature Team comment thread tools (own feature doc only)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.errors import NotFound
from cascade.board.store import read_doc
from cascade.comments import store as comment_store
from cascade.comments.store import CommentNotFound
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.registry import register_feature_tool


def reply_comment(
    comment_id: str,
    body: str,
    *,
    feature_id: str,
    root: Path,
    author: str = "feature_lead",
    doc_id: str | None = None,
) -> str:
    _require_own_feature(feature_id, root)
    target = _target_doc_id(feature_id, doc_id, root=root)
    try:
        parent = comment_store.read_comments(target, root=root)
    except comment_store.CommentStoreError as exc:
        raise FeatureToolDenied(str(exc)) from exc
    if not any(row.id == comment_id for row in parent):
        raise CommentNotFound(comment_id)
    return comment_store.reply_comment(
        target,
        comment_id,
        body,
        author=author,
        root=root,
    )


def _target_doc_id(feature_id: str, doc_id: str | None, *, root: Path) -> str:
    if doc_id is None:
        return feature_id
    tier = comment_store.work_tier(doc_id, root=root)
    if tier == "epic":
        raise FeatureToolDenied("feature tools cannot access epic-owned threads")
    if doc_id != feature_id:
        raise FeatureToolDenied("feature tools cannot access another doc's threads")
    return doc_id


def _require_own_feature(feature_id: str, root: Path) -> None:
    repo = Path(root).resolve()
    try:
        doc = read_doc(feature_id, root=repo)
    except NotFound:
        raise FeatureToolDenied(f"unknown work id {feature_id}") from None
    if doc.meta.tier != "feature":
        raise FeatureToolDenied(f"{feature_id} is not a feature")


register_feature_tool("reply_comment", reply_comment)
