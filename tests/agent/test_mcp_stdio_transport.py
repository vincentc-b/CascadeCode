from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("module", "env_key", "config"),
    [
        (
            "cascade.agent.mcp_stdio",
            "CASCADE_MCP_CONFIG",
            {"tier": "epic", "scope_id": "epic_001", "tool_names": ["read_doc"]},
        ),
        (
            "cascade.task.swe_mcp_stdio",
            "CASCADE_TASK_MCP_CONFIG",
            {"task_id": "task_001", "tool_names": ["report_completion"]},
        ),
    ],
)
def test_stdio_servers_speak_jsonl(
    tmp_path: Path,
    module: str,
    env_key: str,
    config: dict[str, object],
) -> None:
    config_path = tmp_path / "mcp.json"
    config_path.write_text(
        json.dumps({**config, "repo_root": str(tmp_path)}),
        encoding="utf-8",
    )
    messages = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    ]
    payload = "".join(json.dumps(message) + "\n" for message in messages)
    completed = subprocess.run(
        [sys.executable, "-m", module],
        input=payload,
        text=True,
        capture_output=True,
        env={**os.environ, env_key: str(config_path)},
        check=True,
        timeout=10,
    )
    responses = [json.loads(line) for line in completed.stdout.splitlines()]
    assert [response["id"] for response in responses] == [1, 2]
    assert responses[1]["result"]["tools"][0]["name"] == config["tool_names"][0]
