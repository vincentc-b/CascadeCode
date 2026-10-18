"""Role turn types for the Cursor SDK adapter (feat_009 / task_045)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cascade.agent.providers import ProviderId

RoleId = Literal[
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
    "boss",
]

RoleResultStatus = Literal["finished", "error"]


@dataclass(frozen=True)
class ToolEffect:
    """Cascade-applied tool outcome (filled by later MCP sandbox tasks)."""

    tool: str
    summary: str = ""


@dataclass(frozen=True)
class RoleTurn:
    role: RoleId
    provider: ProviderId
    model_id: str
    prompt: str
    cwd: Path
    tools: list[Any] | dict[str, Any] = field(default_factory=list)


@dataclass(frozen=True)
class RoleResult:
    text: str
    status: RoleResultStatus
    tool_effects: list[ToolEffect] = field(default_factory=list)
