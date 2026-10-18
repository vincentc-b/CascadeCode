"""Task LangGraph runtime: checkpoint, ingest, boot hook, stale parent_rev."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import cascade.task.boot as task_boot
import cascade.task.graph as task_graph
from cascade.task import (
    clear_task_tools,
    ensure_task_graph,
    fail_closed_boot,
    ingest_queue,
    install_task_boot_hook,
    invoke_tool,
    last_fail_closed_boot,
    register_task_tool,
)
from cascade.task.graph import clear_task_graph_sessions, ensure_task_graph
from cascade.task.checkpoint import checkpoint_path, get_checkpointer, thread_config
from cascade.task.wiring import clear_task_wiring_state, install_task_wiring
from cascade.board.store import pin_parent, read_doc, write_doc
from cascade.watchdog import append_event
from cascade.watchdog.events import read_events
from cascade.watchdog.hooks import clear_hooks, invoke_boot
from cascade.watchdog.types import Event
from tests.support import add_doc, make_repo, write_swe_default_role_skills


@pytest.fixture(autouse=True)
def _task_test_isolation() -> None:
    clear_hooks()
    clear_task_tools()
    clear_task_graph_sessions()
    clear_task_wiring_state()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None
    yield
    clear_hooks()
    clear_task_tools()
    clear_task_graph_sessions()
    clear_task_wiring_state()
    task_boot._boot_root = None
    task_boot._last_fail_closed = None


def test_checkpoint_file_created(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    ensure_task_graph("task_001", root=root, feature_id="feat_001")
    path = checkpoint_path("task_001", root=root)
    assert path.is_file()
    assert path.parent == root / ".cascade" / "checkpoints"


def test_ingest_queue_advances_offset_and_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    event = Event(
        type="TaskDispatched",
        ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
        payload={"task_id": "task_001", "feature_id": "feat_001", "by": "human"},
        dest="task_001",
    )
    append_event("task_001", event, root=root)

    first = ingest_queue("task_001", root=root, feature_id="feat_001")
    events = [m for m in first["messages"] if m.get("role") == "event"]
    assert len(events) == 1
    assert "TaskDispatched" in events[0]["content"]
    assert first["last_queue_offset"] > 0
    assert first["skill_playbooks"] == []

    second = ingest_queue("task_001", root=root, feature_id="feat_001")
    assert second["last_queue_offset"] == first["last_queue_offset"]
    assert len([m for m in second["messages"] if m.get("role") == "event"]) == 1


def test_ingest_queue_does_not_run_task_swe(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    append_event(
        "task_001",
        Event(
            type="TaskDispatched",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"task_id": "task_001", "feature_id": "feat_001", "by": "human"},
            dest="task_001",
        ),
        root=root,
    )
    state = ingest_queue("task_001", root=root, feature_id="feat_001")
    assert not any(m.get("role") == "task_swe" for m in state["messages"])


def test_task_activated_on_feature_queue(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Parent feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Boot task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_001", "feat_001", root=root)
    install_task_boot_hook(root)
    invoke_boot("task", "task_001")

    events, _ = read_events("feat_001", 0, root=root)
    activated = [event for event in events if event.type == "TaskActivated"]
    assert len(activated) == 1
    assert activated[0].dest == "feat_001"
    assert activated[0].payload["task_id"] == "task_001"
    assert activated[0].payload["feature_id"] == "feat_001"


def test_stale_parent_rev_fail_closed_no_activation(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Parent feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Stale task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_001", "feat_001", root=root)
    stale_rev = read_doc("task_001", root=root).meta.parent_rev
    assert stale_rev is not None

    feature = read_doc("feat_001", root=root)
    feature.body = feature.body + "\nRevised feature body.\n"
    write_doc(feature, root=root)
    assert read_doc("feat_001", root=root).sha != stale_rev

    install_task_boot_hook(root)
    invoke_boot("task", "task_001")

    assert last_fail_closed_boot() == ("task_001", "stale_parent_rev")
    events, _ = read_events("feat_001", 0, root=root)
    assert not any(event.type == "TaskActivated" for event in events)
    assert not checkpoint_path("task_001", root=root).exists()


def test_install_task_boot_hook_is_idempotent(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    install_task_boot_hook(root)
    install_task_boot_hook(root)
    from cascade.watchdog.hooks import _boot

    task_hooks = _boot["task"]
    assert sum(fn is task_boot.boot_task for fn in task_hooks) == 1


def test_two_tasks_do_not_share_messages(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    append_event(
        "task_001",
        Event(
            type="TaskDispatched",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"task_id": "task_001", "feature_id": "feat_001", "by": "human"},
            dest="task_001",
        ),
        root=root,
    )
    append_event(
        "task_002",
        Event(
            type="TaskDispatched",
            ts=datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc),
            payload={"task_id": "task_002", "feature_id": "feat_001", "by": "human"},
            dest="task_002",
        ),
        root=root,
    )
    ingest_queue("task_001", root=root, feature_id="feat_001")
    ingest_queue("task_002", root=root, feature_id="feat_001")

    g1 = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    g2 = ensure_task_graph("task_002", root=root, feature_id="feat_001")
    s1 = g1.get_state({"configurable": {"thread_id": "task_001"}}).values
    s2 = g2.get_state({"configurable": {"thread_id": "task_002"}}).values
    assert s1 and s2
    assert all("task_002" not in m.get("content", "") for m in s1["messages"])
    assert all("task_001" not in m.get("content", "") for m in s2["messages"])
    assert checkpoint_path("task_001", root=root) != checkpoint_path("task_002", root=root)


def test_invoke_tool_uses_registry(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    def ping(**_kwargs: object) -> str:
        return "pong"

    register_task_tool("ping", ping)
    result = invoke_tool("task_001", "ping", {}, root=root, feature_id="feat_001")
    assert result == "pong"

    graph = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    state = graph.get_state({"configurable": {"thread_id": "task_001"}}).values
    tools = [m for m in state["messages"] if m.get("role") == "tool"]
    assert len(tools) == 1
    assert tools[0]["name"] == "ping"
    assert tools[0]["content"] == "pong"


def test_boot_task_skips_non_task_tier(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Not task",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    install_task_boot_hook(root)
    invoke_boot("task", "feat_001")
    with pytest.raises(ValueError):
        checkpoint_path("feat_001", root=root)


def test_checkpoint_rejects_path_traversal(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    outside = tmp_path / "escaped.sqlite"
    for bad_id in ("../evil", "task_001/x"):
        with pytest.raises(ValueError):
            get_checkpointer(bad_id, root=root)
    assert not outside.exists()
    assert not (tmp_path / "evil.sqlite").exists()


def test_fail_closed_boot_is_observable(tmp_path: Path) -> None:
    fail_closed_boot("task_099", reason="stale_parent_rev")
    assert last_fail_closed_boot() == ("task_099", "stale_parent_rev")


def test_boot_seeds_swe_model_in_checkpoint(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Parent feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Boot task",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_001", "feat_001", root=root)
    install_task_boot_hook(root)
    invoke_boot("task", "task_001")

    graph = ensure_task_graph("task_001", root=root, feature_id="feat_001")
    state = graph.get_state({"configurable": {"thread_id": "task_001"}}).values
    assert state is not None
    assert state["model_ids"]["swe"] == "proj-task"
    assert state["model_sources"]["swe"] == "project-tier"


def _boot_ready_board(tmp_path: Path, *, skills: list | None = None) -> tuple[Path, str]:
    root = make_repo(tmp_path, models=True)
    write_swe_default_role_skills(root)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Parent feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="Boot task",
        tier="task",
        status="active",
        parent="feat_001",
        skills=[Path(p) for p in skills] if skills is not None else None,
    )
    pin_parent("task_001", "feat_001", root=root)
    return root, "task_001"


def test_boot_empty_task_skills_seeds_role_default_playbooks(tmp_path: Path) -> None:
    root, task_id = _boot_ready_board(tmp_path, skills=[])
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    graph = ensure_task_graph(task_id, root=root, feature_id="feat_001")
    values = graph.get_state(thread_config(task_id)).values
    assert values is not None
    paths = [entry["path"] for entry in values["skill_playbooks"]]
    assert paths == [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
    ]


def test_boot_unions_extra_task_skill_with_role_defaults(tmp_path: Path) -> None:
    root, task_id = _boot_ready_board(tmp_path)
    extra = root / "skills" / "custom" / "SKILL.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("custom\n", encoding="utf-8")
    task = read_doc(task_id, root=root)
    task.meta.skills = [extra.relative_to(root)]
    write_doc(task, root=root)

    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    graph = ensure_task_graph(task_id, root=root, feature_id="feat_001")
    values = graph.get_state(thread_config(task_id)).values
    assert values is not None
    paths = [entry["path"] for entry in values["skill_playbooks"]]
    assert paths == [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
        "skills/custom/SKILL.md",
    ]


def test_boot_illegal_task_skill_path_fails_closed(tmp_path: Path) -> None:
    root, task_id = _boot_ready_board(tmp_path, skills=["skills/missing/SKILL.md"])
    install_task_boot_hook(root)
    install_task_wiring(root)
    invoke_boot("task", task_id)

    assert read_doc(task_id, root=root).meta.status == "blocked"
    events, _ = read_events("feat_001", 0, root=root)
    failed = [e for e in events if e.type == "TaskFailed"]
    assert len(failed) == 1
    assert failed[0].payload["reason"].startswith("skill_path_error:")


def test_boot_missing_models_table_fail_closed_no_graph(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=False)
    add_doc(root, id="epic_001", title="Parent epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Parent feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="task_001",
        title="No models",
        tier="task",
        status="active",
        parent="feat_001",
    )
    pin_parent("task_001", "feat_001", root=root)
    install_task_boot_hook(root)
    invoke_boot("task", "task_001")

    assert last_fail_closed_boot() is not None
    assert last_fail_closed_boot()[0] == "task_001"
    assert not checkpoint_path("task_001", root=root).exists()
    war_events, _ = read_events("war_room", 0, root=root)
    assert any(
        e.type == "Toast" and e.payload.get("id") == "task_001" for e in war_events
    )
