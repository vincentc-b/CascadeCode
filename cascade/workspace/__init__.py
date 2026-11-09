"""Workspace contract: init and up against a git root."""

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.init import init_workspace
from cascade.workspace.project_config import (
    ProjectConfiguration,
    TrackingRepositoryReference,
    find_project_config,
    parse_tracking_repository_reference,
    read_project_configuration,
    read_tracking_repository,
)
from cascade.workspace.repository_resolver import (
    prepare_tracking_repository,
    synchronize_tracking_repository,
)
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.types import ProjectContext, RepositoryContext, WorkspaceRoot
from cascade.workspace.architecture import (
    ArchitectureArtifactRef,
    DesignOwnership,
    create_architecture_artifact_ref,
    ensure_target_repository_key,
    load_design_ownerships,
    require_design_ownership,
    resolve_artifact_ref_path,
    resolve_design_ownership,
)
from cascade.workspace.up import prepare_up, up

__all__ = [
    "WorkspaceError",
    "ProjectContext",
    "ProjectConfiguration",
    "RepositoryContext",
    "ArchitectureArtifactRef",
    "DesignOwnership",
    "TrackingRepositoryReference",
    "WorkspaceRoot",
    "find_project_config",
    "init_workspace",
    "parse_tracking_repository_reference",
    "read_project_configuration",
    "prepare_tracking_repository",
    "synchronize_tracking_repository",
    "prepare_up",
    "read_tracking_repository",
    "create_architecture_artifact_ref",
    "ensure_target_repository_key",
    "resolve_artifact_ref_path",
    "resolve_design_ownership",
    "load_design_ownerships",
    "require_design_ownership",
    "resolve_product_trunk",
    "up",
]
