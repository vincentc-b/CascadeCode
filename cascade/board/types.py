"""Work-document types locked by feat_001."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Literal

from cascade.agent.providers import ProviderId

WorkTier = Literal["epic", "feature", "task"]
WorkStatus = Literal[
    "backlog",
    "ready_to_plan",
    "active",
    "blocked",
    "completed",
    "cancelling",
    "cancelled",
]
Column = Literal["backlog", "active", "completed"]
WorkId = str
CancellationDisposition = Literal[
    "continue_reduced_scope", "replace_replan", "cancel_parent"
]


@dataclass
class CancellationFeedback:
    """Durable upward feedback created by a cancelled direct child."""

    child_id: WorkId
    child_tier: WorkTier
    parent_id: WorkId
    reason: str
    cancelled_at: datetime
    available_dispositions: list[CancellationDisposition] = field(
        default_factory=lambda: [
            "continue_reduced_scope",
            "replace_replan",
            "cancel_parent",
        ]
    )
    disposition: CancellationDisposition | None = None
    resolved_at: datetime | None = None


@dataclass(frozen=True)
class MonitoringBlocker:
    """A blockage reported by monitoring one immediate child."""

    child_id: WorkId
    reason: str
    # True only when adding this cause performed the active -> blocked edge.
    # Reconciliation must not reopen work that was already blocked manually.
    blocked_supervisor: bool = False
    # Recovery results are durable incidents, rather than a broad condition on
    # a child.  Keeping their identity lets a later recovery clear only the
    # blocker it actually resolved.
    incident_id: str | None = None


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
    flex_mode: bool | None = None
    integration_branch: str | None = None
    integration_worktree: str | None = None
    cites: list[str] = field(default_factory=list)
    approved_at: datetime | None = None
    plan_approved_at: datetime | None = None
    cancellation_reason: str | None = None
    cancelled_at: datetime | None = None
    cancellation_step: str | None = None
    cancellation_error: str | None = None
    cancellation_feedback: list[CancellationFeedback] = field(default_factory=list)
    monitoring_blockers: list[MonitoringBlocker] = field(default_factory=list)


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
