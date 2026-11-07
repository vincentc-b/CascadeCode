"""Role turn types for the Cursor SDK adapter (feat_009 / task_045)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from cascade.agent.providers import ProviderId
from cascade.agent.recovery_contract import ProviderRecoveryLaunch, ProviderRecoveryReport

RoleId = Literal[
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
    "boss",
]

RoleResultStatus = Literal["finished", "error"]
ProviderPermissionMode = Literal["default", "yolo"]


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
    # Cursor local agents: SDK custom_tools (stdio MCP is unreliable in the bridge).
    custom_tools: Mapping[str, Any] | None = None
    reasoning_level: str | None = None
    flex_mode: bool | None = None
    # Project-selected provider launch policy. ``default`` adds no optional
    # permission flag; ``yolo`` opts into the provider's non-interactive,
    # unrestricted permission mode.
    permission_mode: ProviderPermissionMode = "default"
    # Feature/Epic recovery input is identical for every provider launcher.
    recovery: ProviderRecoveryLaunch | None = None


@dataclass(frozen=True)
class RoleResult:
    text: str
    status: RoleResultStatus
    tool_effects: list[ToolEffect] = field(default_factory=list)
    # Adapters attach this only for an explicitly recovery-scoped turn.
    recovery: ProviderRecoveryReport | None = None
