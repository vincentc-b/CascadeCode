"""Boss lieutenant model turn (planning sandbox + adapter; not queue dispatch)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from cascade.agent import CursorAgentError
from cascade.agent.graph_turn import (
    format_turn_prompt,
    missing_model_message,
    prepend_role_skills,
    role_skills_error_message,
    run_coro_sync,
    run_error_message,
    startup_error_message,
)
BOSS_CHAT_GRAPH_ID = "boss"


@dataclass(frozen=True)
class BossModelReply:
    """One boss role message suitable for chat sidecar or API responses."""

    content: str
    role: str = "boss"


def build_boss_prompt(
    messages: list[dict],
    *,
    root: Path,
    provider_id: str | None = None,
    provider_source: str | None = None,
    model_id: str | None = None,
    model_source: str | None = None,
) -> str:
    from cascade.watchdog.role_skills import load_role_skills_context

    repo = Path(root).resolve()
    role_skills = load_role_skills_context(repo, "boss")
    return format_turn_prompt(
        messages,
        provider_id=provider_id,
        provider_source=provider_source,  # type: ignore[arg-type]
        model_id=model_id,
        model_source=model_source,  # type: ignore[arg-type]
        role_skills=role_skills,
    )


def produce_boss_reply(
    model_id: str | None,
    prompt: str,
    *,
    root: Path,
    provider_id: str,
) -> BossModelReply:
    """Run one boss planning turn; surface startup and run errors in content."""

    repo = Path(root).resolve()
    if model_id is None or not str(model_id).strip():
        return BossModelReply(content=missing_model_message("boss"))

    if "Role skill paths:" not in prompt:
        from cascade.watchdog.role_skills import load_role_skills_context
        from cascade.watchdog.skills import SkillPathError

        try:
            role_skills = load_role_skills_context(repo, "boss")
        except SkillPathError as exc:
            return BossModelReply(content=role_skills_error_message("boss", exc))
        prompt = prepend_role_skills(prompt, role_skills)

    from cascade.agent.planning_turn import run_boss_planning_turn

    try:
        result = run_coro_sync(
            run_boss_planning_turn(
                str(model_id).strip(),
                prompt,
                provider=provider_id,  # type: ignore[arg-type]
                root=repo,
            )
        )
    except CursorAgentError as exc:
        return BossModelReply(content=startup_error_message("boss", exc))

    if result.status == "error":
        return BossModelReply(content=run_error_message("boss", result))
    return BossModelReply(content=result.text)
