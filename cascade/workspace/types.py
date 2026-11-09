"""Workspace contract types (feat_014)."""

from __future__ import annotations

import hashlib
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
ArchitectureDestination = Literal["target", "tracking"]


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
    continuation_receipt_id: str | None = None
    continuation_handoff_id: str | None = None


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
    repository_key: str | None = None

    def __post_init__(self) -> None:
        root = Path(self.root).resolve()
        object.__setattr__(self, "root", root)
        if self.repository_key is None:
            # The key deliberately contains no basename.  Repository basenames
            # are neither unique nor stable enough to own mirrored documents.
            identity = self.display_identity or root.as_uri()
            digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
            object.__setattr__(self, "repository_key", f"repository-{digest}")


@dataclass(frozen=True)
class ProjectContext:
    """Explicit target and tracking repository roles for downstream services.

    In compatibility mode both names intentionally reference the same immutable
    context object.  A repository resolver can instead supply two contexts
    without changing consumers of this contract.
    """

    target: RepositoryContext
    tracking: RepositoryContext
    architecture_destination: ArchitectureDestination = "target"

    def __post_init__(self) -> None:
        if self.architecture_destination not in {"target", "tracking"}:
            raise ValueError(
                "architecture destination must be either 'target' or 'tracking'"
            )

    @classmethod
    def colocated(cls, root: Path) -> "ProjectContext":
        repository = RepositoryContext(root=Path(root).resolve())
        return cls(target=repository, tracking=repository)

    @classmethod
    def split(
        cls,
        target: Path,
        tracking: Path,
        *,
        architecture_destination: ArchitectureDestination = "target",
    ) -> "ProjectContext":
        return cls(
            target=RepositoryContext(root=Path(target).resolve()),
            tracking=RepositoryContext(root=Path(tracking).resolve()),
            architecture_destination=architecture_destination,
        )

    @property
    def architecture_repository(self) -> RepositoryContext:
        if self.architecture_destination == "tracking":
            return self.tracking
        return self.target

    @property
    def target_repository_key(self) -> str:
        # The target key is stored with the first target-owned architecture
        # mapping. It must not be reconstructed from a checkout path, remote
        # name, or directory basename once that index exists.
        from cascade.workspace.architecture import ensure_target_repository_key

        return ensure_target_repository_key(self)

    @property
    def editable_architecture_root(self) -> Path:
        return (
            self.architecture_repository.root
            / "architecture"
            / self.target_repository_key
        )

    @property
    def design_ownership_path(self) -> Path:
        # This index deliberately remains in the target repository even when
        # architecture artifacts are routed to the tracking repository.
        return self.target.root / "architecture" / "design-mappings.json"

    def design_path(self, code_directory: Path | str = ".") -> Path:
        """Resolve the one DESIGN.md home for a target-code directory."""

        relative = Path(code_directory)
        if relative.is_absolute():
            try:
                relative = relative.resolve().relative_to(self.target.root)
            except ValueError as exc:
                raise ValueError("code directory must be inside the target repository") from exc
        if any(part == ".." for part in relative.parts):
            raise ValueError("code directory must not escape the target repository")
        relative = Path(*[part for part in relative.parts if part not in {"", "."}])
        if self.architecture_destination == "tracking":
            return (
                self.tracking.root
                / "design"
                / self.target_repository_key
                / relative
                / "DESIGN.md"
            )
        return self.target.root / relative / "DESIGN.md"


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
