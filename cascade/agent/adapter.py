"""Local async Cursor SDK adapter for one-shot role turns."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from cursor_sdk import (
    AgentOptions,
    AsyncAgent,
    AsyncClient,
    CloudAgentOptions,
    LocalAgentOptions,
    SandboxOptions,
)
from cursor_sdk import CursorAgentError as SdkCursorAgentError

from cascade.agent.credentials import resolve_credential
from cascade.agent.errors import (
    CursorAgentError,
    ProviderNotAuthenticatedError,
    ProviderNotImplementedError,
    ProviderNotInstalledError,
)
from cascade.agent.providers import parse_provider_id, probe_provider
from cascade.agent.types import RoleId, RoleResult, RoleResultStatus, RoleTurn

_PLANNING_ROLES: frozenset[RoleId] = frozenset(
    {
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "boss",
    }
)


def validate_model_id(model_id: str) -> None:
    if not model_id or not model_id.strip():
        raise ValueError("model_id is required and must be non-blank")


def reject_cloud_runtime(*, cloud: CloudAgentOptions | Mapping[str, Any] | None) -> None:
    if cloud is not None:
        raise TypeError(
            "cloud agent runtime is not supported; Cascade uses local agents only"
        )


def _mcp_servers_from_turn_tools(tools: list[Any] | dict[str, Any]) -> Mapping[str, Any] | None:
    if isinstance(tools, Mapping):
        return tools or None
    if isinstance(tools, list):
        if tools:
            raise TypeError(
                "RoleTurn.tools must be an MCP server mapping or an empty list; "
                f"got a non-empty list of length {len(tools)}"
            )
        return None
    raise TypeError(f"RoleTurn.tools must be a mapping or list, got {type(tools).__name__}")


def build_agent_options(turn: RoleTurn, *, api_key: str) -> AgentOptions:
    reject_cloud_runtime(cloud=None)
    custom_tools = turn.custom_tools
    mcp_servers = None if custom_tools else _mcp_servers_from_turn_tools(turn.tools)

    local_kwargs: dict[str, Any] = {
        "cwd": os.fspath(turn.cwd),
        "setting_sources": [],
    }
    if custom_tools:
        local_kwargs["custom_tools"] = custom_tools
    # Cursor's local filesystem sandbox blocks stdio MCP; planning turns need Cascade tools.
    elif turn.role in _PLANNING_ROLES and not mcp_servers:
        local_kwargs["sandbox_options"] = SandboxOptions(enabled=True)

    # tools=[] disables built-in Cursor tools only; omit when unset so custom_tools
    # and default builtins stay available for planning turns that need both.
    builtin_tools: list[str] | None = [] if not custom_tools else None

    return AgentOptions(
        api_key=api_key,
        model=turn.model_id,
        local=LocalAgentOptions(**local_kwargs),
        cloud=None,
        mcp_servers=mcp_servers,
        tools=builtin_tools,
    )


def _role_status_from_sdk(status: str) -> RoleResultStatus:
    if status == "finished":
        return "finished"
    return "error"


async def _run_cursor_role(turn: RoleTurn, *, api_key: str) -> RoleResult:
    options = build_agent_options(turn, api_key=api_key)
    reject_cloud_runtime(cloud=options.cloud)

    try:
        async with await AsyncClient.launch_bridge(
            workspace=os.fspath(turn.cwd),
            allow_api_key_env_fallback=False,
        ) as client:
            sdk_result = await AsyncAgent.prompt(
                turn.prompt,
                options,
                client=client,
            )
    except SdkCursorAgentError as err:
        raise CursorAgentError.from_sdk(err) from err

    return RoleResult(
        text=sdk_result.result or "",
        status=_role_status_from_sdk(str(sdk_result.status)),
        tool_effects=[],
    )


async def run_role(turn: RoleTurn) -> RoleResult:
    provider = parse_provider_id(turn.provider)
    validate_model_id(turn.model_id)
    reject_cloud_runtime(cloud=None)

    status = probe_provider(provider)
    if not status.installed:
        raise ProviderNotInstalledError(
            f"provider {provider!r} is not installed on this machine"
        )

    credential = resolve_credential(provider)
    if credential is None:
        raise ProviderNotAuthenticatedError(
            f"no credential configured for provider {provider!r}"
        )

    if provider == "cursor":
        return await _run_cursor_role(turn, api_key=credential.token)

    if provider == "claude":
        from cascade.agent.claude_cli import run_claude_role

        return await run_claude_role(turn, token=credential.token)

    if provider == "codex":
        from cascade.agent.codex_cli import run_codex_role

        return await run_codex_role(turn, token=credential.token)

    raise ProviderNotImplementedError(f"provider {provider!r} dispatch is not implemented yet")
