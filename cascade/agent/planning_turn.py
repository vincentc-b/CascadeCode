"""Public helpers: owned team worktrees + MCP + ``run_role`` planning roles."""

from __future__ import annotations

import json
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
from cascade.agent.recovery_contract import ProviderRecoveryLaunch
from cascade.agent.types import ProviderPermissionMode, RoleId, RoleResult, RoleTurn
from cascade.board.parse import parse_doc
from cascade.planning_dependency_tools import refresh_planning_dependencies

_EPIC_ROLES = frozenset({"epic_manager", "epic_architect"})
_FEATURE_ROLES = frozenset({"feature_lead", "feature_architect"})

_DEPENDENCY_PROJECTION_HEADING = (
    "Authoritative dependency status projection "
    "(read-only; does not grant content access or authorize actions):"
)
_DEPENDENCY_PROJECTION_BOUNDARY = (
    "A spec read denied by scoped authorization is content_access_denied "
    "independently of this dependency outcome. Treat outcome/reason fields as "
    "machine-readable and explanation fields as guidance only. Normal planning "
    "actions, including mint_feature, recheck authoritative dependency status: "
    "dependency_unmet means a known prerequisite is incomplete, while "
    "dependency_status_unavailable means status could not be established. "
    "For missing_manifest, the owning Epic Manager or Architect must use "
    "read_dependency_manifest then write_dependency_manifest with expected_revision=0 "
    "and complete target environment identity. Declare none_required=true and "
    "dependencies=[] only when no software is needed. Declaration grants no install authority."
)


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
    recovery: ProviderRecoveryLaunch | None = None,
) -> RoleResult:
    if role not in _EPIC_ROLES:
        raise ValueError(f"not an epic planning role: {role}")
    validate_model_id(model_id)
    repo = Path(root).resolve()
    from cascade.workspace.integration_worktree import doc_filesystem_root
    from cascade.watchdog.config import provider_permission_mode

    workspace = doc_filesystem_root(epic_id, trunk=repo).resolve()
    paths = collect_epic_readable_paths(epic_id, root=repo)
    turn_prompt = _with_dependency_projection(prompt, owner_path=paths[0], root=repo)
    turn_prompt = _with_architecture_context(turn_prompt, epic_id, root=repo)
    scratch = materialize_scratch(repo, paths, tier="epic")
    return await _run_sandbox_turn(
        role=role,
        provider=provider,
        model_id=model_id,
        prompt=turn_prompt,
        reasoning_level=reasoning_level,
        flex_mode=flex_mode,
        recovery=recovery,
        sandbox=PlanningSandbox(
            scratch_dir=scratch,
            repo_root=repo,
            tier="epic",
            scope_id=epic_id,
            role=role,
            workspace_dir=workspace,
        ),
        permission_mode=provider_permission_mode(repo, provider),
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
    recovery: ProviderRecoveryLaunch | None = None,
) -> RoleResult:
    if role not in _FEATURE_ROLES:
        raise ValueError(f"not a feature planning role: {role}")
    validate_model_id(model_id)
    repo = Path(root).resolve()
    from cascade.feature.checkout import feature_checkout_root
    from cascade.watchdog.config import provider_permission_mode

    workspace = feature_checkout_root(feature_id, trunk=repo).resolve()
    paths = collect_feature_readable_paths(feature_id, root=repo)
    turn_prompt = _with_dependency_projection(prompt, owner_path=paths[0], root=repo)
    turn_prompt = _with_architecture_context(turn_prompt, feature_id, root=repo)
    scratch = materialize_scratch(repo, paths, tier="feature")
    return await _run_sandbox_turn(
        role=role,
        provider=provider,
        model_id=model_id,
        prompt=turn_prompt,
        reasoning_level=reasoning_level,
        flex_mode=flex_mode,
        recovery=recovery,
        sandbox=PlanningSandbox(
            scratch_dir=scratch,
            repo_root=repo,
            tier="feature",
            scope_id=feature_id,
            role=role,
            workspace_dir=workspace,
        ),
        permission_mode=provider_permission_mode(repo, provider),
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
    recovery: ProviderRecoveryLaunch | None = None,
    permission_mode: ProviderPermissionMode = "default",
) -> RoleResult:
    scratch = sandbox.scratch_dir
    cwd = sandbox.turn_cwd
    effects_path = scratch / ".cascade_effects.jsonl"
    collector = ToolEffectCollector()
    if provider in ("cursor", "fake"):
        turn = RoleTurn(
            role=role,
            provider=provider,
            model_id=model_id,
            prompt=_recovery_prompt(prompt, recovery),
            cwd=cwd,
            tools=[],
            custom_tools=build_planning_custom_tools(sandbox, collector),
            reasoning_level=reasoning_level,
            flex_mode=flex_mode,
            recovery=recovery,
            permission_mode=permission_mode,
        )
    else:
        turn = RoleTurn(
            role=role,
            provider=provider,
            model_id=model_id,
            prompt=_recovery_prompt(prompt, recovery),
            cwd=cwd,
            tools=build_planning_mcp_servers(sandbox),
            reasoning_level=reasoning_level,
            flex_mode=flex_mode,
            recovery=recovery,
            permission_mode=permission_mode,
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
            recovery=result.recovery,
        )
    finally:
        teardown_scratch(scratch)


def _recovery_prompt(prompt: str, recovery: ProviderRecoveryLaunch | None) -> str:
    """Give every provider the exact same recovery identity and evidence."""

    if recovery is None:
        return prompt
    return f"{recovery.prompt_block()}\n\n{prompt}"


def _with_dependency_projection(prompt: str, *, owner_path: Path, root: Path) -> str:
    """Append lifecycle-only dependency context from the current owning spec."""

    owner = parse_doc(owner_path).meta
    projection = refresh_planning_dependencies(owner.id, root=root)
    payload = json.dumps(projection, sort_keys=True, separators=(",", ":"))
    return "\n\n".join(
        (prompt, _DEPENDENCY_PROJECTION_HEADING, payload, _DEPENDENCY_PROJECTION_BOUNDARY)
    )


def _with_architecture_context(prompt: str, work_id: str, *, root: Path) -> str:
    from cascade.board.context import get_project_context
    from cascade.workspace.architecture_context import planning_context_prompt
    from cascade.workspace.types import ProjectContext

    project = get_project_context() or ProjectContext.colocated(root)
    return f"{prompt}\n\n{planning_context_prompt(project, work_id)}"
