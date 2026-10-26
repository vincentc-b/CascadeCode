"""Public helpers: scratch sandbox + MCP + ``run_role`` for planning roles."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.adapter import run_role, validate_model_id
from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    build_planning_custom_tools,
    build_planning_mcp_servers,
    merge_tool_effects_from_file,
)
from cascade.agent.planning_sandbox import (
    PlanningSandbox,
    collect_boss_readable_paths,
    collect_epic_readable_paths,
    collect_feature_readable_paths,
    materialize_scratch,
    teardown_scratch,
)
from cascade.agent.providers import ProviderId
from cascade.agent.types import RoleId, RoleResult, RoleTurn

_EPIC_ROLES = frozenset({"epic_manager", "epic_architect"})
_FEATURE_ROLES = frozenset({"feature_lead", "feature_architect"})


async def run_epic_planning_turn(
    role: RoleId,
    model_id: str,
    prompt: str,
    *,
    provider: ProviderId,
    epic_id: str,
    root: Path,
    reasoning_level: str | None = None,
    flex_mode: bool | None = None,
) -> RoleResult:
    if role not in _EPIC_ROLES:
        raise ValueError(f"not an epic planning role: {role}")
    validate_model_id(model_id)
    repo = Path(root).resolve()
    paths = collect_epic_readable_paths(epic_id, root=repo)
    scratch = materialize_scratch(repo, paths, tier="epic")
    return await _run_sandbox_turn(
        role=role,
        provider=provider,
        model_id=model_id,
        prompt=prompt,
        reasoning_level=reasoning_level,
        flex_mode=flex_mode,
        sandbox=PlanningSandbox(
            scratch_dir=scratch,
            repo_root=repo,
            tier="epic",
            scope_id=epic_id,
            role=role,
        ),
    )


async def run_feature_planning_turn(
    role: RoleId,
    model_id: str,
    prompt: str,
    *,
    provider: ProviderId,
    feature_id: str,
    root: Path,
    reasoning_level: str | None = None,
    flex_mode: bool | None = None,
) -> RoleResult:
    if role not in _FEATURE_ROLES:
        raise ValueError(f"not a feature planning role: {role}")
    validate_model_id(model_id)
    repo = Path(root).resolve()
    paths = collect_feature_readable_paths(feature_id, root=repo)
    scratch = materialize_scratch(repo, paths, tier="feature")
    return await _run_sandbox_turn(
        role=role,
        provider=provider,
        model_id=model_id,
        prompt=prompt,
        reasoning_level=reasoning_level,
        flex_mode=flex_mode,
        sandbox=PlanningSandbox(
            scratch_dir=scratch,
            repo_root=repo,
            tier="feature",
            scope_id=feature_id,
            role=role,
        ),
    )


async def run_boss_planning_turn(
    model_id: str,
    prompt: str,
    *,
    provider: ProviderId,
    root: Path,
) -> RoleResult:
    validate_model_id(model_id)
    repo = Path(root).resolve()
    paths = collect_boss_readable_paths(root=repo)
    scratch = materialize_scratch(repo, paths, tier="boss")
    return await _run_sandbox_turn(
        role="boss",
        provider=provider,
        model_id=model_id,
        prompt=prompt,
        sandbox=PlanningSandbox(
            scratch_dir=scratch,
            repo_root=repo,
            tier="boss",
            scope_id=None,
        ),
    )


async def _run_sandbox_turn(
    *,
    role: RoleId,
    provider: ProviderId,
    model_id: str,
    prompt: str,
    sandbox: PlanningSandbox,
    reasoning_level: str | None = None,
    flex_mode: bool | None = None,
) -> RoleResult:
    scratch = sandbox.scratch_dir
    effects_path = scratch / ".cascade_effects.jsonl"
    collector = ToolEffectCollector()
    if provider in ("cursor", "fake"):
        turn = RoleTurn(
            role=role,
            provider=provider,
            model_id=model_id,
            prompt=prompt,
            cwd=scratch,
            tools=[],
            custom_tools=build_planning_custom_tools(sandbox, collector),
            reasoning_level=reasoning_level,
            flex_mode=flex_mode,
        )
    else:
        turn = RoleTurn(
            role=role,
            provider=provider,
            model_id=model_id,
            prompt=prompt,
            cwd=scratch,
            tools=build_planning_mcp_servers(sandbox),
            reasoning_level=reasoning_level,
            flex_mode=flex_mode,
        )
    try:
        result = await run_role(turn)
        if provider in ("cursor", "fake"):
            tool_effects = list(collector.effects)
        else:
            tool_effects = merge_tool_effects_from_file(effects_path)
        return RoleResult(
            text=result.text,
            status=result.status,
            tool_effects=tool_effects,
        )
    finally:
        teardown_scratch(scratch)
