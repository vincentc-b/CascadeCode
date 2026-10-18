"""Epic-scoped read_doc / write_doc wrappers."""

from __future__ import annotations

from pathlib import Path

from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc

from cascade.epic.guard import EpicToolDenied, tool_guard


def epic_read_doc(work_id: str, *, epic_id: str, root: Path) -> WorkDoc:
    """Read a work doc if the Epic team is allowed to see it."""

    doc = read_doc(work_id, root=root)
    if doc.meta.tier == "task":
        raise EpicToolDenied(f"epic team cannot read task {work_id}")
    if not tool_guard(doc.meta.path, "read", epic_id=epic_id, root=root):
        raise EpicToolDenied(f"read denied for {doc.meta.path}")
    return doc


def epic_write_doc(doc: WorkDoc, *, epic_id: str, root: Path) -> str | None:
    """Write a work doc if the Epic team is allowed to touch that path."""

    if doc.meta.tier == "task":
        raise EpicToolDenied(f"epic team cannot write task {doc.meta.id}")
    if doc.meta.tier == "feature":
        if doc.meta.parent != epic_id:
            raise EpicToolDenied(
                f"feature {doc.meta.id} parent {doc.meta.parent!r} != epic {epic_id}"
            )
        try:
            rel = doc.meta.path.resolve().relative_to(Path(root).resolve())
        except ValueError:
            raise EpicToolDenied(f"write denied for {doc.meta.path}") from None
        parts = rel.parts
        if (
            len(parts) < 3
            or parts[0] != "docs"
            or parts[1] != "features"
            or parts[2] != "1_backlog"
        ):
            raise EpicToolDenied(f"write denied for {doc.meta.path}")
        from cascade.board.store import list_board

        board = list_board(root)
        work_id = doc.meta.id
        if work_id in board.by_id:
            current = board.by_id[work_id]
            if current.path.resolve().parent.name != parts[2]:
                raise EpicToolDenied(
                    f"column move denied for {doc.meta.id}: {parts[2]!r}"
                )
    if not tool_guard(doc.meta.path, "write", epic_id=epic_id, root=root):
        raise EpicToolDenied(f"write denied for {doc.meta.path}")
    return write_doc(doc, root=root)
