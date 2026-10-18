"""MCP stdio server config and guarded task tool dispatch for SWE turns."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

MCP_SERVER_NAME = "cascade_task"

SWE_TOOL_NAMES = (
    "swe_read",
    "swe_write",
    "read_doc",
    "swe_run_tests",
    "swe_commit",
    "fail_task",
)

_SWE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "swe_read": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    "swe_write": {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
    },
    "read_doc": {
        "type": "object",
        "properties": {"work_id": {"type": "string"}},
        "required": ["work_id"],
    },
    "swe_run_tests": {"type": "object", "properties": {}},
    "swe_commit": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
    "fail_task": {
        "type": "object",
        "properties": {"reason": {"type": "string"}},
        "required": ["reason"],
    },
}


def build_swe_mcp_servers(
    task_id: str,
    *,
    root: Path,
    config_path: Path | None = None,
) -> dict[str, Mapping[str, Any]]:
    """Return SDK ``mcp_servers`` mapping for one SWE turn."""

    from cascade.task.registry import task_tools
    from cascade.task.wiring import load_task_tools

    load_task_tools()
    registered = set(task_tools())
    tool_names = [name for name in SWE_TOOL_NAMES if name in registered]

    repo = Path(root).resolve()
    cfg_path = config_path or (repo / ".cascade" / "task_mcp" / f"{task_id}.json")
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg_path.write_text(
        json.dumps(
            {
                "task_id": task_id,
                "repo_root": str(repo),
                "tool_names": tool_names,
            }
        ),
        encoding="utf-8",
    )

    return {
        MCP_SERVER_NAME: {
            "command": sys.executable,
            "args": ["-m", "cascade.task.swe_mcp_stdio"],
            "env": {"CASCADE_TASK_MCP_CONFIG": str(cfg_path)},
            "cwd": str(repo),
        }
    }


def mcp_tool_catalog(tool_names: list[str]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name in tool_names:
        schema = _SWE_TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}})
        tools.append(
            {
                "name": name,
                "description": f"Cascade task tool {name}",
                "inputSchema": schema,
            }
        )
    return tools


def dispatch_swe_tool(
    name: str,
    args: dict[str, Any],
    *,
    task_id: str,
    repo_root: Path,
    tool_names: list[str],
) -> object:
    if name not in tool_names:
        raise KeyError(f"tool not allowed: {name}")

    from cascade.task.graph import invoke_tool

    repo = Path(repo_root).resolve()
    return invoke_tool(task_id, name, dict(args), root=repo)
