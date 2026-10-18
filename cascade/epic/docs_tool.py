"""Epic-scoped read_doc / write_doc tool wrappers."""

from __future__ import annotations

from pathlib import Path

from cascade.board.types import WorkDoc
from cascade.epic.registry import register_epic_tool
from cascade.epic.scoped_docs import epic_read_doc, epic_write_doc


def read_doc(work_id: str, *, epic_id: str, root: Path) -> WorkDoc:
    return epic_read_doc(work_id, epic_id=epic_id, root=root)


def write_doc(doc: WorkDoc, *, epic_id: str, root: Path) -> str | None:
    return epic_write_doc(doc, epic_id=epic_id, root=root)


register_epic_tool("read_doc", read_doc)
register_epic_tool("write_doc", write_doc)
