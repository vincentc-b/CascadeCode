"""Idempotent feature and epic completion reconciliation (feat_002 / task_004)."""

from __future__ import annotations

from pathlib import Path

from cascade.board.context import resolve_root
from cascade.boss.epic_complete import epic_completed_recorded, try_complete_epic
from cascade.boss.rollup import feature_completed_recorded, try_complete_feature
from cascade.review import reconcile_feature_review_completions
from cascade.workspace.integration_worktree import locate_trunk, merged_board


def reconcile_completion(root: Path | None = None) -> dict[str, list[str]]:
    """Derive terminal feature and epic completion from persisted lifecycle state.

    Restart-safe: repeated calls do not duplicate ``FeatureCompleted`` or
    ``EpicCompleted`` transitions.
    """

    repo = resolve_root(root)
    trunk = locate_trunk(repo)
    features: list[str] = []
    epics: list[str] = []

    features.extend(reconcile_feature_review_completions(repo))

    board = merged_board(trunk)
    for meta in sorted(board.by_id.values(), key=lambda row: row.id):
        if meta.tier != "feature" or meta.path.parent.name != "2_active":
            continue
        epic_id = meta.parent or ""
        before = feature_completed_recorded(meta.id, epic_id, root=repo) if epic_id else False
        try_complete_feature(meta.id, root=repo)
        if epic_id and not before and feature_completed_recorded(meta.id, epic_id, root=repo):
            features.append(meta.id)

    board = merged_board(trunk)
    for meta in sorted(board.by_id.values(), key=lambda row: row.id):
        if meta.tier != "epic" or meta.path.parent.name != "2_active":
            continue
        before = epic_completed_recorded(meta.id, root=repo)
        try_complete_epic(meta.id, root=repo)
        if not before and epic_completed_recorded(meta.id, root=repo):
            epics.append(meta.id)

    return {"features": features, "epics": epics}
