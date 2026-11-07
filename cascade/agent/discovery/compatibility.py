"""Non-interactive compatibility observations for the installed launch adapters."""

from __future__ import annotations

import shutil
import subprocess

from cascade.agent.cli_common import (
    claude_help_supports_turn,
    codex_help_supports_turn,
)
from cascade.agent.discovery.types import ProviderCompatibilityEvidence


def _help(binary: str, *args: str) -> str | None:
    path = shutil.which(binary)
    if path is None:
        return None
    try:
        result = subprocess.run(
            [path, *args, "--help"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return result.stdout if result.returncode == 0 else None


def probe_provider_compatibility(provider: str) -> ProviderCompatibilityEvidence:
    """Observe launch requirements without starting a model turn or exposing output.

    A CLI provider does not require the Cursor SDK; Cursor does not require a
    CLI. Those non-applicable dimensions are explicitly satisfied here.
    Missing or failed help probes remain unknown, never verified support.
    """

    if provider == "codex":
        exec_help = _help("codex", "exec")
        mcp_help = _help("codex", "mcp")
        if exec_help is None or mcp_help is None:
            return ProviderCompatibilityEvidence(sdk_compatible=True)
        cli, host = codex_help_supports_turn(exec_help=exec_help, mcp_help=mcp_help)
        return ProviderCompatibilityEvidence(
            cli_compatible=cli,
            sdk_compatible=True,
            required_tool_host_compatible=host,
        )
    if provider == "claude":
        help_text = _help("claude")
        if help_text is None:
            return ProviderCompatibilityEvidence(sdk_compatible=True)
        cli, host = claude_help_supports_turn(print_help=help_text)
        return ProviderCompatibilityEvidence(
            cli_compatible=cli,
            sdk_compatible=True,
            required_tool_host_compatible=host,
        )
    if provider == "cursor":
        try:
            from cursor_sdk import (
                AgentOptions,
                AsyncAgent,
                AsyncClient,
                CustomTool,
                CustomToolContext,
            )
        except Exception:
            return ProviderCompatibilityEvidence(cli_compatible=True)
        sdk = all((AgentOptions, AsyncAgent, AsyncClient))
        host = all((CustomTool, CustomToolContext))
        return ProviderCompatibilityEvidence(
            cli_compatible=True,
            sdk_compatible=bool(sdk),
            required_tool_host_compatible=bool(host),
        )
    return ProviderCompatibilityEvidence()
