"""OpenAI Codex CLI one-shot adapter (task_074).

Non-interactive turns use ``codex exec`` (feat_015). Prompt is sent on stdin via the
documented ``-`` prompt sentinel. MCP servers are supplied as per-turn ``-c`` overrides
so the operator's ``CODEX_HOME`` remains available for CLI-session authentication.
When ``codex exec --help`` does not document configuration overrides or ``codex mcp
--help`` does not mention MCP, guarded turns fail closed with ``ProviderToolHostError``.
"""

from __future__ import annotations

from cascade.agent.cli_common import (
    assert_codex_non_interactive,
    codex_mcp_config_overrides,
    codex_help_supports_turn,
    mcp_servers_from_turn_tools,
    read_cli_help,
    require_planning_mcp_tools,
    run_subprocess_turn,
    turn_needs_mcp_tools,
)
from cascade.agent.errors import ProviderCliError, ProviderToolHostError
from cascade.agent.types import RoleResult, RoleTurn

CODEX_BINARY = "codex"


async def _codex_exec_help() -> str:
    return await read_cli_help(CODEX_BINARY, "exec")


async def _codex_mcp_help() -> str:
    return await read_cli_help(CODEX_BINARY, "mcp")


def build_codex_argv(
    turn: RoleTurn,
    *,
    exec_help: str,
) -> list[str]:
    exec_ok, _mcp_ok = codex_help_supports_turn(exec_help=exec_help, mcp_help=exec_help)
    if not exec_ok:
        raise ProviderCliError(
            f"{CODEX_BINARY} exec --help does not document inline configuration overrides"
        )

    argv: list[str] = [
        CODEX_BINARY,
        "exec",
        "--color",
        "never",
        "--config",
        'approval_policy="never"',
    ]
    # Codex exec defaults to a restricted sandbox. SWE turns edit only their
    # Task worktree; planning turns continue to use guarded MCP tools.
    if turn.role == "swe":
        argv.extend(["--config", 'sandbox_mode="workspace-write"'])
    if turn.model_id.strip():
        argv.extend(["--model", turn.model_id])
    if turn.flex_mode is True:
        argv.extend(["--config", 'service_tier="flex"'])
    if turn.reasoning_level:
        argv.extend(["--config", f'model_reasoning_effort="{turn.reasoning_level}"'])
    servers = mcp_servers_from_turn_tools(turn.tools)
    if servers:
        if "--ignore-user-config" in exec_help:
            argv.append("--ignore-user-config")
        for override in codex_mcp_config_overrides(servers):
            argv.extend(["--config", override])
    # Planning turns run in a deliberately minimal scratch directory rather
    # than a Git checkout.  Newer Codex releases reject such directories by
    # default; older releases that do not advertise the flag did not require
    # it, so keep this capability-gated.
    if "--skip-git-repo-check" in exec_help:
        argv.append("--skip-git-repo-check")
    argv.append("-")
    assert_codex_non_interactive(argv)
    return argv


async def run_codex_role(turn: RoleTurn, *, token: str) -> RoleResult:
    require_planning_mcp_tools(turn)
    exec_help = await _codex_exec_help()
    mcp_help = await _codex_mcp_help()
    exec_ok, mcp_ok = codex_help_supports_turn(exec_help=exec_help, mcp_help=mcp_help)

    servers = mcp_servers_from_turn_tools(turn.tools)
    if turn_needs_mcp_tools(turn):
        if not servers:
            raise ProviderToolHostError("planning or SWE turn requires MCP tools but none were supplied")
        if not (exec_ok and mcp_ok):
            raise ProviderToolHostError(
                f"{CODEX_BINARY} cannot load Cascade MCP in non-interactive exec mode "
                "(fail closed; confirm `codex exec --help` and `codex mcp --help` on your machine)"
            )

    argv = build_codex_argv(turn, exec_help=exec_help)
    env = {"OPENAI_API_KEY": token}
    return await run_subprocess_turn(argv=argv, cwd=turn.cwd, prompt=turn.prompt, env=env)
