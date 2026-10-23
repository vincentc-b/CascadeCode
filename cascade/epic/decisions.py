"""Append decisions to an Epic decision log."""

from __future__ import annotations

from pathlib import Path

from cascade.board.decision_log import append_to_decision_log, find_matching_decision_id
from cascade.board.types import WorkDoc
from cascade.epic.registry import register_epic_tool
from cascade.epic.scoped_docs import epic_read_doc, epic_write_doc

_AUTHOR_LABELS = {
    "epic_architect": "Epic Architect",
    "epic_manager": "Epic Manager",
}


def record_decision(
    section: str,
    choice: str,
    rationale: str,
    honors: str,
    *,
    epic_id: str,
    root: Path,
    author: str = "epic_architect",
) -> str:
    """Append one entry to the Epic decision log and commit via epic_write_doc."""

    doc = epic_read_doc(epic_id, epic_id=epic_id, root=root)
    existing = find_matching_decision_id(doc.body, section=section, choice=choice)
    if existing is not None:
        return existing
    decision_id, new_body = append_to_decision_log(
        doc.body,
        section=section,
        choice=choice,
        rationale=rationale,
        honors=honors,
        author=author,
        author_labels=_AUTHOR_LABELS,
        missing_section_message="epic body missing ## Decision log section",
    )
    updated = WorkDoc(meta=doc.meta, body=new_body, sha=doc.sha)
    epic_write_doc(updated, epic_id=epic_id, root=root)
    return decision_id


register_epic_tool("record_decision", record_decision)
