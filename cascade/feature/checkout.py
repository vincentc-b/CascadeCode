"""Feature Team checkout root for guards and board tools."""

from __future__ import annotations

from pathlib import Path

from cascade.board.types import WorkId
from cascade.workspace.integration_worktree import doc_filesystem_root


def feature_checkout_root(feature_id: WorkId, *, trunk: Path) -> Path:
    """Git checkout that owns ``feature_id``'s spec and minted tasks."""

    return doc_filesystem_root(feature_id, trunk=Path(trunk).resolve())
