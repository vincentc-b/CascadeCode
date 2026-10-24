"""Deterministic in-process provider for integration tests (epic_018 drain harness)."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import Any, Mapping

from cascade.agent.types import RoleResult, RoleTurn

_SCENARIO_FAST = "fast"


async def _invoke_custom_tool(tool: Any, args: Mapping[str, Any]) -> None:
    execute = getattr(tool, "execute", None)
    if execute is None:
        return
    result = execute(dict(args), None)
    if asyncio.iscoroutine(result):
        await result


async def _drain_replay_architect(turn: RoleTurn) -> RoleResult:
    tools = turn.custom_tools or {}
    if "record_decision" in tools:
        await _invoke_custom_tool(
            tools["record_decision"],
            {
                "section": "Drain replay",
                "choice": "Hold through drain",
                "rationale": "integration test",
                "honors": "epic dec_005",
            },
        )
    if "mint_feature" in tools:
        await _invoke_custom_tool(
            tools["mint_feature"],
            {"title": "Drain replay child", "depends_on": [], "body_stub": ""},
        )
    block_path = os.environ.get("CASCADE_FAKE_BLOCK_FILE", "").strip()
    if block_path:
        gate = Path(block_path)
        while gate.is_file():
            await asyncio.sleep(0.05)
    return RoleResult(text="drain-replay finished", status="finished")


async def _forever_connected(turn: RoleTurn) -> RoleResult:
    from cascade.workspace.in_flight_turn_watchdog import (
        clear_provider_transport,
        mark_provider_transport_active,
    )

    mark_provider_transport_active()
    try:
        while True:
            await asyncio.sleep(3600)
    finally:
        clear_provider_transport()
    return RoleResult(text=f"{turn.role}:stalled", status="error")


async def run_fake_role(turn: RoleTurn) -> RoleResult:
    scenario = (turn.model_id or "").strip() or _SCENARIO_FAST
    if scenario == _SCENARIO_FAST:
        return RoleResult(text=f"{turn.role}:ok", status="finished")
    if scenario == "forever-connected":
        return await _forever_connected(turn)
    if scenario == "drain-replay" and turn.role == "epic_architect":
        return await _drain_replay_architect(turn)
    return RoleResult(text=f"{turn.role}:{scenario}", status="finished")
