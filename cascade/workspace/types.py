"""Workspace contract types (feat_014)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from cascade.workspace.integration_worktree import IntegrationWorktree

KickoffKind = Literal[
    "activate",
    "dispatch",
    "human_message",
    "comment",
    "queue_event",
    "resume_inflight",
]
KickoffPrincipal = Literal["human", "boss", "watchdog"]


@dataclass(frozen=True)
class KickoffReason:
    """Authorized edge that may start one roster model turn."""

    kind: KickoffKind
    work_id: str
    by: KickoffPrincipal
    root: Path | None = None
    message: dict | None = None
    feature_id: str | None = None
    model_id: str | None = None


@dataclass(frozen=True)
class FlightOverlap:
    paths: tuple[str, ...]
    work_ids: tuple[str, ...]


@dataclass(frozen=True)
class FlightReport:
    epics: tuple["IntegrationWorktree", ...]
    features: tuple["IntegrationWorktree", ...]
    tasks: tuple["IntegrationWorktree", ...]
    changed_paths: dict[str, tuple[str, ...]]
    overlaps: tuple[FlightOverlap, ...]


@dataclass(frozen=True)
class RepositoryContext:
    """A resolved checkout used by one or more project repository roles."""

    root: Path
    display_identity: str | None = None
    synchronize_remote: bool = False


@dataclass(frozen=True)
class ProjectContext:
    """Explicit target and tracking repository roles for downstream services.

    In compatibility mode both names intentionally reference the same immutable
    context object.  A repository resolver can instead supply two contexts
    without changing consumers of this contract.
    """

    target: RepositoryContext
    tracking: RepositoryContext

    @classmethod
    def colocated(cls, root: Path) -> "ProjectContext":
        repository = RepositoryContext(root=Path(root).resolve())
        return cls(target=repository, tracking=repository)

    @classmethod
    def split(cls, target: Path, tracking: Path) -> "ProjectContext":
        return cls(
            target=RepositoryContext(root=Path(target).resolve()),
            tracking=RepositoryContext(root=Path(tracking).resolve()),
        )


@dataclass(frozen=True)
class WorkspaceRoot:
    """Git workspace paths the supervisor uses against a single repo root."""

    path: Path
    trunk: str | None
    board: Path
    config: Path
    runtime: Path
    project: ProjectContext | None = None

    def __post_init__(self) -> None:
        if self.project is None:
            object.__setattr__(self, "project", ProjectContext.colocated(self.path))

    @property
    def target_repository(self) -> RepositoryContext:
        assert self.project is not None
        return self.project.target

    @property
    def tracking_repository(self) -> RepositoryContext:
        assert self.project is not None
        return self.project.tracking
