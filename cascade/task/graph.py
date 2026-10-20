"""Task LangGraph subgraph: ingest and SWE role turn."""

from __future__ import annotations

import json
from pathlib import Path
from langgraph.graph import END, START, StateGraph

from cascade.agent.graph_turn import (
    clear_turn_model_override,
    format_turn_prompt,
    latest_input,
    missing_model_message,
    missing_provider_message,
    model_for_role,
    no_input_message,
    provider_for_role,
    run_coro_sync,
)
from cascade.task.checkpoint import drop_task_checkpoint, get_checkpointer, thread_config
from cascade.task.registry import task_tools
from cascade.task.state import TaskGraphState
from cascade.task.swe_turn import RunRoleFn, SweTurnResult
from cascade.watchdog.events import read_events
from cascade.watchdog.model_resolve import ResolvedBackend

_graph_cache: dict[tuple[str, str], object] = {}
_session_roots: dict[tuple[str, str], Path] = {}
_session_features: dict[tuple[str, str], str | None] = {}
_run_role_fn: RunRoleFn | None = None


def clear_task_graph_sessions() -> None:
    """Reset cached graph compile keys and bound repo roots (tests only)."""

    _graph_cache.clear()
    _session_roots.clear()
    _session_features.clear()
    global _run_role_fn
    _run_role_fn = None


def set_task_run_role_fn(fn: RunRoleFn | None) -> None:
    """Inject adapter for tests (module boundary)."""

    global _run_role_fn
    _run_role_fn = fn


def seed_task_role_models(
    task_id: str,
    *,
    swe: ResolvedBackend,
    root: Path,
    feature_id: str | None = None,
) -> None:
    """Persist resolved SWE provider and model id on the task graph checkpoint."""

    graph = ensure_task_graph(task_id, root=root, feature_id=feature_id)
    config = thread_config(task_id)
    update: TaskGraphState = {
        "model_ids": {"swe": swe.model.model_id},
        "model_sources": {"swe": swe.model.source},
        "provider_ids": {"swe": swe.provider},
        "provider_sources": {"swe": swe.provider_source},
    }
    snapshot = graph.get_state(config)
    if not snapshot.values:
        update.update(_empty_state(task_id, feature_id, 0))
    graph.update_state(config, update)


def ensure_task_graph(task_id: str, *, root: Path, feature_id: str | None = None):
    """Compile (or return cached) task subgraph with a local SQLite checkpointer."""

    repo = Path(root).resolve()
    key = (str(repo), task_id)
    _session_roots[key] = repo
    _session_features[key] = feature_id
    if key in _graph_cache:
        return _graph_cache[key]

    checkpointer = get_checkpointer(task_id, root=repo)
    builder = StateGraph(TaskGraphState)
    builder.add_node("ingest", _ingest_node)
    builder.add_node("task_swe", _task_swe_node)
    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "task_swe")
    builder.add_edge("task_swe", END)
    compiled = builder.compile(checkpointer=checkpointer)
    _graph_cache[key] = compiled
    return compiled


def drop_task_graph(task_id: str, *, root: Path) -> None:
    """Drop cached graph and close/remove this task's checkpointer."""

    repo = Path(root).resolve()
    key = (str(repo), task_id)
    _graph_cache.pop(key, None)
    _session_roots.pop(key, None)
    _session_features.pop(key, None)
    drop_task_checkpoint(task_id, root=repo)


def invoke_role_turn(
    task_id: str,
    message: dict,
    *,
    root: Path,
    feature_id: str | None = None,
    model_id: str | None = None,
) -> TaskGraphState:
    """Append one input message and run a single SWE turn."""

    from cascade.workspace.kickoff import kickoff_turn
    from cascade.workspace.types import KickoffReason

    kickoff_turn(
        KickoffReason(
            kind="human_message",
            work_id=task_id,
            by="human",
            root=root,
            message=message,
            feature_id=feature_id,
            model_id=model_id,
        )
    )
    graph = ensure_task_graph(task_id, root=root, feature_id=feature_id)
    config = thread_config(task_id)
    return _state_values(graph, config)


def ingest_queue(task_id: str, *, root: Path, feature_id: str | None = None) -> TaskGraphState:
    """Pull new queue events into graph state without a SWE turn."""

    graph = ensure_task_graph(task_id, root=root, feature_id=feature_id)
    config = thread_config(task_id)
    snapshot = graph.get_state(config)
    values = snapshot.values or {}
    offset = int(values.get("last_queue_offset") or 0)
    events, new_offset = read_events(task_id, offset, root=root)
    if not events:
        if not values:
            graph.update_state(
                config,
                _empty_state(task_id, feature_id, offset),
            )
            return _state_values(graph, config)
        return values  # type: ignore[return-value]

    event_messages = [_event_message(event) for event in events]
    if not values:
        update = _empty_state(task_id, feature_id, new_offset)
        update["messages"] = event_messages
    else:
        update = {
            "messages": event_messages,
            "last_queue_offset": new_offset,
        }
    graph.update_state(config, update)
    return _state_values(graph, config)


