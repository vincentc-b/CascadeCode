"""Append decisions to a Feature decision log."""

from __future__ import annotations

from pathlib import Path

from cascade.board.decision_log import append_to_decision_log, find_matching_decision_id
from cascade.board.types import WorkDoc
from cascade.feature.registry import register_feature_tool
from cascade.feature.scoped_docs import feature_read_doc, feature_write_doc

_AUTHOR_LABELS = {
    "feature_architect": "Feature Architect",
    "feature_lead": "Feature Lead",
}


def record_decision(
    section: str,
    choice: str,
    rationale: str,
    honors: str,
    *,
    feature_id: str,
    root: Path,
    author: str = "feature_architect",
) -> str:
    """Append one entry to the Feature decision log and commit via feature_write_doc."""

    doc = feature_read_doc(feature_id, feature_id=feature_id, root=root)
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
        missing_section_message="feature body missing ## Decision log section",
    )
    updated = WorkDoc(meta=doc.meta, body=new_body, sha=doc.sha)
    feature_write_doc(updated, feature_id=feature_id, root=root)
    return decision_id


register_feature_tool("record_decision", record_decision)
