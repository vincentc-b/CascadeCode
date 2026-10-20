"""Epic Team checkout root for guards and board tools."""

from __future__ import annotations

from pathlib import Path

from cascade.board.types import WorkId
from cascade.workspace.integration_worktree import doc_filesystem_root


def epic_checkout_root(epic_id: WorkId, *, trunk: Path) -> Path:
    """Git checkout that owns ``epic_id``'s live spec and backlog features."""

    return doc_filesystem_root(epic_id, trunk=Path(trunk).resolve())
