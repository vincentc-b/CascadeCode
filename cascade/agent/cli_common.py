"""Shared helpers for Claude/Codex one-shot CLI adapters (task_074)."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shlex
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from cascade.agent.errors import ProviderCliError, ProviderCliTimeoutError
from cascade.agent.turn_registry import set_current_turn_pid
from cascade.agent.types import RoleResult, RoleTurn

PLANNING_ROLES: frozenset[str] = frozenset(
    {
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "boss",
    }
)

DEFAULT_CLI_TIMEOUT_SEC = 3600.0

_help_cache: dict[tuple[str, tuple[str, ...]], str] = {}


def turn_needs_mcp_tools(turn: RoleTurn) -> bool:
    tools = turn.tools
    if isinstance(tools, list):
        return bool(tools)
    if isinstance(tools, Mapping):
        return bool(tools)
    raise TypeError(f"RoleTurn.tools must be a mapping or list, got {type(tools).__name__}")


def require_planning_mcp_tools(turn: RoleTurn) -> None:
    """Planning and boss roles must host Cascade MCP tools before CLI spawn."""

    from cascade.agent.errors import ProviderToolHostError

    if turn.role not in PLANNING_ROLES:
        return
    servers = mcp_servers_from_turn_tools(turn.tools)
    if not servers:
        raise ProviderToolHostError(
            "planning or boss turn requires MCP tools but none were supplied"
        )


def mcp_servers_from_turn_tools(tools: list[Any] | dict[str, Any]) -> dict[str, Mapping[str, Any]] | None:
    if isinstance(tools, Mapping):
        return dict(tools) if tools else None
    if isinstance(tools, list):
        if tools:
            raise TypeError(
                "RoleTurn.tools must be an MCP server mapping or an empty list; "
                f"got a non-empty list of length {len(tools)}"
            )
        return None
    raise TypeError(f"RoleTurn.tools must be a mapping or list, got {type(tools).__name__}")


def sdk_mcp_to_claude_json(servers: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    """Claude Code ``--mcp-config`` document (``mcpServers`` key)."""

    out: dict[str, Any] = {}
    for name, spec in servers.items():
        entry: dict[str, Any] = {"command": spec["command"]}
        if args := spec.get("args"):
            entry["args"] = list(args)
        if env := spec.get("env"):
            entry["env"] = dict(env)
        if cwd := spec.get("cwd"):
            entry["cwd"] = cwd
        out[name] = entry
    return {"mcpServers": out}


def write_claude_mcp_config(turn: RoleTurn, servers: Mapping[str, Mapping[str, Any]]) -> Path:
    path = turn.cwd / ".cascade_claude_mcp.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sdk_mcp_to_claude_json(servers), indent=2) + "\n", encoding="utf-8")
    return path


def codex_mcp_config_overrides(
    servers: Mapping[str, Mapping[str, Any]],
) -> list[str]:
    """Return Codex ``-c`` values for MCP servers without replacing CODEX_HOME.

    Keeping the operator's CODEX_HOME is required for CLI-session authentication.
    Values are encoded as TOML fragments; JSON strings and arrays are valid TOML
    values for the scalar data accepted by Cascade's MCP server mapping.
    """

    overrides: list[str] = []
    for name, spec in servers.items():
        server_name = str(name)
        if re.fullmatch(r"[A-Za-z0-9_-]+", server_name) is None:
            raise ValueError(f"invalid Codex MCP server name: {server_name!r}")
        # Codex's dotted override parser treats quote characters in a path
        # segment literally (creating a server named '"cascade"'), unlike a
        # TOML document parser. MCP server names are therefore restricted to
        # bare-key characters here.
        prefix = f"mcp_servers.{server_name}"
        overrides.append(f"{prefix}.enabled=true")
        overrides.append(f"{prefix}.required=true")
        # Cascade tools enforce their own tier/work-id guards. CLI turns are
        # non-interactive, so prompting here would make every tool unusable.
        overrides.append(f'{prefix}.default_tools_approval_mode="approve"')
        overrides.append(f"{prefix}.command={json.dumps(str(spec['command']))}")
        args = [str(arg) for arg in spec.get("args") or []]
        overrides.append(f"{prefix}.args={json.dumps(args)}")
        env = spec.get("env") or {}
        if env:
            pairs = ", ".join(
                f"{json.dumps(str(key))} = {json.dumps(str(value))}"
                for key, value in env.items()
            )
            overrides.append(f"{prefix}.env={{ {pairs} }}")
        cwd = spec.get("cwd")
        if cwd:
            overrides.append(f"{prefix}.cwd={json.dumps(str(cwd))}")
    return overrides


async def read_cli_help(binary: str, *prefix: str) -> str:
    key = (binary, prefix)
    if key in _help_cache:
        return _help_cache[key]
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *prefix,
            "--help",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as err:
        raise ProviderCliError(f"failed to spawn {binary!r} for --help: {err}") from err
    stdout, _ = await proc.communicate()
    text = stdout.decode(errors="replace")
    _help_cache[key] = text
    return text


def claude_help_supports_turn(*, print_help: str) -> tuple[bool, bool]:
    """Return (print_mode_ok, mcp_config_ok) from cached ``claude --help`` text."""

    lower = print_help.lower()
    print_ok = "-p" in print_help or "--print" in lower
    mcp_ok = "--mcp-config" in lower
    return print_ok, mcp_ok


def codex_help_supports_turn(*, exec_help: str, mcp_help: str) -> tuple[bool, bool]:
    """Return (exec_ok, mcp_config_ok) from ``codex exec --help`` and ``codex mcp --help``."""

    has_config = (
        "--config" in exec_help
        or "-c," in exec_help
        or " -c " in exec_help
        or exec_help.lstrip().startswith("-c,")
    )
    # Use the exec-scoped config override for the approval policy.  Codex CLI
    # versions disagree about whether ``--ask-for-approval`` is an exec option
    # or a root option, while ``codex exec -c key=value`` is the interface we
    # already require for MCP configuration.
    exec_ok = bool(exec_help.strip()) and has_config
    mcp_ok = "mcp" in mcp_help.lower() and has_config
    return exec_ok, mcp_ok


def assert_claude_non_interactive(argv: list[str]) -> None:
    if "-p" not in argv and "--print" not in argv:
        raise ProviderCliError(
            "interactive Claude CLI invocation is a programming error; use print mode (-p)"
        )


def assert_codex_non_interactive(argv: list[str]) -> None:
    if len(argv) < 2 or argv[0] != "codex" or argv[1] != "exec":
        raise ProviderCliError(
            "interactive Codex CLI invocation is a programming error; use `codex exec`"
        )


async def run_subprocess_turn(
    *,
    argv: list[str],
    cwd: Path,
    prompt: str,
    env: Mapping[str, str] | None = None,
    timeout: float = DEFAULT_CLI_TIMEOUT_SEC,
) -> RoleResult:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=os.fspath(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged,
        )
    except OSError as err:
        raise ProviderCliError(f"failed to spawn CLI: {err}") from err

    if proc.pid is not None:
        set_current_turn_pid(proc.pid)

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(prompt.encode("utf-8")),
            timeout=timeout,
        )
    except asyncio.TimeoutError as err:
        proc.kill()
        await proc.wait()
        raise ProviderCliTimeoutError(f"CLI subprocess timed out after {timeout}s") from err

    out = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")
    if proc.returncode == 0:
        return RoleResult(text=out, status="finished", tool_effects=[])
    combined = out
    if err_text.strip():
        combined = (combined + "\n" + err_text).strip() if combined else err_text
    if not combined.strip():
        combined = f"CLI exited with code {proc.returncode}"
    return RoleResult(text=combined, status="error", tool_effects=[])


def format_argv_for_tests(argv: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in argv)
