"""Append epic/feature planning role lines to War Room chat sidecars."""

from __future__ import annotations

import logging
from pathlib import Path

from cascade.comments.types import AGENT_AUTHORS
from cascade.war_room.chat_store import append_transcript_message, read_messages
from cascade.watchdog.lock import process_lock

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
) -> None:
    """Mirror manager/architect (or feature roles) output into the graph chat JSONL."""

    for msg in new_messages:
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
        )


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
            presentable = _presentable_message(role, body)
            if presentable is None:
                continue
            author, text = presentable
            if (author, text) in seen:
                continue
            append_transcript_message(graph_id, author=author, body=text, root=root)
            seen.add((author, text))


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
