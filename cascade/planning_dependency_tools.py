"""Scope-bound dependency status refresh for planning tools."""

from __future__ import annotations

from pathlib import Path

from cascade.dependency_projection import project_dependency_status


def refresh_epic_dependencies(*, epic_id: str, root: Path) -> dict[str, object]:
    """Refresh only the dependencies declared by the current owning epic."""

    from cascade.epic.scoped_docs import epic_read_doc

    owner = epic_read_doc(epic_id, epic_id=epic_id, root=root)
    return project_dependency_status(owner.meta, root=root).to_dict()


def refresh_feature_dependencies(*, feature_id: str, root: Path) -> dict[str, object]:
    """Refresh only the dependencies declared by the current owning feature."""

    from cascade.feature.scoped_docs import feature_read_doc

    owner = feature_read_doc(feature_id, feature_id=feature_id, root=root)
    return project_dependency_status(owner.meta, root=root).to_dict()
