"""Epic Team entrypoint for an owned integration-branch recovery."""

from __future__ import annotations

from pathlib import Path

from cascade.epic.registry import register_epic_tool
from cascade.team_branch_recovery import retry_team_integration_branch_update


def retry_integration_branch_update(
    action_id: str, *, epic_id: str, root: Path
) -> dict[str, object]:
    return retry_team_integration_branch_update(
        action_id,
        team_kind="epic_team",
        team_id=epic_id,
        root=root,
    )


register_epic_tool("retry_integration_branch_update", retry_integration_branch_update)
