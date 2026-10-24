"""Shared helpers for LangGraph role nodes calling planning / SWE turns."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, TypeVar

from pathlib import Path

from cascade.agent.errors import (
    CursorAgentError,
    ProviderNotAuthenticatedError,
    ProviderNotImplementedError,
    ProviderNotInstalledError,
    TurnCancelledForDrain,
)
from cascade.agent.providers import ProviderId
from cascade.agent.types import RoleId, RoleResult

if TYPE_CHECKING:
    from cascade.watchdog.model_resolve import ModelSource, ProviderSource

T = TypeVar("T")

PlanningTurnRunner = Callable[..., Awaitable[RoleResult]]


def model_id_from_state(state: dict) -> str | None:
    raw = state.get("model_id")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def clear_turn_model_override(graph, config: dict) -> None:
    """Drop a one-invoke HTTP model_id so later turns use seeded model_ids."""

    snapshot = graph.get_state(config)
    values = snapshot.values
    if not values or model_id_from_state(values) is None:
        return
    graph.update_state(config, {"model_id": None})


def provider_for_role(
    state: dict, role: RoleId
) -> tuple[ProviderId | None, ProviderSource | None]:
    """Resolve provider id and source for one role from graph checkpoint state."""

    provider_ids = state.get("provider_ids") or {}
    provider_sources = state.get("provider_sources") or {}
    raw_id = provider_ids.get(role)
    if raw_id is None:
        return None, None
    text = str(raw_id).strip()
    if not text:
        return None, None
    source = provider_sources.get(role)
    if source is not None:
        source = str(source).strip()  # type: ignore[assignment]
        if not source:
            source = None
    return text, source  # type: ignore[return-value]


def model_for_role(state: dict, role: RoleId) -> tuple[str | None, ModelSource | None]:
    """Resolve model id and source for one role from graph checkpoint state."""

    override = model_id_from_state(state)
    if override is not None:
        return override, None

    model_ids = state.get("model_ids") or {}
    model_sources = state.get("model_sources") or {}
    raw_id = model_ids.get(role)
    if raw_id is None:
        return None, None
    text = str(raw_id).strip()
    if not text:
        return None, None
    source = model_sources.get(role)
    if source is not None:
        source = str(source).strip()  # type: ignore[assignment]
        if not source:
            source = None
    return text, source  # type: ignore[return-value]


def format_model_assignment(model_id: str, source: ModelSource | None) -> str:
    if source:
        return f"Assigned model: {model_id} (source: {source})"
    return f"Assigned model: {model_id}"


def format_provider_assignment(provider_id: str, source: ProviderSource | None) -> str:
    if source:
        return f"Assigned provider: {provider_id} (source: {source})"
    return f"Assigned provider: {provider_id}"


def format_role_skill_paths(playbooks: list[dict]) -> str:
    paths = [str(entry.get("path", "")) for entry in playbooks]
    return "Role skill paths: " + ", ".join(paths)


def format_role_skills_block(playbooks: list[dict]) -> str:
    """Visible path list plus playbook bodies for one planning turn."""

    parts: list[str] = [format_role_skill_paths(playbooks)]
    for entry in playbooks:
        path = str(entry.get("path", ""))
        text = str(entry.get("text", "")).strip()
        parts.append(f"--- {path} ---\n{text}")
    return "\n\n".join(parts)


def format_turn_prompt(
    messages: list[dict],
    *,
    provider_id: str | None = None,
    provider_source: ProviderSource | None = None,
    model_id: str | None = None,
    model_source: ModelSource | None = None,
    role_skills: list[dict] | None = None,
) -> str:
    """Serialize graph messages into a single role prompt."""

    lines: list[str] = []
    for message in messages:
        role = message.get("role", "unknown")
        content = str(message.get("content", ""))
        if not content.strip():
            continue
        lines.append(f"[{role}] {content}")
    if not lines:
        body = "No prior transcript."
    else:
        body = "\n".join(lines)
    header_parts: list[str] = []
    if provider_id:
        header_parts.append(format_provider_assignment(provider_id, provider_source))
    if model_id:
        header_parts.append(format_model_assignment(model_id, model_source))
    if role_skills:
        header_parts.append(format_role_skills_block(role_skills))
    if header_parts:
        return "\n\n".join([*header_parts, body])
    return body


def prepend_role_skills(prompt: str, playbooks: list[dict]) -> str:
    """Prepend role-skill path visibility and playbook text to an existing prompt."""

    block = format_role_skills_block(playbooks)
    if not prompt.strip():
        return block
    return f"{block}\n\n{prompt}"


def latest_input(messages: list[dict]) -> dict[str, str] | None:
    for message in reversed(messages):
        role = message.get("role")
        if role == "human":
            return {"kind": "human", "text": str(message.get("content", ""))}
        if role == "event":
            return {"kind": "event", "text": str(message.get("content", ""))}
    return None


def missing_model_message(role: RoleId) -> str:
    return f"{role}: turn failed — model_id is required and must be non-blank."


def missing_provider_message(role: RoleId) -> str:
    return f"{role}: turn failed — provider is required and must be non-blank."


def provider_startup_error_message(role: RoleId, exc: BaseException) -> str:
    return f"{role}: provider startup failed — {exc}"


def role_skills_error_message(role: RoleId, exc: BaseException) -> str:
    return f"{role}: turn failed — role skill playbook error: {exc}"


def no_input_message(role: RoleId) -> str:
    return f"{role}: no new human or queue input to observe."


def startup_error_message(role: RoleId, exc: CursorAgentError) -> str:
    return f"{role}: Cursor agent startup failed — {exc.message}"


def run_error_message(role: RoleId, result: RoleResult) -> str:
    detail = result.text.strip() if result.text else "run failed"
    return f"{role}: turn failed — {detail}"


async def run_planning_role_turn(
    role: RoleId,
    state: dict,
    *,
    root: Path,
    run_turn: PlanningTurnRunner,
    **turn_kwargs: object,
) -> str:
    """Run one planning sandbox turn; return the role message body."""

    from cascade.workspace.kickoff import model_turn_authorized

    if not model_turn_authorized():
        return no_input_message(role)

    messages = state.get("messages") or []
    if latest_input(messages) is None:
        return no_input_message(role)

    model_id, model_source = model_for_role(state, role)
    if model_id is None:
        return missing_model_message(role)

    provider_id, provider_source = provider_for_role(state, role)
    if provider_id is None:
        return missing_provider_message(role)

    from cascade.watchdog.role_skills import load_role_skills_context
    from cascade.watchdog.skills import SkillPathError

    repo = Path(root).resolve()
    try:
        role_skills = load_role_skills_context(repo, role)
    except SkillPathError as exc:
        return role_skills_error_message(role, exc)

    prompt = format_turn_prompt(
        messages,
        provider_id=provider_id,
        provider_source=provider_source,
        model_id=model_id,
        model_source=model_source,
        role_skills=role_skills,
    )
    prompt = _append_planning_tool_directive(
        role,
        prompt,
        scope_id=turn_kwargs.get("feature_id") or turn_kwargs.get("epic_id"),  # type: ignore[arg-type]
        latest=latest_input(messages),
    )
    try:
        result = await run_turn(
            role,
            model_id,
            prompt,
            provider=provider_id,
            root=repo,
            **turn_kwargs,
        )
    except TurnCancelledForDrain:
        raise
    except CursorAgentError as exc:
        return startup_error_message(role, exc)
    except (
        ProviderNotInstalledError,
        ProviderNotAuthenticatedError,
        ProviderNotImplementedError,
    ) as exc:
        return provider_startup_error_message(role, exc)

    if result.status == "error":
        return run_error_message(role, result)
    return result.text


_PLANNING_TOOL_DIRECTIVE = (
    "Cascade MCP tools are the only way to change board markdown. "
    "To update an epic or feature spec, call read_doc, then write_doc with the full revised body, "
    "and record_decision for each decision-log entry. "
    "War Room chat and turn text are not the spec — never claim the plan was updated unless write_doc succeeded."
)

_EPIC_PLANNING_ROLES = frozenset({"epic_manager", "epic_architect"})
_FEATURE_PLANNING_ROLES = frozenset({"feature_lead", "feature_architect"})


_FEATURE_DISPATCH_DIRECTIVE = (
    "This feature was just dispatched; the team should start work now without waiting for a human. "
    "Break the spec into tasks: call list_children first, then call mint_task once for each task "
    "that is not minted yet, in dependency order, passing depends_on with the task ids returned "
    "by earlier mint_task calls. Finish by listing the task ids you minted."
)


def _scope_line(role: RoleId, scope_id: str) -> str:
    tier = "epic" if role in _EPIC_PLANNING_ROLES else "feature"
    return (
        f"You are {role} on the Cascade {tier} team for `{scope_id}`. "
        f"Every board tool is already bound to `{scope_id}`; pass work_id \"{scope_id}\" "
        f"to read_doc for its spec (a copy is also at ./plan.md)."
    )


def _append_planning_tool_directive(
    role: RoleId,
    prompt: str,
    *,
    scope_id: str | None = None,
    latest: dict[str, str] | None = None,
) -> str:
    if role not in _EPIC_PLANNING_ROLES and role not in _FEATURE_PLANNING_ROLES:
        return prompt
    parts = [prompt]
    if scope_id:
        parts.append(_scope_line(role, scope_id))
    parts.append(_PLANNING_TOOL_DIRECTIVE)
    if role in _EPIC_PLANNING_ROLES:
        parts.append(
            "For CommentPosted events, call read_comment with the comment_id to get the "
            "full comment body; event blocks are selected plan text, not the comment body. "
            "When the current epic plan is complete and you have reviewed its final "
            "revision, call read_doc for the epic and then sign_off_plan with its sha. "
            "Sign off only for your own role, after all requested changes and open "
            "question threads have been handled. If the other role edits the plan "
            "after your sign-off, review the new revision and sign off again."
        )
    if (
        role in _FEATURE_PLANNING_ROLES
        and latest is not None
        and latest["kind"] == "event"
        and latest["text"].startswith("FeatureReadyToPlan")
    ):
        parts.append(_FEATURE_DISPATCH_DIRECTIVE)
    return "\n\n".join(parts)


def run_coro_sync(coro: Awaitable[T]) -> T:
    """Run an async coroutine from a sync LangGraph node."""

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()
