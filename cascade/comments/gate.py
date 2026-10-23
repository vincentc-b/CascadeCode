"""Scoped dispatch gate: open blocking comment roots (feat_019)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from cascade.board.context import resolve_root
from cascade.board.store import read_doc
from cascade.board.types import BoardIndex
from cascade.comments.slug import section_slug
from cascade.comments.store import read_comments
from cascade.comments.types import Comment
from cascade.workspace.integration_worktree import locate_trunk, merged_board

_HEADING_RE = re.compile(r"^(#{2,})\s+(.+?)\s*$", re.MULTILINE)


@dataclass(frozen=True)
class GateThread:
    id: str
    doc_id: str
    section: str
    blocking: bool


@dataclass
class GateResult:
    blocked: bool
    threads: list[GateThread] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def is_section_thread(doc_id: str, section: str, *, root: Path) -> bool:
    """True when ``section`` matches a current ``##`` or deeper heading slug on the doc."""

    if not section.strip():
        return False
    doc = read_doc(doc_id, root=resolve_root(root))
    for match in _HEADING_RE.finditer(doc.body):
        if section == section_slug(match.group(2)):
            return True
    return False


def blocking_threads_for(
    work_id: str, *, root: Path, board: BoardIndex | None = None
) -> GateResult:
    """Return open blocking roots on this work and ancestors that still block ``work_id``."""

    repo = resolve_root(root)
    trunk = locate_trunk(repo)
    board = board if board is not None else merged_board(trunk)
    warnings = _unmatched_cite_warnings(board, root=repo)
    blocking_roots = _load_blocking_roots(work_id, board, root=repo)
    hits: list[GateThread] = []
    for row in blocking_roots:
        if _blocks_work(row, work_id, board, root=repo):
            hits.append(
                GateThread(
                    id=row.id,
                    doc_id=row.doc_id,
                    section=row.section,
                    blocking=row.blocking,
                )
            )
    return GateResult(blocked=bool(hits), threads=hits, warnings=warnings)


def gate_refusal_reason(result: GateResult) -> str:
    """Human-readable refusal listing each blocking thread and plan deep-links."""

    lines = ["open blocking review thread(s):"]
    for thread in result.threads:
        link = f"/plan/{thread.doc_id}#plan-comments"
        lines.append(
            f"- {thread.id} doc_id={thread.doc_id} section={thread.section} {link}"
        )
    text = "\n".join(lines)
    if result.warnings:
        text = text + "\n" + "\n".join(result.warnings)
    return text


def refusal_if_blocked(
    work_id: str, *, root: Path, board: BoardIndex | None = None
) -> str | None:
    """Return refusal text when ``work_id`` is blocked by open review threads."""

    gate = blocking_threads_for(work_id, root=root, board=board)
    if gate.blocked:
        return gate_refusal_reason(gate)
    return None


def _load_blocking_roots(work_id: str, board, *, root: Path) -> list[Comment]:
    seen: set[str] = set()
    roots: list[Comment] = []
    for doc_id in _comment_scan_doc_ids(work_id, board):
        for row in read_comments(doc_id, root=root):
            if row.parent is not None:
                continue
            if row.state != "open" or not row.blocking:
                continue
            if row.id in seen:
                continue
            seen.add(row.id)
            roots.append(row)
    return roots


def _comment_scan_doc_ids(work_id: str, board) -> list[str]:
    meta = board.by_id.get(work_id)
    if meta is None:
        return [work_id]
    ids: list[str] = [work_id]
    if meta.tier == "task" and meta.parent:
        ids.append(meta.parent)
        feature = board.by_id.get(meta.parent)
        if feature and feature.parent:
            ids.append(feature.parent)
    elif meta.tier == "feature" and meta.parent:
        ids.append(meta.parent)
    return list(dict.fromkeys(ids))


def _blocks_work(row: Comment, work_id: str, board, *, root: Path) -> bool:
    affected = _affected_work_ids(row, board, root=root)
    if work_id in affected:
        return True
    meta = board.by_id.get(work_id)
    if meta and meta.tier == "task" and meta.parent and meta.parent in affected:
        return True
    return False


def _affected_work_ids(row: Comment, board, *, root: Path) -> set[str]:
    if row.blocks:
        return {bid for bid in row.blocks if bid in board.by_id}

    doc_id = row.doc_id
    meta = board.by_id.get(doc_id)
    tier = meta.tier if meta else None

    if (
        tier == "epic"
        and is_section_thread(doc_id, row.section, root=root)
    ):
        cite_key = f"{doc_id}#{row.section}"
        affected: set[str] = {doc_id}
        for feature in board.by_id.values():
            if feature.tier == "feature" and cite_key in feature.cites:
                affected.add(feature.id)
        return affected

    return _doc_and_children(doc_id, board)


def _doc_and_children(doc_id: str, board) -> set[str]:
    affected: set[str] = {doc_id}
    meta = board.by_id.get(doc_id)
    if meta is None:
        return affected
    for child_id in meta.children:
        if child_id in board.by_id:
            affected.add(child_id)
    return affected


def _unmatched_cite_warnings(board, *, root: Path) -> list[str]:
    warnings: list[str] = []
    seen: set[str] = set()
    for meta in board.by_id.values():
        if meta.tier != "feature":
            continue
        for cite in meta.cites:
            if cite in seen:
                continue
            seen.add(cite)
            doc_id, _, section = cite.partition("#")
            if not doc_id or not section:
                message = f"unmatched cite {cite!r} (no current heading on cited doc)"
                warnings.append(message)
                continue
            if doc_id not in board.by_id:
                message = f"unmatched cite {cite!r} (no current heading on cited doc)"
                warnings.append(message)
                continue
            if not is_section_thread(doc_id, section, root=root):
                message = f"unmatched cite {cite!r} (no current heading on cited doc)"
                warnings.append(message)
    return warnings
