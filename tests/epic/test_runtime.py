"""Epic LangGraph runtime: checkpoint, ingest, boot hook, tools."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.epic.boot as epic_boot
from cascade.epic import (
    clear_epic_tools,
    ensure_epic_graph,
    ingest_human,
    ingest_queue,
    install_epic_boot_hook,
    invoke_tool,
    register_epic_tool,
)
from cascade.epic.graph import clear_epic_graph_sessions
from tests.support import TEST_MODEL_ID
from cascade.epic.checkpoint import checkpoint_path, get_checkpointer
from cascade.epic.guard import EpicToolDenied
from cascade.watchdog import activate_epic, append_event
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks, invoke_boot
from cascade.watchdog.types import Event
from cascade.workspace.kickoff import install_kickoff, kickoff_turn, wait_for_background_kickoffs
from cascade.workspace.types import KickoffReason
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _epic_test_isolation() -> None:
    clear_hooks()
    clear_epic_tools()
    clear_epic_graph_sessions()
    epic_boot._boot_root = None
    epic_boot._last_model_config_failure = None
    yield
    clear_hooks()
    clear_epic_tools()
    clear_epic_graph_sessions()
    epic_boot._boot_root = None
    epic_boot._last_model_config_failure = None


def test_checkpoint_file_created(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    ensure_epic_graph("epic_001", root=root)
    path = checkpoint_path("epic_001", root=root)
    assert path.is_file()
    assert path.parent == root / ".cascade" / "checkpoints"


def test_ingest_human_persists_across_ensure(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    human = {"role": "human", "content": "Ship the MVP"}
    first = ingest_human("epic_001", human, root=root)
    assert any(m.get("role") == "human" for m in first["messages"])

    again = ensure_epic_graph("epic_001", root=root)
    state = again.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    assert any(m.get("content") == "Ship the MVP" for m in state["messages"])


def test_one_turn_adds_manager_and_architect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import install_fake_planning_turns

    install_fake_planning_turns(monkeypatch)
    root = make_repo(tmp_path, role_skills=True)
    state = ingest_human(
        "epic_001",
        {"role": "human", "content": "Plan features"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    managers = [m for m in state["messages"] if m.get("role") == "epic_manager"]
    architects = [m for m in state["messages"] if m.get("role") == "epic_architect"]
    assert len(managers) == 1
    assert len(architects) == 1
    assert "Plan features" in managers[0]["content"]
    assert "Plan features" in architects[0]["content"]
    assert managers[0]["content"].startswith("epic_manager:")
    assert architects[0]["content"].startswith("epic_architect:")


def test_ingest_queue_advances_offset_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    event = Event(
        type="EpicActivated",
        ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        payload={"epic_id": "epic_001", "by": "human"},
        dest="epic_001",
    )
    append_event("epic_001", event, root=root)

    first = ingest_queue("epic_001", root=root)
    events = [m for m in first["messages"] if m.get("role") == "event"]
    assert len(events) == 1
    assert "EpicActivated" in events[0]["content"]
    assert first["last_queue_offset"] > 0

    second = ingest_queue("epic_001", root=root)
    assert second["last_queue_offset"] == first["last_queue_offset"]
    assert len([m for m in second["messages"] if m.get("role") == "event"]) == 1


def test_install_boot_hook_consumes_epic_activated(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Boot epic", tier="epic", status="ready_to_plan")
    install_epic_boot_hook(root)

    activate_epic("epic_001", "human", root=root)
    assert wait_for_background_kickoffs(timeout=15)

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    event_msgs = [m for m in state["messages"] if m.get("role") == "event"]
    assert len(event_msgs) == 1
    assert "EpicActivated" in event_msgs[0]["content"]


def test_invoke_boot_with_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Invoke boot", tier="epic", status="active")
    append_event(
        "epic_001",
        Event(
            type="EpicActivated",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"epic_id": "epic_001", "by": "human"},
            dest="epic_001",
        ),
        root=root,
    )
    install_epic_boot_hook(root)
    install_kickoff(root)
    invoke_boot("epic", "epic_001")
    kickoff_turn(
        KickoffReason(
            kind="activate",
            work_id="epic_001",
            by="human",
            root=root,
        )
    )
    assert wait_for_background_kickoffs(timeout=15)

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state and any(m.get("role") == "event" for m in state["messages"])


def test_invoke_tool_uses_registry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    def ping(**_kwargs: object) -> str:
        return "pong"

    register_epic_tool("ping", ping)
    result = invoke_tool("epic_001", "ping", {}, root=root)
    assert result == "pong"

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    tools = [m for m in state["messages"] if m.get("role") == "tool"]
    assert len(tools) == 1
    assert tools[0]["name"] == "ping"
    assert tools[0]["content"] == "pong"


def test_two_epics_do_not_share_messages(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    ingest_human("epic_001", {"role": "human", "content": "Alpha"}, root=root)
    ingest_human("epic_002", {"role": "human", "content": "Beta"}, root=root)

    g1 = ensure_epic_graph("epic_001", root=root)
    g2 = ensure_epic_graph("epic_002", root=root)
    s1 = g1.get_state({"configurable": {"thread_id": "epic_001"}}).values
    s2 = g2.get_state({"configurable": {"thread_id": "epic_002"}}).values
    assert s1 and s2
    assert all("Beta" not in m.get("content", "") for m in s1["messages"])
    assert all("Alpha" not in m.get("content", "") for m in s2["messages"])
    assert checkpoint_path("epic_001", root=root) != checkpoint_path("epic_002", root=root)


def test_boot_epic_skips_non_epic_tier(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Not epic",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    install_epic_boot_hook(root)
    invoke_boot("epic", "feat_001")
    with pytest.raises(ValueError):
        checkpoint_path("feat_001", root=root)


def test_checkpoint_rejects_path_traversal(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    outside = tmp_path / "escaped.sqlite"
    for bad_id in ("../evil", "epic_001/x"):
        with pytest.raises(ValueError):
            get_checkpointer(bad_id, root=root)
    assert not outside.exists()
    assert not (tmp_path / "evil.sqlite").exists()


def test_invoke_tool_binds_session_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="One", tier="epic", status="active")
    add_doc(root, id="epic_002", title="Two", tier="epic", status="active")
    from cascade.epic import load_epic_tools

    load_epic_tools()

    with pytest.raises(EpicToolDenied):
        invoke_tool(
            "epic_001",
            "mint_feature",
            {"title": "Sneak", "epic_id": "epic_002", "root": root},
            root=root,
        )


def test_run_watchdog_installs_epic_boot_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Watchdog epic", tier="epic", status="ready_to_plan")
    from cascade.watchdog.loop import run_watchdog

    run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)
    activate_epic("epic_001", "human", root=root)
    assert wait_for_background_kickoffs(timeout=15)
    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    assert any(m.get("role") == "event" and "EpicActivated" in m.get("content", "") for m in state["messages"])


def test_boot_seeds_per_role_models_in_checkpoint(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Models epic", tier="epic", status="active")
    install_epic_boot_hook(root)
    invoke_boot("epic", "epic_001")

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    assert state["model_ids"]["epic_manager"] == "proj-epic"
    assert state["model_ids"]["epic_architect"] == "proj-epic"
    assert state["model_sources"]["epic_manager"] == "project-tier"


def test_boot_missing_models_table_fails_closed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=False)
    add_doc(root, id="epic_001", title="No models", tier="epic", status="active")
    install_epic_boot_hook(root)
    invoke_boot("epic", "epic_001")

    assert epic_boot.last_epic_boot_model_failure() is not None
    assert not checkpoint_path("epic_001", root=root).is_file()
    war_events, _ = read_events("war_room", 0, root=root)
    assert any(
        e.type == "Toast" and e.payload.get("id") == "epic_001" for e in war_events
    )
    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert not state or not any(
        m.get("role") in ("epic_manager", "epic_architect") for m in (state.get("messages") or [])
    )


def test_install_epic_boot_hook_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    install_epic_boot_hook(root)
    install_epic_boot_hook(root)
    from cascade.watchdog.hooks import _boot

    epic_hooks = _boot["epic"]
    assert sum(fn is epic_boot.boot_epic for fn in epic_hooks) == 1
