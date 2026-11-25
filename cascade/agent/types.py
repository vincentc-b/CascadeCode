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
UsageQuality = Literal["known", "estimated", "unavailable"]
InvocationOutcome = Literal["success", "error", "interrupted", "unknown"]
CancellationBound = Literal["provider", "local_transport", "unavailable"]
RecoveryLaunchRoute = Literal[
    "direct",
    "manual",
    "periodic",
    "audit",
    "briefing",
    "provider_switch",
    "parent",
    "replacement_action",
]

_RECOVERY_LAUNCH_ROUTES = frozenset(
    {
        "direct",
        "manual",
        "periodic",
        "audit",
        "briefing",
        "provider_switch",
        "parent",
        "replacement_action",
    }
)


@dataclass(frozen=True, slots=True)
class ProviderUsageValue:
    """One provider usage field without manufacturing a missing value."""

    quality: UsageQuality
    value: int | None = None

    def __post_init__(self) -> None:
        if self.quality not in {"known", "estimated", "unavailable"}:
            raise ValueError(f"unsupported provider usage quality: {self.quality}")
        if self.quality == "unavailable":
            if self.value is not None:
                raise ValueError("unavailable provider usage cannot have a value")
        elif isinstance(self.value, bool) or not isinstance(self.value, int) or self.value < 0:
            raise ValueError(f"{self.quality} provider usage requires a non-negative integer")


def unavailable_provider_usage() -> ProviderUsageValue:
    return ProviderUsageValue("unavailable")


@dataclass(frozen=True, slots=True)
class ProviderTokenUsage:
    """Normalized token evidence; cached input remains a subset, not an addend."""

    input: ProviderUsageValue = field(default_factory=unavailable_provider_usage)
    output: ProviderUsageValue = field(default_factory=unavailable_provider_usage)
    cached_input: ProviderUsageValue = field(default_factory=unavailable_provider_usage)

    def __post_init__(self) -> None:
        if (
            self.input.value is not None
            and self.cached_input.value is not None
            and self.cached_input.value > self.input.value
        ):
            raise ValueError("cached input tokens must be a subset of input tokens")

    @property
    def known_total(self) -> int:
        """Return only provider-reported known input plus output tokens."""

        values = (self.input, self.output)
        if any(item.quality != "known" for item in values):
            return 0
        return sum(item.value or 0 for item in values)


@dataclass(frozen=True, slots=True)
class ProviderInvocationReceipt:
    """Provider-neutral evidence for one physical model invocation."""

    provider: ProviderId
    model_id: str
    invocation_id: str
    usage: ProviderTokenUsage = field(default_factory=ProviderTokenUsage)
    outcome: InvocationOutcome = "success"
    cancellation_bound: CancellationBound = "unavailable"
    output_token_limit: int | None = None

    def __post_init__(self) -> None:
        if self.outcome not in {"success", "error", "interrupted", "unknown"}:
            raise ValueError(f"unsupported provider invocation outcome: {self.outcome}")
        if self.cancellation_bound not in {
            "provider",
            "local_transport",
            "unavailable",
        }:
            raise ValueError(
                f"unsupported provider cancellation bound: {self.cancellation_bound}"
            )
        if not self.model_id or not self.model_id.strip():
            raise ValueError("invocation model_id must be nonempty")
        if not self.invocation_id or self.invocation_id.strip() != self.invocation_id:
            raise ValueError("invocation_id must be a nonempty stable string")
        if self.output_token_limit is not None and (
            isinstance(self.output_token_limit, bool)
            or not isinstance(self.output_token_limit, int)
            or self.output_token_limit <= 0
        ):
            raise ValueError("output_token_limit must be a positive integer")

    def to_dict(self) -> dict[str, Any]:
        def usage_value(value: ProviderUsageValue) -> dict[str, Any]:
            return {"quality": value.quality, "value": value.value}

        return {
            "provider": self.provider,
            "model_id": self.model_id,
            "invocation_id": self.invocation_id,
            "usage": {
                "input": usage_value(self.usage.input),
                "output": usage_value(self.usage.output),
                "cached_input": usage_value(self.usage.cached_input),
            },
            "outcome": self.outcome,
            "cancellation_bound": self.cancellation_bound,
            "output_token_limit": self.output_token_limit,
        }


@dataclass(frozen=True, slots=True)
class IncidentProviderTurn:
    """Canonical Task-budget identity and finite bounds for a recovery turn."""

    incident_id: str
    claim_id: str
    operation_id: str
    root: Path
    policy_version: int = 1
    worst_case_model_seconds: int = 300
    worst_case_known_tokens: int = 0
    output_token_limit: int | None = None
    cancellation_bound: CancellationBound = "local_transport"
    launch_route: RecoveryLaunchRoute = "direct"

    def __post_init__(self) -> None:
        for name in ("incident_id", "claim_id", "operation_id"):
            value = getattr(self, name)
            if not value or value.strip() != value:
                raise ValueError(f"{name} must be a nonempty stable string")
        if isinstance(self.policy_version, bool) or not isinstance(
            self.policy_version, int
        ) or self.policy_version <= 0:
            raise ValueError("policy_version must be positive")
        if isinstance(self.worst_case_model_seconds, bool) or not isinstance(
            self.worst_case_model_seconds, int
        ) or self.worst_case_model_seconds <= 0:
            raise ValueError("worst_case_model_seconds must be positive")
        if isinstance(self.worst_case_known_tokens, bool) or not isinstance(
            self.worst_case_known_tokens, int
        ) or self.worst_case_known_tokens < 0:
            raise ValueError("worst_case_known_tokens cannot be negative")
        if self.output_token_limit is not None and (
            isinstance(self.output_token_limit, bool)
            or not isinstance(self.output_token_limit, int)
            or self.output_token_limit <= 0
        ):
            raise ValueError("output_token_limit must be a positive integer")
        if self.cancellation_bound not in {
            "provider",
            "local_transport",
            "unavailable",
        }:
            raise ValueError(
                f"unsupported provider cancellation bound: {self.cancellation_bound}"
            )
        if self.launch_route not in _RECOVERY_LAUNCH_ROUTES:
            raise ValueError(
                f"unsupported recovery launch route: {self.launch_route}"
            )


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
    # Required for any non-terminal recovery turn. Admission is performed in
    # ``run_role`` immediately before the provider adapter is invoked.
    incident_turn: IncidentProviderTurn | None = None


@dataclass(frozen=True)
class RoleResult:
    text: str
    status: RoleResultStatus
    tool_effects: list[ToolEffect] = field(default_factory=list)
    # Adapters attach this only for an explicitly recovery-scoped turn.
    recovery: ProviderRecoveryReport | None = None
    invocation: ProviderInvocationReceipt | None = None
