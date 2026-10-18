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
class WorkspaceRoot:
    """Git workspace paths the supervisor uses against a single repo root."""

    path: Path
    trunk: str | None
    board: Path
    config: Path
    runtime: Path
