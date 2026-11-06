"""Workspace contract: init and up against a git root."""

from cascade.workspace.errors import WorkspaceError
from cascade.workspace.init import init_workspace
from cascade.workspace.project_config import (
    TrackingRepositoryReference,
    find_project_config,
    parse_tracking_repository_reference,
    read_tracking_repository,
)
from cascade.workspace.repository_resolver import prepare_tracking_repository
from cascade.workspace.trunk import resolve_product_trunk
from cascade.workspace.types import ProjectContext, RepositoryContext, WorkspaceRoot
from cascade.workspace.up import prepare_up, up

__all__ = [
    "WorkspaceError",
    "ProjectContext",
    "RepositoryContext",
    "TrackingRepositoryReference",
    "WorkspaceRoot",
    "find_project_config",
    "init_workspace",
    "parse_tracking_repository_reference",
    "prepare_tracking_repository",
    "prepare_up",
    "read_tracking_repository",
    "resolve_product_trunk",
    "up",
]
