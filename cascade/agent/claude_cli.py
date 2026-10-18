"""Claude Code one-shot CLI adapter (task_074).

Argv locked against Anthropic CLI reference (not verified on this CI host; binaries
may be absent). Print mode uses ``-p``; guarded tools use ``--strict-mcp-config`` and
``--mcp-config`` when ``claude --help`` documents those flags. Prompt is sent on stdin
with a trailing ``-`` argument when supported, otherwise appended as the final argv word.
"""

from __future__ import annotations

import os
from typing import Any

from cascade.agent.cli_common import (
    assert_claude_non_interactive,
    claude_help_supports_turn,
    mcp_servers_from_turn_tools,
    read_cli_help,
    require_planning_mcp_tools,
    run_subprocess_turn,
    turn_needs_mcp_tools,
    write_claude_mcp_config,
)
from cascade.agent.errors import ProviderCliError, ProviderToolHostError
from cascade.agent.types import RoleResult, RoleTurn

CLAUDE_BINARY = "claude"


async def _claude_help() -> str:
    return await read_cli_help(CLAUDE_BINARY)


def build_claude_argv(
    turn: RoleTurn,
    *,
    mcp_config_path: str | None,
    print_help: str,
    use_stdin_prompt: bool = True,
) -> list[str]:
    print_ok, mcp_ok = claude_help_supports_turn(print_help=print_help)
    if not print_ok:
        raise ProviderCliError(
            f"{CLAUDE_BINARY} --help does not document print mode (-p / --print)"
        )

    argv: list[str] = [
        CLAUDE_BINARY,
        "-p",
        "--output-format",
        "text",
    ]
    if mcp_config_path is not None:
        if not mcp_ok:
            raise ProviderToolHostError(
                f"{CLAUDE_BINARY} --help does not document --mcp-config; "
                "cannot run a guarded planning or SWE turn"
            )
        argv.extend(["--strict-mcp-config", "--mcp-config", mcp_config_path])

    if turn.model_id.strip():
        argv.extend(["--model", turn.model_id])

    if use_stdin_prompt:
        argv.append("-")
    else:
        argv.append(turn.prompt)
    assert_claude_non_interactive(argv)
    return argv


async def run_claude_role(turn: RoleTurn, *, token: str) -> RoleResult:
    require_planning_mcp_tools(turn)
    print_help = await _claude_help()
    servers = mcp_servers_from_turn_tools(turn.tools)
    mcp_path: str | None = None
    if turn_needs_mcp_tools(turn):
        if not servers:
            raise ProviderToolHostError("planning or SWE turn requires MCP tools but none were supplied")
        mcp_path = os.fspath(write_claude_mcp_config(turn, servers))

    argv = build_claude_argv(turn, mcp_config_path=mcp_path, print_help=print_help)
    env = {"ANTHROPIC_API_KEY": token}
    return await run_subprocess_turn(argv=argv, cwd=turn.cwd, prompt=turn.prompt, env=env)
