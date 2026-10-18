"""War Room boss chat → boss planning turn (not queue dispatch)."""

from __future__ import annotations

from pathlib import Path

from cascade.agent.graph_turn import role_skills_error_message
from cascade.boss.model_turn import (
    BOSS_CHAT_GRAPH_ID,
    BossModelReply,
    build_boss_prompt,
    produce_boss_reply,
)
from cascade.war_room.chat_store import append_transcript_message, read_messages
from cascade.watchdog.boot_model import toast_model_config_failure
from cascade.watchdog.config import ConfigError
from cascade.agent.errors import ProviderConfigError
from cascade.watchdog.model_resolve import ModelConfigError, resolve_backend


def accept_boss_chat(
    human_message: dict,
    *,
    root: Path,
    model_id: str | None,
) -> dict:
    """Run one boss lieutenant turn and append the reply to the boss chat sidecar."""

    repo = Path(root).resolve()
    prior = read_messages(BOSS_CHAT_GRAPH_ID, root=repo)
    transcript = [
        {"role": row.get("author", "unknown"), "content": row.get("body", "")} for row in prior
    ]
    transcript.append({"role": "human", "content": human_message.get("body", "")})
    model_source: str | None = None
    provider_id: str | None = None
    provider_source: str | None = None
    if model_id is None or not str(model_id).strip():
        try:
            resolved = resolve_backend("boss", None, root=repo)
        except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
            toast_model_config_failure(BOSS_CHAT_GRAPH_ID, str(exc), root=repo)
            raise
        model_id = resolved.model.model_id
        model_source = resolved.model.source
        provider_id = resolved.provider
        provider_source = resolved.provider_source
    else:
        model_id = str(model_id).strip()
        try:
            resolved = resolve_backend("boss", None, root=repo)
        except (ModelConfigError, ProviderConfigError, ConfigError) as exc:
            toast_model_config_failure(BOSS_CHAT_GRAPH_ID, str(exc), root=repo)
            raise
        provider_id = resolved.provider
        provider_source = resolved.provider_source
        if model_source is None:
            model_source = resolved.model.source
    try:
        prompt = build_boss_prompt(
            transcript,
            root=repo,
            provider_id=provider_id,
            provider_source=provider_source,
            model_id=model_id,
            model_source=model_source,
        )
    except Exception as exc:
        from cascade.watchdog.skills import SkillPathError

        if not isinstance(exc, SkillPathError):
            raise
        reply = BossModelReply(content=role_skills_error_message("boss", exc))
        return append_transcript_message(
            BOSS_CHAT_GRAPH_ID,
            author=reply.role,
            body=reply.content,
            root=repo,
        )
    if provider_id is None or not str(provider_id).strip():
        from cascade.agent.errors import ProviderConfigError

        toast_model_config_failure(
            BOSS_CHAT_GRAPH_ID,
            str(ProviderConfigError("no provider resolved for boss turn")),
            root=repo,
        )
        raise ProviderConfigError("no provider resolved for boss turn")
    reply = produce_boss_reply(
        model_id,
        prompt,
        root=repo,
        provider_id=str(provider_id).strip(),
    )
    return append_transcript_message(
        BOSS_CHAT_GRAPH_ID,
        author=reply.role,
        body=reply.content,
        root=repo,
    )
