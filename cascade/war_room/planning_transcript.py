"""Append epic/feature planning role lines to War Room chat sidecars."""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)

from cascade.comments.types import AGENT_AUTHORS
from cascade.war_room.chat_store import append_transcript_message, read_messages
from cascade.watchdog.lock import process_lock

_SKIP_BODY_PREFIXES = (
    "turn failed",
    "no input",
    "provider startup failed",
    "model_id is required",
)


def append_planning_turn_to_chat(
    graph_id: str,
    new_messages: list[dict],
    *,
    root,
) -> None:
    """Mirror manager/architect (or feature roles) output into the graph chat JSONL."""

    for msg in new_messages:
        role = str(msg.get("role") or "")
        if role not in AGENT_AUTHORS:
            continue
        body = str(msg.get("content") or "").strip()
        if not body or _should_skip(body):
            continue
        append_transcript_message(
            graph_id,
            author=role,
            body=body,
            root=root,
        )


def _should_skip(body: str) -> bool:
    lowered = body.lower()
    return any(lowered.startswith(prefix) for prefix in _SKIP_BODY_PREFIXES)


def sync_planning_transcript_to_chat(graph_id: str, *, root: Path) -> None:
    """Backfill agent lines from the graph checkpoint into the chat JSONL (idempotent)."""

    tier = _tier_for_graph_id(graph_id)
    if tier is None:
        return
    try:
        graph_messages = _load_graph_messages(graph_id, tier, root=root)
    except Exception:
        _log.exception("failed to load planning graph messages for %s", graph_id)
        raise
    if not graph_messages:
        return
    with process_lock:
        existing = read_messages(graph_id, root=root)
        seen = {(row.get("author"), row.get("body")) for row in existing}
        for msg in graph_messages:
            role = str(msg.get("role") or "")
            body = str(msg.get("content") or "").strip()
            if role not in AGENT_AUTHORS or not body or _should_skip(body):
                continue
            if (role, body) in seen:
                continue
            append_transcript_message(graph_id, author=role, body=body, root=root)
            seen.add((role, body))


def _tier_for_graph_id(graph_id: str) -> str | None:
    if graph_id.startswith("epic_"):
        return "epic"
    if graph_id.startswith("feat_"):
        return "feature"
    return None


def _load_graph_messages(graph_id: str, tier: str, *, root: Path) -> list[dict]:
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
    values = graph.get_state(config).values or {}
    raw = values.get("messages") or []
    out: list[dict] = []
    for item in raw:
        if isinstance(item, dict):
            out.append(item)
    return out
