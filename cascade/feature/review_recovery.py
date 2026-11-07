"""Feature Team entrypoint for publishing an owned review resolution."""

from __future__ import annotations

from pathlib import Path

from cascade.feature.registry import register_feature_tool
from cascade.team_review_recovery import publish_team_review_resolution


def publish_review_resolution(action_id: str, *, feature_id: str, root: Path) -> dict[str, object]:
    return publish_team_review_resolution(
        action_id, team_kind="feature_team", team_id=feature_id, root=root
    )


register_feature_tool("publish_review_resolution", publish_review_resolution)
