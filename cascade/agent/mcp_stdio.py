"""Minimal stdio MCP server forwarding tool calls to guarded Cascade tools."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    dispatch_planning_tool,
    mcp_tool_catalog,
)
from cascade.agent.mcp_transport import read_message, write_message
from cascade.agent.planning_sandbox import PlanningTier


def main() -> None:
    config_path = os.environ.get("CASCADE_MCP_CONFIG")
    if not config_path:
        raise SystemExit("CASCADE_MCP_CONFIG is required")
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    tier: PlanningTier = config["tier"]
    scope_id = config.get("scope_id")
    repo_root = Path(config["repo_root"])
    tool_names: list[str] = list(config.get("tool_names") or [])
    collector = ToolEffectCollector()

    while True:
        incoming = read_message()
        if incoming is None:
            break
        message, framing = incoming
        response = _handle_message(message, tier, scope_id, repo_root, tool_names, collector)
        if response is not None:
            write_message(response, framing=framing)


def _handle_message(
    message: dict[str, Any],
    tier: PlanningTier,
    scope_id: str | None,
    repo_root: Path,
    tool_names: list[str],
    collector: ToolEffectCollector,
) -> dict[str, Any] | None:
    msg_id = message.get("id")
    method = message.get("method")
    params = message.get("params") or {}

    if method == "notifications/initialized":
        return None
    if method == "initialize":
        return _reply(
            msg_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "cascade-planning", "version": "0.0.1"},
            },
        )
    if method == "tools/list":
        return _reply(msg_id, {"tools": mcp_tool_catalog(tier, tool_names)})
    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not isinstance(name, str):
            return _error(msg_id, -32602, "tools/call requires name")
        if tool_names and name not in tool_names:
            return _error(msg_id, -32602, f"tool not allowed: {name}")
        try:
            result = dispatch_planning_tool(
                tier,
                name,
                dict(arguments),
                scope_id=scope_id,
                repo_root=repo_root,
                collector=collector,
            )
            payload = json.dumps(result, default=str)
        except Exception as exc:  # noqa: BLE001 — surface tool failures to the agent
            return _reply(
                msg_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        return _reply(
            msg_id,
            {"content": [{"type": "text", "text": payload}], "isError": False},
        )
    if msg_id is None:
        return None
    return _error(msg_id, -32601, f"Method not found: {method}")


def _reply(msg_id: object, result: object) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: object, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": msg_id,
        "error": {"code": code, "message": message},
    }


if __name__ == "__main__":
    main()
