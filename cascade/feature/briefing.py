"""Briefing pack for feature war-room attach (feat_005)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from cascade.board.errors import NotFound
from cascade.workspace.doc_root import read_doc_resolved, resolve_doc_worktree
from cascade.workspace.integration_worktree import locate_trunk
from cascade.board.types import WorkDoc
from cascade.comments.store import read_comments
from cascade.comments.types import Comment
from cascade.feature.checkpoint import thread_config
from cascade.feature.graph import ensure_feature_graph

_DECISION_LOG_HEADING = re.compile(r"^## Decision log\s*$", re.MULTILINE)


@dataclass(frozen=True)
class BriefingPack:
    doc: WorkDoc
    decision_log: str
    open_comments: list[Comment]
    parent_constraints: WorkDoc | None
    recent_messages: list[dict]


def extract_decision_log(body: str) -> str:
    """Return markdown under ``## Decision log`` until the next ``##`` heading."""

    match = _DECISION_LOG_HEADING.search(body)
    if not match:
        return ""
    start = match.end()
    if start < len(body) and body[start] == "\n":
        start += 1
    next_heading = re.search(r"^## ", body[start:], re.MULTILINE)
    section_end = start + next_heading.start() if next_heading else len(body)
    return body[start:section_end].strip()


def _parent_at_pin(feature: WorkDoc, *, root: Path) -> WorkDoc | None:
    parent_id = feature.meta.parent
    if not parent_id:
        return None
    rev = feature.meta.parent_rev
    if not rev:
        return None
    from cascade.board.errors import GitError
    from cascade.board.store import read_doc_in_worktree
    from cascade.workspace.doc_root import resolve_doc_worktree

    try:
        epic_root = resolve_doc_worktree(parent_id, root=root)
        parent = read_doc_in_worktree(parent_id, epic_root, rev=rev)
    except (NotFound, GitError):
        return None
    if parent.meta.tier != "epic":
        return None
    return parent


def _recent_graph_messages(feature_id: str, *, root: Path, limit: int = 20) -> list[dict]:
    graph = ensure_feature_graph(feature_id, root=root)
    snapshot = graph.get_state(thread_config(feature_id))
    values = snapshot.values or {}
    messages = list(values.get("messages") or [])
    if limit <= 0:
        return []
    return messages[-limit:]


def build_briefing_pack(
    feature_id: str,
    *,
    root: Path,
    recent_limit: int = 20,
) -> BriefingPack:
    """Assemble attach briefing for one feature work id."""

    trunk = locate_trunk(Path(root).resolve())
    feature = read_doc_resolved(feature_id, root=trunk)
    if feature.meta.tier != "feature":
        raise ValueError(f"{feature_id} is not a feature")
    doc_root = resolve_doc_worktree(feature_id, root=trunk)

    open_comments = [
        row for row in read_comments(feature_id, root=trunk) if row.state == "open"
    ]
    return BriefingPack(
        doc=feature,
        decision_log=extract_decision_log(feature.body),
        open_comments=open_comments,
        parent_constraints=_parent_at_pin(feature, root=trunk),
        recent_messages=_recent_graph_messages(
            feature_id, root=trunk, limit=recent_limit
        ),
    )
