"""Feature Team entrypoint for an owned integration-branch recovery."""

from __future__ import annotations

from pathlib import Path

from cascade.feature.registry import register_feature_tool
from cascade.team_branch_recovery import retry_team_integration_branch_update


def retry_integration_branch_update(
    action_id: str, *, feature_id: str, root: Path
) -> dict[str, object]:
    return retry_team_integration_branch_update(
        action_id,
        team_kind="feature_team",
        team_id=feature_id,
        root=root,
    )


register_feature_tool("retry_integration_branch_update", retry_integration_branch_update)
