"""Shared comment sidecar store."""

from cascade.comments.slug import section_slug
from cascade.comments.store import (
    BlockingNotAllowed,
    CommentNotFound,
    CommentStoreError,
    NotARoot,
    ReopenNotAllowed,
    ResolveNotAllowed,
    comment,
    read_comments,
    reopen_comment,
    reply_comment,
    resolve_comment,
    sidecar_path,
    work_tier,
)
from cascade.comments.types import AGENT_AUTHORS, Comment, CommentAuthor, CommentState
from cascade.comments.handoffs import (
    ChangeRequestHandoff,
    CommentHandoffError,
    escalate_feature_comment,
    read_change_request_handoffs,
    route_feature_comment,
)

__all__ = [
    "AGENT_AUTHORS",
    "BlockingNotAllowed",
    "Comment",
    "CommentAuthor",
    "CommentNotFound",
    "CommentState",
    "CommentStoreError",
    "ChangeRequestHandoff",
    "CommentHandoffError",
    "NotARoot",
    "ReopenNotAllowed",
    "ResolveNotAllowed",
    "comment",
    "escalate_feature_comment",
    "read_comments",
    "reopen_comment",
    "read_change_request_handoffs",
    "reply_comment",
    "resolve_comment",
    "route_feature_comment",
    "section_slug",
    "sidecar_path",
    "work_tier",
]
