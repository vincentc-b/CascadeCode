"""Feature LangGraph runtime: checkpoint, ingest, boot hook, tools."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.feature.boot as feature_boot
from cascade.feature import (
    clear_feature_tools,
    ensure_feature_graph,
    ingest_human,
    ingest_queue,
    install_feature_boot_hook,
    invoke_tool,
    register_feature_tool,
)
from cascade.feature.graph import clear_feature_graph_sessions
from tests.support import TEST_MODEL_ID, approve_board_feature
from cascade.feature.checkpoint import checkpoint_path, get_checkpointer
from cascade.board.store import pin_parent, read_doc
from cascade.watchdog import activate_epic, append_event, dispatch_feature
from cascade.watchdog.hooks import clear_hooks, invoke_boot
from cascade.watchdog.events import read_events
from cascade.watchdog.types import Event
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _feature_test_isolation() -> None:
    clear_hooks()
    clear_feature_tools()
    clear_feature_graph_sessions()
    feature_boot._boot_root = None
    feature_boot._last_model_config_failure = None
    yield
    clear_hooks()
    clear_feature_tools()
    clear_feature_graph_sessions()
    feature_boot._boot_root = None
    feature_boot._last_model_config_failure = None


def test_checkpoint_file_created(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    ensure_feature_graph("feat_001", root=root)
    path = checkpoint_path("feat_001", root=root)
    assert path.is_file()
    assert path.parent == root / ".cascade" / "checkpoints"


def test_ingest_human_persists_across_ensure(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    human = {"role": "human", "content": "Plan tasks"}
    first = ingest_human("feat_001", human, root=root)
    assert any(m.get("role") == "human" for m in first["messages"])

    again = ensure_feature_graph("feat_001", root=root)
    state = again.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert state is not None
    assert any(m.get("content") == "Plan tasks" for m in state["messages"])


def test_one_turn_adds_lead_and_architect(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tests.support import install_fake_planning_turns

    install_fake_planning_turns(monkeypatch)
    root = make_repo(tmp_path, role_skills=True)
    state = ingest_human(
        "feat_001",
        {"role": "human", "content": "Scope MVP"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    leads = [m for m in state["messages"] if m.get("role") == "feature_lead"]
    architects = [m for m in state["messages"] if m.get("role") == "feature_architect"]
    assert len(leads) == 1
    assert len(architects) == 1
    assert "Scope MVP" in leads[0]["content"]
    assert "Scope MVP" in architects[0]["content"]
    assert leads[0]["content"].startswith("feature_lead:")
    assert architects[0]["content"].startswith("feature_architect:")


def test_ingest_queue_advances_offset_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    event = Event(
        type="FeatureReadyToPlan",
        ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        payload={"id": "feat_001", "feature_id": "feat_001", "by": "human"},
        dest="feat_001",
    )
    append_event("feat_001", event, root=root)

    first = ingest_queue("feat_001", root=root)
    events = [m for m in first["messages"] if m.get("role") == "event"]
    assert len(events) == 1
    assert "FeatureReadyToPlan" in events[0]["content"]
    assert first["last_queue_offset"] > 0

    second = ingest_queue("feat_001", root=root)
    assert second["last_queue_offset"] == first["last_queue_offset"]
    assert len([m for m in second["messages"] if m.get("role") == "event"]) == 1

    append_event("feat_001", event, root=root)
    third = ingest_queue("feat_001", root=root)
    assert len(third["messages"]) == 2


def test_ingest_queue_does_not_run_lead_or_architect(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    append_event(
        "feat_001",
        Event(
            type="FeatureReadyToPlan",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"id": "feat_001", "feature_id": "feat_001", "by": "human"},
            dest="feat_001",
        ),
        root=root,
    )
    state = ingest_queue("feat_001", root=root)
    assert not any(m.get("role") == "feature_lead" for m in state["messages"])
    assert not any(m.get("role") == "feature_architect" for m in state["messages"])


def test_install_boot_hook_consumes_feature_ready_to_plan(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Boot feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    install_feature_boot_hook(root)

    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    dispatch_feature("feat_001", "human", root=root)

    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert state is not None
    event_msgs = [m for m in state["messages"] if m.get("role") == "event"]
    assert len(event_msgs) == 1
    assert "FeatureReadyToPlan" in event_msgs[0]["content"]


def test_boot_pins_parent_rev(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    parent = add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Child feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    assert read_doc("feat_001", root=root).meta.parent_rev is None

    install_feature_boot_hook(root)
    invoke_boot("feature", "feat_001")

    child = read_doc("feat_001", root=root)
    assert child.meta.parent_rev == parent.sha


def test_invoke_boot_with_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Invoke boot",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    append_event(
        "feat_001",
        Event(
            type="FeatureReadyToPlan",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"id": "feat_001", "feature_id": "feat_001", "by": "human"},
            dest="feat_001",
        ),
        root=root,
    )
    install_feature_boot_hook(root)
    invoke_boot("feature", "feat_001")

    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert state and any(m.get("role") == "event" for m in state["messages"])


def test_invoke_tool_uses_registry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    def ping(**_kwargs: object) -> str:
        return "pong"

    register_feature_tool("ping", ping)
    result = invoke_tool("feat_001", "ping", {}, root=root)
    assert result == "pong"

    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    tools = [m for m in state["messages"] if m.get("role") == "tool"]
    assert len(tools) == 1
    assert tools[0]["name"] == "ping"
    assert tools[0]["content"] == "pong"


def test_two_features_do_not_share_messages(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    ingest_human("feat_001", {"role": "human", "content": "Alpha"}, root=root)
    ingest_human("feat_002", {"role": "human", "content": "Beta"}, root=root)

    g1 = ensure_feature_graph("feat_001", root=root)
    g2 = ensure_feature_graph("feat_002", root=root)
    s1 = g1.get_state({"configurable": {"thread_id": "feat_001"}}).values
    s2 = g2.get_state({"configurable": {"thread_id": "feat_002"}}).values
    assert s1 and s2
    assert all("Beta" not in m.get("content", "") for m in s1["messages"])
    assert all("Alpha" not in m.get("content", "") for m in s2["messages"])
    assert checkpoint_path("feat_001", root=root) != checkpoint_path("feat_002", root=root)


def test_boot_feature_skips_non_feature_tier(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Not feature", tier="epic", status="active")
    install_feature_boot_hook(root)
    invoke_boot("feature", "epic_001")
    with pytest.raises(ValueError):
        checkpoint_path("epic_001", root=root)


def test_checkpoint_rejects_path_traversal(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    outside = tmp_path / "escaped.sqlite"
    for bad_id in ("../evil", "feat_001/x"):
        with pytest.raises(ValueError):
            get_checkpointer(bad_id, root=root)
    assert not outside.exists()
    assert not (tmp_path / "evil.sqlite").exists()


def test_run_watchdog_installs_feature_boot_hook(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="ready_to_plan")
    add_doc(
        root,
        id="feat_001",
        title="Watchdog feature",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    from cascade.watchdog.loop import run_watchdog

    run_watchdog(root=root, poll_interval=0.01, stop_when=lambda: True)
    assert activate_epic("epic_001", "human", root=root).ok
    approve_board_feature(root, "feat_001")
    dispatch_feature("feat_001", "human", root=root)
    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert state is not None
    assert any(
        m.get("role") == "event" and "FeatureReadyToPlan" in m.get("content", "")
        for m in state["messages"]
    )


def test_boot_seeds_per_role_models_in_checkpoint(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Models feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    install_feature_boot_hook(root)
    invoke_boot("feature", "feat_001")

    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert state is not None
    assert state["model_ids"]["feature_lead"] == "proj-feature"
    assert state["model_ids"]["feature_architect"] == "proj-feature"
    assert state["model_sources"]["feature_lead"] == "project-tier"
    assert state["model_sources"]["feature_architect"] == "project-tier"


def test_boot_missing_models_table_fails_closed(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=False)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="No models",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    install_feature_boot_hook(root)
    invoke_boot("feature", "feat_001")

    assert feature_boot.last_feature_boot_model_failure() is not None
    assert not checkpoint_path("feat_001", root=root).is_file()
    war_events, _ = read_events("war_room", 0, root=root)
    assert any(
        e.type == "Toast" and e.payload.get("id") == "feat_001" for e in war_events
    )
    graph = ensure_feature_graph("feat_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "feat_001"}}).values
    assert not state or not any(
        m.get("role") in ("feature_lead", "feature_architect") for m in (state.get("messages") or [])
    )


def test_install_feature_boot_hook_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    install_feature_boot_hook(root)
    install_feature_boot_hook(root)
    from cascade.watchdog.hooks import _boot

    feature_hooks = _boot["feature"]
    assert sum(fn is feature_boot.boot_feature for fn in feature_hooks) == 1


def test_pin_parent_via_store_matches_boot_pin(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    parent = add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    pin_parent("feat_001", "epic_001", root=root)
    assert read_doc("feat_001", root=root).meta.parent_rev == parent.sha
