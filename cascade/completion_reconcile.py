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

    from cascade.stacked_dispatch import reconcile_stacked_native_retargeting

    reconcile_stacked_native_retargeting(repo)

    board = merged_board(trunk)
    for meta in sorted(board.by_id.values(), key=lambda row: row.id):
        if meta.tier != "feature" or meta.path.parent.name not in (
            "2_active",
            "3_completed",
        ):
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


def reconcile_completion_with_prompts(root: Path | None = None) -> dict[str, list[str]]:
    """Run completion reconciliation and surface epic close prompts for new completions."""

    repo = resolve_root(root)
    result = reconcile_completion(root=repo)
    from cascade.boss.epic_complete import on_feature_completed
    from cascade.workspace.integration_worktree import locate_trunk, merged_board

    board = merged_board(locate_trunk(repo))
    auto_completed_epics = set(result["epics"])

    for feature_id in result["features"]:
        feature = board.by_id.get(feature_id)
        if feature is None:
            continue
        epic_id = feature.parent or ""
        if not epic_id or epic_id in auto_completed_epics:
            continue
        epic = board.by_id.get(epic_id)
        if epic is None or epic.path.parent.name != "2_active":
            continue
        on_feature_completed(feature_id, root=repo)
    return result
