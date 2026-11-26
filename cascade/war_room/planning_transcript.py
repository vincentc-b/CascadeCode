"""Append epic/feature planning role lines to War Room chat sidecars."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

from cascade.comments.types import AGENT_AUTHORS
from cascade.war_room.chat_store import (
    append_transcript_message,
    mark_message_legacy_unknown,
    read_messages,
)

_log = logging.getLogger(__name__)

_SKIP_BODY_PREFIXES = (
    "no input",
    "model_id is required",
)

_FAILURE_MARKERS = (
    "turn failed",
    "provider startup failed",
    "provider blocked",
    "agent startup failed",
)


def _presentable_message(role: str, body: str) -> tuple[str, str] | None:
    if role not in AGENT_AUTHORS or not body:
        return None
    lowered = body.lower()
    if any(marker in lowered for marker in _FAILURE_MARKERS):
        # CLI failure output often contains the entire prompt and provider
        # diagnostics.  Show a useful, bounded message without publishing it.
        if "unsupported service_tier: flex" in lowered:
            detail = "The selected model rejected Flex service tier. Disable Flex or choose a compatible model, then retry."
        else:
            detail = "The agent turn failed. Check provider settings and retry."
        return "system", f"{role.replace('_', ' ').title()}: {detail}"
    if any(lowered.startswith(prefix) for prefix in _SKIP_BODY_PREFIXES):
        return None
    return role, body


def append_planning_turn_to_chat(
    graph_id: str,
    new_messages: list[dict],
    *,
    root,
    checkpoint_config: Mapping[str, object] | None = None,
    message_offset: int = 0,
    provenance: str = "direct",
) -> None:
    """Mirror manager/architect (or feature roles) output into the graph chat JSONL."""

    checkpoint_id = _checkpoint_id(checkpoint_config)
    for relative_ordinal, msg in enumerate(new_messages):
        role = str(msg.get("role") or "")
        body = str(msg.get("content") or "").strip()
        presentable = _presentable_message(role, body)
        if presentable is None:
            continue
        author, text = presentable
        append_transcript_message(
            graph_id,
            author=author,
            body=text,
            root=root,
            source_key=_role_reply_source_key(
                graph_id,
                msg,
                checkpoint_id=checkpoint_id,
                message_ordinal=message_offset + relative_ordinal,
            ),
            occurred_at=_message_time(msg),
            provenance=provenance,
            metadata={
                "kind": "role_reply",
                "checkpoint_id": checkpoint_id,
                "message_ordinal": message_offset + relative_ordinal,
                "checkpoint_message_id": _message_id(msg),
            },
        )


def sync_planning_transcript_to_chat(graph_id: str, *, root: Path) -> None:
    """Backfill agent lines from the graph checkpoint into the chat JSONL (idempotent)."""

    tier = _tier_for_graph_id(graph_id)
    if tier is None:
        return
    try:
        graph_messages, checkpoint_config = _load_graph_messages(graph_id, tier, root=root)
    except Exception:
        _log.exception("failed to load planning graph messages for %s", graph_id)
        raise
    if not graph_messages:
        return
    existing = read_messages(graph_id, root=root)
    legacy_matches: dict[tuple[object, object], list[str]] = {}
    for row in existing:
        if row.get("source_key") or row.get("provenance") == "reconciled":
            continue
        message_id = row.get("id")
        if isinstance(message_id, str):
            legacy_matches.setdefault((row.get("author"), row.get("body")), []).append(
                message_id
            )
    for message_ordinal, msg in enumerate(graph_messages):
        role = str(msg.get("role") or "")
        body = str(msg.get("content") or "").strip()
        presentable = _presentable_message(role, body)
        if presentable is None:
            continue
        author, text = presentable
        legacy_ids = legacy_matches.get((author, text))
        if legacy_ids:
            mark_message_legacy_unknown(graph_id, legacy_ids.pop(0), root=root)
            continue
        append_planning_turn_to_chat(
            graph_id,
            [msg],
            root=root,
            checkpoint_config=checkpoint_config,
            message_offset=message_ordinal,
            provenance="reconciled",
        )


def _checkpoint_id(config: Mapping[str, object] | None) -> str | None:
    configurable = config.get("configurable") if config else None
    if not isinstance(configurable, Mapping):
        return None
    value = configurable.get("checkpoint_id")
    return value if isinstance(value, str) and value else None


def _message_id(message: Mapping[str, object]) -> str | None:
    value = message.get("id")
    return value if isinstance(value, str) and value else None


def _message_time(message: Mapping[str, object]) -> str | None:
    value = message.get("ts")
    return value if isinstance(value, str) and value else None


def _role_reply_source_key(
    graph_id: str,
    message: Mapping[str, object],
    *,
    checkpoint_id: str | None,
    message_ordinal: int,
) -> str | None:
    durable_id = _message_id(message)
    if durable_id is not None:
        return f"role_reply:{graph_id}:message:{durable_id}"
    if checkpoint_id is not None:
        return f"role_reply:{graph_id}:checkpoint:{checkpoint_id}:{message_ordinal}"
    return None


def _tier_for_graph_id(graph_id: str) -> str | None:
    if graph_id.startswith("epic_"):
        return "epic"
    if graph_id.startswith("feat_"):
        return "feature"
    return None


def _load_graph_messages(
    graph_id: str, tier: str, *, root: Path
) -> tuple[list[dict], Mapping[str, object]]:
    repo = Path(root).resolve()
    if tier == "epic":
        from cascade.epic.checkpoint import thread_config
        from cascade.epic.graph import ensure_epic_graph

        graph = ensure_epic_graph(graph_id, root=repo)
        config = thread_config(graph_id)
    else:
        from cascade.feature.checkpoint import thread_config
        from cascade.feature.graph import ensure_feature_graph

        graph = ensure_feature_graph(graph_id, root=repo)
        config = thread_config(graph_id)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    raw = values.get("messages") or []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out, snapshot.config or config
