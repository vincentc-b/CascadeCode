"""Normal Epic/Feature registry adapters for architecture publication."""

from __future__ import annotations

from pathlib import Path

from cascade.workspace.architecture_publication import publish_architecture_review


def publish_epic_architecture_review(
    *, proposal: dict[str, object], expected_plan_revision: str,
    expected_generation: int | None, actor: str, epic_id: str, root: Path,
) -> dict[str, object]:
    return publish_architecture_review(
        proposal=proposal, expected_plan_revision=expected_plan_revision,
        expected_generation=expected_generation, actor=actor,
        work_id=epic_id, root=root,
    )


def publish_feature_architecture_review(
    *, proposal: dict[str, object], expected_plan_revision: str,
    expected_generation: int | None, actor: str, feature_id: str, root: Path,
) -> dict[str, object]:
    return publish_architecture_review(
        proposal=proposal, expected_plan_revision=expected_plan_revision,
        expected_generation=expected_generation, actor=actor,
        work_id=feature_id, root=root,
    )
