"""Feature LangGraph subgraph: ingest, lead, and architect role turns."""

from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from cascade.agent.graph_turn import clear_turn_model_override, run_coro_sync, run_planning_role_turn
from cascade.feature.checkpoint import get_checkpointer, thread_config
from cascade.feature.registry import feature_tools
from cascade.feature.state import FeatureGraphState
from cascade.watchdog.events import read_events
from cascade.watchdog.queue_cursor import resolve_last_queue_offset
from cascade.watchdog.model_resolve import ResolvedBackend

_graph_cache: dict[tuple[str, str], object] = {}
_session_roots: dict[tuple[str, str], Path] = {}


def clear_feature_graph_sessions() -> None:
    """Reset cached graph compile keys and bound repo roots (tests only)."""

    _graph_cache.clear()
    _session_roots.clear()


def seed_feature_role_models(
    feature_id: str,
    *,
    lead: ResolvedBackend,
    architect: ResolvedBackend,
    root: Path,
) -> None:
    """Persist per-role resolved provider and model ids on the feature graph checkpoint."""

    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    update: FeatureGraphState = {
        "model_ids": {
            "feature_lead": lead.model.model_id,
            "feature_architect": architect.model.model_id,
        },
        "model_sources": {
            "feature_lead": lead.model.source,
            "feature_architect": architect.model.source,
        },
        "provider_ids": {
            "feature_lead": lead.provider,
            "feature_architect": architect.provider,
        },
        "provider_sources": {
            "feature_lead": lead.provider_source,
            "feature_architect": architect.provider_source,
        },
    }
    if lead.reasoning:
        update.setdefault("reasoning_ids", {})["feature_lead"] = lead.reasoning
        update.setdefault("reasoning_sources", {})["feature_lead"] = lead.reasoning_source or "document-role"
    if architect.reasoning:
        update.setdefault("reasoning_ids", {})["feature_architect"] = architect.reasoning
        update.setdefault("reasoning_sources", {})["feature_architect"] = architect.reasoning_source or "document-role"
    snapshot = graph.get_state(config)
    if not snapshot.values:
        update["feature_id"] = feature_id
        update["messages"] = []
        update["last_queue_offset"] = resolve_last_queue_offset(
            feature_id, current=0, proposed=0, root=root
        )
    graph.update_state(config, update)


def ensure_feature_graph(feature_id: str, *, root: Path):
    """Compile (or return cached) feature subgraph with a local SQLite checkpointer."""

    repo = Path(root).resolve()
    key = (str(repo), feature_id)
    _session_roots[key] = repo
    if key in _graph_cache:
        return _graph_cache[key]

    checkpointer = get_checkpointer(feature_id, root=repo)
    builder = StateGraph(FeatureGraphState)
    builder.add_node("ingest", _ingest_node)
    builder.add_node("feature_lead", _feature_lead_node)
    builder.add_node("feature_architect", _feature_architect_node)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "feature_lead")
    builder.add_edge("feature_lead", "feature_architect")
    builder.add_edge("feature_architect", END)
    compiled = builder.compile(checkpointer=checkpointer)
    _graph_cache[key] = compiled
    return compiled


def ingest_human(
    feature_id: str,
    message: dict,
    *,
    root: Path,
    model_id: str | None = None,
) -> FeatureGraphState:
    """Append one human message and run a single lead/architect turn."""

    from cascade.workspace.kickoff import kickoff_turn
    from cascade.workspace.types import KickoffReason

    kickoff_turn(
        KickoffReason(
            kind="human_message",
            work_id=feature_id,
            by="human",
            root=root,
            message=message,
            model_id=model_id,
        )
    )
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    return _state_values(graph, config)


def ingest_queue(
    feature_id: str,
    *,
    root: Path,
    queue_root: Path | None = None,
) -> FeatureGraphState:
    """Pull new queue events into graph state without a lead/architect turn."""

    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    offset = int(values.get("last_queue_offset") or 0)
    events, new_offset = read_events(feature_id, offset, root=queue_root or root)
    if not events:
        if not values:
            graph.update_state(
                config,
                {
                    "feature_id": feature_id,
                    "messages": [],
                    "last_queue_offset": resolve_last_queue_offset(
                        feature_id, current=0, proposed=offset, root=queue_root or root
                    ),
                },
            )
            return _state_values(graph, config)
        return values  # type: ignore[return-value]

    event_messages = [_event_message(event) for event in events]
    update: FeatureGraphState = {
        "messages": event_messages,
        "last_queue_offset": resolve_last_queue_offset(
            feature_id, current=offset, proposed=new_offset, root=queue_root or root
        ),
    }
    if not values:
        update["feature_id"] = feature_id
    graph.update_state(config, update)
    return _state_values(graph, config)


def invoke_tool(feature_id: str, name: str, args: dict, *, root: Path) -> object:
    """Run a registered feature tool and record a tool message on success."""

    tools = feature_tools()
    if name not in tools:
        raise KeyError(name)
    bound_root = Path(root).resolve()
    result = tools[name](**{**args, "feature_id": feature_id, "root": bound_root})
    graph = ensure_feature_graph(feature_id, root=root)
    config = thread_config(feature_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        graph.update_state(
            config,
            {
                "feature_id": feature_id,
                "messages": [],
                "last_queue_offset": resolve_last_queue_offset(
                    feature_id, current=0, proposed=0, root=root
                ),
            },
        )
    tool_message = {
        "role": "tool",
        "name": name,
        "content": _tool_content(result),
    }
    graph.update_state(config, {"messages": [tool_message]})
    return result


def _ingest_node(state: FeatureGraphState) -> dict:
    return {}


def _feature_lead_node(state: FeatureGraphState) -> dict:
    content = _planning_role_content("feature_lead", state)
    return {"messages": [{"role": "feature_lead", "content": content}]}


def _feature_architect_node(state: FeatureGraphState) -> dict:
    content = _planning_role_content("feature_architect", state)
    return {"messages": [{"role": "feature_architect", "content": content}]}


def _planning_role_content(role: str, state: FeatureGraphState) -> str:
    from cascade.agent.planning_turn import run_feature_planning_turn

    repo = _repo_for_state(state)
    feature_id = state.get("feature_id") or ""
    return run_coro_sync(
        run_planning_role_turn(
            role,  # type: ignore[arg-type]
            state,
            root=repo,
            run_turn=run_feature_planning_turn,
            feature_id=feature_id,
        )
    )


def _repo_for_state(state: FeatureGraphState) -> Path:
    feature_id = state.get("feature_id") or ""
    for (_repo_str, bound_id), repo in _session_roots.items():
        if bound_id == feature_id:
            return repo
    raise RuntimeError(f"no session root bound for feature {feature_id!r}")


def _event_message(event) -> dict:
    payload = json.dumps(event.payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "role": "event",
        "content": f"{event.type} {payload}",
        "name": event.type,
    }


def _tool_content(result: object) -> str:
    if isinstance(result, str):
        return result
    try:
        return json.dumps(result, ensure_ascii=False, default=str)
    except TypeError:
        return str(result)


def _state_values(graph, config: dict) -> FeatureGraphState:
    values = graph.get_state(config).values
    if not values:
        return {
            "feature_id": config["configurable"]["thread_id"],
            "messages": [],
            "last_queue_offset": 0,
        }
    return values  # type: ignore[return-value]
