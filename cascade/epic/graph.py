"""Epic LangGraph subgraph: ingest, manager, and architect role turns."""

from __future__ import annotations

import json
from pathlib import Path

from langgraph.graph import END, START, StateGraph

from cascade.agent.graph_turn import clear_turn_model_override, run_coro_sync, run_planning_role_turn
from cascade.epic.checkpoint import get_checkpointer, thread_config
from cascade.epic.registry import epic_tools
from cascade.epic.state import EpicGraphState
from cascade.watchdog.events import read_events
from cascade.watchdog.model_resolve import ResolvedBackend

_graph_cache: dict[tuple[str, str], object] = {}
_session_roots: dict[tuple[str, str], Path] = {}


def clear_epic_graph_sessions() -> None:
    """Reset cached graph compile keys and bound repo roots (tests only)."""

    _graph_cache.clear()
    _session_roots.clear()


def seed_epic_role_models(
    epic_id: str,
    *,
    manager: ResolvedBackend,
    architect: ResolvedBackend,
    root: Path,
) -> None:
    """Persist per-role resolved provider and model ids on the epic graph checkpoint."""

    graph = ensure_epic_graph(epic_id, root=root)
    config = thread_config(epic_id)
    update: EpicGraphState = {
        "model_ids": {
            "epic_manager": manager.model.model_id,
            "epic_architect": architect.model.model_id,
        },
        "model_sources": {
            "epic_manager": manager.model.source,
            "epic_architect": architect.model.source,
        },
        "provider_ids": {
            "epic_manager": manager.provider,
            "epic_architect": architect.provider,
        },
        "provider_sources": {
            "epic_manager": manager.provider_source,
            "epic_architect": architect.provider_source,
        },
    }
    snapshot = graph.get_state(config)
    if not snapshot.values:
        update["epic_id"] = epic_id
        update["messages"] = []
        update["last_queue_offset"] = 0
    graph.update_state(config, update)


def ensure_epic_graph(epic_id: str, *, root: Path):
    """Compile (or return cached) epic subgraph with a local SQLite checkpointer."""

    repo = Path(root).resolve()
    key = (str(repo), epic_id)
    _session_roots[key] = repo
    if key in _graph_cache:
        return _graph_cache[key]

    checkpointer = get_checkpointer(epic_id, root=repo)
    builder = StateGraph(EpicGraphState)
    builder.add_node("ingest", _ingest_node)
    builder.add_node("manager", _manager_node)
    builder.add_node("architect", _architect_node)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "manager")
    builder.add_edge("manager", "architect")
    builder.add_edge("architect", END)
    compiled = builder.compile(checkpointer=checkpointer)
    _graph_cache[key] = compiled
    return compiled


def ingest_human(
    epic_id: str,
    message: dict,
    *,
    root: Path,
    model_id: str | None = None,
) -> EpicGraphState:
    """Append one human message and run a single manager/architect turn."""

    from cascade.workspace.kickoff import kickoff_turn
    from cascade.workspace.types import KickoffReason

    kickoff_turn(
        KickoffReason(
            kind="human_message",
            work_id=epic_id,
            by="human",
            root=root,
            message=message,
            model_id=model_id,
        )
    )
    graph = ensure_epic_graph(epic_id, root=root)
    config = thread_config(epic_id)
    return _state_values(graph, config)


def ingest_queue(epic_id: str, *, root: Path) -> EpicGraphState:
    """Pull new queue events into graph state without a manager/architect turn."""

    graph = ensure_epic_graph(epic_id, root=root)
    config = thread_config(epic_id)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    offset = int(values.get("last_queue_offset") or 0)
    events, new_offset = read_events(epic_id, offset, root=root)
    if not events:
        if not values:
            graph.update_state(
                config,
                {"epic_id": epic_id, "messages": [], "last_queue_offset": offset},
            )
            return _state_values(graph, config)
        return values  # type: ignore[return-value]

    event_messages = [_event_message(event) for event in events]
    prior_messages = list(values.get("messages") or [])
    update: EpicGraphState = {
        "messages": prior_messages + event_messages,
        "last_queue_offset": new_offset,
    }
    if not values:
        update["epic_id"] = epic_id
    graph.update_state(config, update)
    return _state_values(graph, config)


def invoke_tool(epic_id: str, name: str, args: dict, *, root: Path) -> object:
    """Run a registered epic tool and record a tool message on success."""

    from cascade.epic.guard import EpicToolDenied

    tools = epic_tools()
    if name not in tools:
        raise KeyError(name)
    if "epic_id" in args and args["epic_id"] != epic_id:
        raise EpicToolDenied("epic_id in args disagrees with session epic")
    bound_root = Path(root).resolve()
    if "root" in args and Path(args["root"]).resolve() != bound_root:
        raise EpicToolDenied("root in args disagrees with session root")
    result = tools[name](**{**args, "epic_id": epic_id, "root": bound_root})
    graph = ensure_epic_graph(epic_id, root=root)
    config = thread_config(epic_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        graph.update_state(
            config,
            {"epic_id": epic_id, "messages": [], "last_queue_offset": 0},
        )
    tool_message = {
        "role": "tool",
        "name": name,
        "content": _tool_content(result),
    }
    graph.update_state(config, {"messages": [tool_message]})
    return result


def _ingest_node(state: EpicGraphState) -> dict:
    return {}


def _manager_node(state: EpicGraphState) -> dict:
    content = _planning_role_content("epic_manager", state)
    return {"messages": [{"role": "epic_manager", "content": content}]}


def _architect_node(state: EpicGraphState) -> dict:
    content = _planning_role_content("epic_architect", state)
    return {"messages": [{"role": "epic_architect", "content": content}]}


def _planning_role_content(role: str, state: EpicGraphState) -> str:
    from cascade.agent.planning_turn import run_epic_planning_turn

    repo = _repo_for_state(state)
    epic_id = state.get("epic_id") or ""
    return run_coro_sync(
        run_planning_role_turn(
            role,  # type: ignore[arg-type]
            state,
            root=repo,
            run_turn=run_epic_planning_turn,
            epic_id=epic_id,
        )
    )


def _repo_for_state(state: EpicGraphState) -> Path:
    epic_id = state.get("epic_id") or ""
    for (repo_str, bound_id), repo in _session_roots.items():
        if bound_id == epic_id:
            return repo
    raise RuntimeError(f"no session root bound for epic {epic_id!r}")


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


def _state_values(graph, config: dict) -> EpicGraphState:
    values = graph.get_state(config).values
    if not values:
        return {"epic_id": config["configurable"]["thread_id"], "messages": [], "last_queue_offset": 0}
    return values  # type: ignore[return-value]