def invoke_tool(task_id: str, name: str, args: dict, *, root: Path, feature_id: str | None = None) -> object:
    """Run a registered task tool and record a tool message on success."""

    from cascade.task.failure import classify_error, maybe_retry
    from cascade.task.wiring import get_infra_attempt, on_tests_finished, on_tool_error, set_infra_attempt

    tools = task_tools()
    if name not in tools:
        raise KeyError(name)
    bound_root = Path(root).resolve()

    if name == "swe_run_tests":
        from cascade.task.worktree import get_task_run

        run = get_task_run(task_id)
        if run is not None:
            run.state = "testing"

    attempt = get_infra_attempt(task_id)
    while True:
        try:
            result = tools[name](**{**args, "task_id": task_id, "root": bound_root})
        except BaseException as exc:
            kind = classify_error(exc)
            if kind == "spec":
                # Ordinary tool mistakes (for example probing a file that does
                # not exist, a guarded access denial, or an empty duplicate
                # commit) are part of an agent turn. Return the error to the
                # agent so it can correct itself; the guards still deny the
                # action and final deliverable/test gates decide whether the
                # Task must be blocked.
                raise
            if maybe_retry(task_id, kind, attempt, root=bound_root):
                attempt += 1
                set_infra_attempt(task_id, attempt)
                continue
            on_tool_error(task_id, exc, root=bound_root)
            raise

        _record_tool_message(task_id, name, result, root=bound_root, feature_id=feature_id)
        set_infra_attempt(task_id, None)

        if name == "swe_run_tests" and isinstance(result, dict):
            on_tests_finished(task_id, result, root=bound_root)

        return result


def _record_tool_message(
    task_id: str,
    name: str,
    result: object,
    *,
    root: Path,
    feature_id: str | None,
) -> None:
    graph = ensure_task_graph(task_id, root=root, feature_id=feature_id)
    config = thread_config(task_id)
    snapshot = graph.get_state(config)
    if not snapshot.values:
        graph.update_state(config, _empty_state(task_id, feature_id, 0))
    tool_message = {
        "role": "tool",
        "name": name,
        "content": _tool_content(result),
    }
    graph.update_state(config, {"messages": [tool_message]})


def _ingest_node(state: TaskGraphState) -> dict:
    return {}


def _task_swe_node(state: TaskGraphState) -> dict:
    content = _swe_role_content(state)
    return {"messages": [{"role": "task_swe", "content": content}]}


def _swe_role_content(state: TaskGraphState) -> str:
    from cascade.workspace.kickoff import model_turn_authorized

    if not model_turn_authorized():
        return no_input_message("swe")

    messages = state.get("messages") or []
    if latest_input(messages) is None:
        return no_input_message("swe")

    model_id, model_source = model_for_role(state, "swe")
    if model_id is None:
        return missing_model_message("swe")

    provider_id, provider_source = provider_for_role(state, "swe")
    if provider_id is None:
        return missing_provider_message("swe")

    task_id = state.get("task_id") or ""
    repo = _repo_for_state(task_id)
    prompt = format_turn_prompt(
        messages,
        provider_id=provider_id,
        provider_source=provider_source,
        model_id=model_id,
        model_source=model_source,
    )

    from cascade.task.swe_turn import default_swe_commit_message, run_swe_turn

    try:
        outcome = run_coro_sync(
            run_swe_turn(
                task_id,
                provider=provider_id,
                model_id=model_id,
                prompt=prompt,
                root=repo,
                commit_message=default_swe_commit_message(task_id),
                run_role_fn=_run_role_fn,
            )
        )
    except RuntimeError as exc:
        return f"swe: {exc}"

    if (
        not outcome.failed_closed
        and outcome.role_result is not None
        and outcome.role_result.status == "finished"
    ):
        _auto_merge_finished_task(task_id, repo)

    return _swe_outcome_message(outcome)


def _auto_merge_finished_task(task_id: str, root: Path) -> None:
    """Land a successful task on its feature branch without another approval click."""

    try:
        from cascade.watchdog.config import read_automation_config

        if not read_automation_config(root).enabled:
            return
        from cascade.task.failure import fail_task
        from cascade.task.swe_turn import has_deliverable_commit
        from cascade.task.worktree import get_task_run

        run = get_task_run(task_id)
        if run is None or not has_deliverable_commit(run):
            fail_task(task_id, "no_task_changes", root=root)
            return
        from cascade.task_rollup import queue_task_merge, retry_pending_task_merges

        queue_task_merge(task_id, root=root)
        retry_pending_task_merges(root)
    except Exception:
        # The task commit remains durable. A later watchdog/review turn can retry
        # rollup without turning successful implementation into a failed task.
        return


def _swe_outcome_message(outcome: SweTurnResult) -> str:
    if outcome.failed_closed:
        if outcome.role_result is not None and outcome.role_result.status == "error":
            detail = outcome.role_result.text.strip() or "run failed"
            return f"swe: turn failed — {detail}"
        reason = outcome.failure_reason or "turn failed"
        return f"swe: {reason}"
    if outcome.role_result is not None:
        if outcome.role_result.status == "finished":
            return outcome.role_result.text
        detail = outcome.role_result.text.strip() or "run failed"
        return f"swe: turn failed — {detail}"
    reason = outcome.failure_reason or "turn failed"
    return f"swe: {reason}"


def _repo_for_state(task_id: str) -> Path:
    for (_repo_str, bound_id), repo in _session_roots.items():
        if bound_id == task_id:
            return repo
    raise RuntimeError(f"no session root bound for task {task_id!r}")


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


def _empty_state(task_id: str, feature_id: str | None, offset: int) -> TaskGraphState:
    return {
        "task_id": task_id,
        "feature_id": feature_id or "",
        "messages": [],
        "last_queue_offset": offset,
        "skill_playbooks": [],
    }


def _state_values(graph, config: dict) -> TaskGraphState:
    values = graph.get_state(config).values
    if not values:
        task_id = config["configurable"]["thread_id"]
        return _empty_state(task_id, None, 0)
    playbooks = values.get("skill_playbooks")
    if playbooks is None:
        values = {**values, "skill_playbooks": []}
    return values  # type: ignore[return-value]
