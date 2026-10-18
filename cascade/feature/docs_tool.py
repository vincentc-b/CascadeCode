"""Feature-scoped read_doc / write_doc / list_children tool wrappers."""

from __future__ import annotations

from pathlib import Path

from cascade.board.types import WorkDoc, WorkMeta
from cascade.feature.registry import register_feature_tool
from cascade.feature.scoped_docs import (
    feature_read_doc,
    feature_write_doc,
    list_children as feature_list_children,
)


def read_doc(work_id: str, *, feature_id: str, root: Path) -> WorkDoc:
    return feature_read_doc(work_id, feature_id=feature_id, root=root)


def write_doc(doc: WorkDoc, *, feature_id: str, root: Path) -> str | None:
    return feature_write_doc(doc, feature_id=feature_id, root=root)


def list_children(*, feature_id: str, root: Path) -> list[WorkMeta]:
    return feature_list_children(feature_id=feature_id, root=root)


register_feature_tool("read_doc", read_doc)
register_feature_tool("write_doc", write_doc)
register_feature_tool("list_children", list_children)
