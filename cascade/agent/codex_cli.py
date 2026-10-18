"""OpenAI Codex CLI one-shot adapter (task_074).

Non-interactive turns use ``codex exec`` (feat_015). Prompt is sent on stdin via the
documented ``-`` prompt sentinel. MCP servers are written under
``turn.cwd/.cascade_codex_home/config.toml`` with ``CODEX_HOME`` pointed there when
``codex exec --help`` documents ``-c`` / ``--config`` and ``codex mcp --help`` mentions
MCP — otherwise guarded turns fail closed with ``ProviderToolHostError``.
"""

from __future__ import annotations

import os
from pathlib import Path

from cascade.agent.cli_common import (
    assert_codex_non_interactive,
    codex_help_supports_turn,
    mcp_servers_from_turn_tools,
    read_cli_help,
    require_planning_mcp_tools,
    run_subprocess_turn,
    turn_needs_mcp_tools,
    write_codex_mcp_config,
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
            f"{CODEX_BINARY} exec --help does not document non-interactive approval flags"
        )

    argv: list[str] = [
        CODEX_BINARY,
        "exec",
        "--color",
        "never",
        "--ask-for-approval",
        "never",
    ]
    if turn.model_id.strip():
        argv.extend(["--model", turn.model_id])
    argv.append("-")
    assert_codex_non_interactive(argv)
    return argv


async def run_codex_role(turn: RoleTurn, *, token: str) -> RoleResult:
    require_planning_mcp_tools(turn)
    exec_help = await _codex_exec_help()
    mcp_help = await _codex_mcp_help()
    exec_ok, mcp_ok = codex_help_supports_turn(exec_help=exec_help, mcp_help=mcp_help)

    servers = mcp_servers_from_turn_tools(turn.tools)
    codex_home: Path | None = None
    if turn_needs_mcp_tools(turn):
        if not servers:
            raise ProviderToolHostError("planning or SWE turn requires MCP tools but none were supplied")
        if not (exec_ok and mcp_ok):
            raise ProviderToolHostError(
                f"{CODEX_BINARY} cannot load Cascade MCP in non-interactive exec mode "
                "(fail closed; confirm `codex exec --help` and `codex mcp --help` on your machine)"
            )
        codex_home = write_codex_mcp_config(turn, servers)

    argv = build_codex_argv(turn, exec_help=exec_help)
    env = {"OPENAI_API_KEY": token}
    if codex_home is not None:
        env["CODEX_HOME"] = os.fspath(codex_home)
    return await run_subprocess_turn(argv=argv, cwd=turn.cwd, prompt=turn.prompt, env=env)
