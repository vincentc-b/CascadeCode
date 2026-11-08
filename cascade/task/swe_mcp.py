"""MCP stdio server config and guarded task tool dispatch for SWE turns."""

from __future__ import annotations

import json
import sys
from collections.abc import Mapping
from pathlib import Path

from cascade.agent.mcp_project_context import project_context_payload
from typing import Any

from cursor_sdk import CustomTool, CustomToolContext

MCP_SERVER_NAME = "cascade_task"

SWE_TOOL_NAMES = (
    "message_team",
    "swe_read",
    "swe_write",
    "read_doc",
    "swe_run_tests",
    "swe_commit",
    "fail_task",
)

_SWE_TOOL_DESCRIPTIONS = {
    "message_team": "Send a durable message to the owning Feature; use a stable request_id for retries.",
    "swe_read": "Read a UTF-8 file from the active task worktree.",
    "swe_write": "Write the complete UTF-8 contents of a file in the active task worktree.",
    "read_doc": "Read this Task plan or its pinned parent Feature plan.",
    "swe_run_tests": "Run pytest in the active task worktree. For delivery, commit first, then run on the clean tree and require a green result containing final_validation.",
    "swe_commit": "Commit all allowed task worktree changes on the task branch. This invalidates prior validation; call swe_run_tests after committing before finishing.",
    "fail_task": "Block this task with a concrete reason when implementation cannot continue.",
}

_SWE_TOOL_SCHEMAS: dict[str, dict[str, Any]] = {
    "message_team": {"type": "object", "properties": {
        "recipient_id": {"type": "string"}, "body": {"type": "string"},
        "request_id": {"type": "string"}}, "required": ["recipient_id", "body", "request_id"]},
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
    "swe_run_tests": {
        "type": "object",
        "properties": {
            "cmd": {
                "type": "array",
                "items": {"type": "string"},
                'description': 'Complete argv, for example ["pytest", "tests/test_example.py", "-q"]. Commit first and rerun after any edit or commit. Omit to use configured validation.',
            }
        },
    },
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
                "project_context": project_context_payload(),
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


def build_swe_custom_tools(task_id: str, *, root: Path) -> dict[str, CustomTool]:
    """Return in-process SDK tools for Cursor SWE turns."""

    from cascade.task.registry import task_tools
    from cascade.task.wiring import load_task_tools

    load_task_tools()
    tool_names = [name for name in SWE_TOOL_NAMES if name in task_tools()]
    repo = Path(root).resolve()
    tools: dict[str, CustomTool] = {}
    for name in tool_names:
        schema = _SWE_TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}})

        def _execute(
            args: Mapping[str, Any],
            _ctx: CustomToolContext,
            *,
            tool_name: str = name,
        ) -> object:
            return dispatch_swe_tool(
                tool_name,
                dict(args),
                task_id=task_id,
                repo_root=repo,
                tool_names=tool_names,
            )

        tools[name] = CustomTool(
            description=_SWE_TOOL_DESCRIPTIONS.get(
                name, f"Guarded Cascade task tool {name}"
            ),
            input_schema=schema,
            execute=_execute,
        )
    return tools


def mcp_tool_catalog(tool_names: list[str]) -> list[dict[str, Any]]:
    tools: list[dict[str, Any]] = []
    for name in tool_names:
        schema = _SWE_TOOL_SCHEMAS.get(name, {"type": "object", "properties": {}})
        tools.append(
            {
                "name": name,
                "description": _SWE_TOOL_DESCRIPTIONS.get(name, f"Cascade task tool {name}"),
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
    from cascade.task.worktree import attach_active_task_run
    from cascade.task.wiring import load_task_tools

    repo = Path(repo_root).resolve()
    load_task_tools()
    if attach_active_task_run(task_id, root=repo) is None:
        raise RuntimeError(f"could not attach active task run for {task_id}")
    return invoke_tool(task_id, name, dict(args), root=repo)
