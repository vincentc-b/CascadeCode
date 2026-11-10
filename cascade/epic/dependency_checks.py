"""Owning-team dependency verification and approved setup continuation."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from cascade.epic.dependency_resume import resume_dependency_bootstrap
from cascade.epic.dependency_status import project_dependency_status
from cascade.epic.local_dependency_executor import LocalBoundedDependencyExecutor


def run_dependency_check(*, epic_id: str, root: Path) -> dict[str, object]:
    """Inspect declared dependencies, installing only with current human approval.

    Runs inside the owning planning turn, so it must not quiesce or relaunch that
    turn. This tool accepts no commands, environment overrides or approval data.
    """
    from cascade.epic.dependency_manifest_authoring import _owned_repository
    from cascade.workspace.integration_worktree import locate_trunk
    from cascade.board.context import get_project_context

    _owned_repository(epic_id, root)
    project = get_project_context()
    execution_root = project.target.root if project else locate_trunk(root)
    result = resume_dependency_bootstrap(
        epic_id, f"team-check-{uuid4().hex}", root=root,
        executor=LocalBoundedDependencyExecutor(execution_root), coordinate_planning=False,
    )
    return {
        "check": result.to_dict(),
        "software_dependency_status": project_dependency_status(epic_id, root=root),
    }
