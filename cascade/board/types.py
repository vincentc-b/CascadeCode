"""Work-document types locked by feat_001."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from cascade.agent.providers import ProviderId

WorkTier = Literal["epic", "feature", "task"]
WorkStatus = Literal["backlog", "ready_to_plan", "active", "blocked", "completed", "cancelling", "cancelled"]
Column = Literal["backlog", "active", "completed"]
WorkId = str


@dataclass
class WorkMeta:
    """Frontmatter plus the on-disk path. Path is not stored in the file."""

    id: WorkId
    title: str
    tier: WorkTier
    status: WorkStatus
    parent: WorkId | None
    children: list[WorkId]
    depends_on: list[WorkId]
    owners: list[str]
    skills: list[Path]
    parent_rev: str | None
    created: date
    updated: date
    path: Path
    model: str | None = None
    models: dict[str, str] | None = None
    reasoning: dict[str, str] | None = None
    provider: ProviderId | None = None
    integration_branch: str | None = None
    integration_worktree: str | None = None
    cites: list[str] = field(default_factory=list)
    approved_at: datetime | None = None
    plan_approved_at: datetime | None = None
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    cancellation_step: str | None = None
    cancellation_error: str | None = None


@dataclass
class WorkDoc:
    """A parsed work markdown file."""

    meta: WorkMeta
    body: str
    sha: str | None = None


@dataclass
class BoardIndex:
    """Directory scan of the board. Not a durable cache."""

    by_id: dict[WorkId, WorkMeta] = field(default_factory=dict)
