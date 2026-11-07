"""Scope-bound dependency status refresh for planning tools."""

from __future__ import annotations

from pathlib import Path

from cascade.dependency_projection import project_dependency_evaluation
from cascade.planning_action_dependencies import evaluate_action_dependencies


def refresh_planning_dependencies(work_id: str, *, root: Path) -> dict[str, object]:
    """Return a projection from an uncached, request-snapshot-free board read."""

    evidence = evaluate_action_dependencies(work_id, root=root)
    return project_dependency_evaluation(work_id, evidence.evaluation).to_dict()


def refresh_epic_dependencies(*, epic_id: str, root: Path) -> dict[str, object]:
    """Refresh only the dependencies declared by the current owning epic."""

    return refresh_planning_dependencies(epic_id, root=root)


def refresh_feature_dependencies(*, feature_id: str, root: Path) -> dict[str, object]:
    """Refresh only the dependencies declared by the current owning feature."""

    return refresh_planning_dependencies(feature_id, root=root)
