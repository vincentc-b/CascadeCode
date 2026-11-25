"""Cursor SDK role adapter (feat_009)."""

from cascade.agent.adapter import (
    build_agent_options,
    reject_cloud_runtime,
    run_role,
    validate_model_id,
)
from cascade.agent.credentials import (
    Credential,
    forget_user_store_token,
    resolve_credential,
    write_user_store_token,
)
from cascade.agent.errors import (
    CursorAgentError,
    ProviderConfigError,
    ProviderNotAuthenticatedError,
    ProviderNotImplementedError,
    ProviderNotInstalledError,
    ProviderBudgetRefusedError,
)
from cascade.agent.providers import (
    ALL_PROVIDER_IDS,
    AuthSource,
    ProviderId,
    ProviderStatus,
    parse_provider_id,
    probe_provider,
    probe_providers,
)
from cascade.agent.types import (
    IncidentProviderTurn,
    ProviderInvocationReceipt,
    ProviderTokenUsage,
    ProviderUsageValue,
    RoleId,
    RoleResult,
    RoleTurn,
    ToolEffect,
)

_PLANNING_EXPORTS = frozenset(
    {
        "run_boss_planning_turn",
        "run_epic_planning_turn",
        "run_feature_planning_turn",
    }
)


def __getattr__(name: str) -> object:
    if name in _PLANNING_EXPORTS:
        from cascade.agent import planning_turn

        return getattr(planning_turn, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "ALL_PROVIDER_IDS",
    "AuthSource",
    "Credential",
    "CursorAgentError",
    "ProviderConfigError",
    "ProviderBudgetRefusedError",
    "ProviderId",
    "ProviderNotAuthenticatedError",
    "ProviderNotImplementedError",
    "ProviderNotInstalledError",
    "ProviderStatus",
    "forget_user_store_token",
    "resolve_credential",
    "write_user_store_token",
    "RoleId",
    "IncidentProviderTurn",
    "ProviderInvocationReceipt",
    "ProviderTokenUsage",
    "ProviderUsageValue",
    "RoleResult",
    "RoleTurn",
    "ToolEffect",
    "build_agent_options",
    "parse_provider_id",
    "probe_provider",
    "probe_providers",
    "reject_cloud_runtime",
    "run_boss_planning_turn",
    "run_epic_planning_turn",
    "run_feature_planning_turn",
    "run_role",
    "validate_model_id",
]
