"""Epic Team entrypoint for publishing an owned review resolution."""

from __future__ import annotations

from pathlib import Path

from cascade.epic.registry import register_epic_tool
from cascade.team_review_recovery import publish_team_review_resolution


def publish_review_resolution(action_id: str, *, epic_id: str, root: Path) -> dict[str, object]:
    return publish_team_review_resolution(
        action_id, team_kind="epic_team", team_id=epic_id, root=root
    )


register_epic_tool("publish_review_resolution", publish_review_resolution)
