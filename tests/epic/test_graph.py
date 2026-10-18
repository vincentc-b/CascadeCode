"""Epic graph role-turn wiring (task_048)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.types import RoleResult
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc
from cascade.epic.graph import clear_epic_graph_sessions, ensure_epic_graph, ingest_human, seed_epic_role_models
from cascade.watchdog.model_resolve import resolve_backend
from tests.support import TEST_MODEL_ID, install_fake_planning_turns
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_epic_graph_sessions()
    yield
    clear_epic_graph_sessions()


def test_missing_model_id_does_not_call_planning_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, role_skills=True)
    called = False

    async def boom(*_args, **_kwargs) -> RoleResult:
        nonlocal called
        called = True
        return RoleResult(text="nope", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", boom)
    state = ingest_human(
        "epic_001",
        {"role": "human", "content": "Hello"},
        root=root,
    )
    assert called is False
    manager = next(m for m in state["messages"] if m.get("role") == "epic_manager")
    assert "model_id is required" in manager["content"]


@pytest.fixture
def fake_planning_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_planning_turns(monkeypatch)


def test_adapter_text_becomes_role_message(
    tmp_path: Path,
    fake_planning_turns: None,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    state = ingest_human(
        "epic_001",
        {"role": "human", "content": "Plan"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    manager = next(m for m in state["messages"] if m.get("role") == "epic_manager")
    assert manager["content"].startswith("epic_manager:")
    assert "Plan" in manager["content"]


def test_per_role_model_ids_and_source_in_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    doc = add_doc(root, id="epic_001", title="Split models", tier="epic", status="active")
    write_doc(
        WorkDoc(
            meta=replace(doc.meta, models={"epic_manager": "mgr-doc-role"}),
            body=doc.body,
            sha=doc.sha,
        ),
        root=root,
    )
    meta = read_doc("epic_001", root=root).meta
    manager = resolve_backend("epic_manager", meta, root=root)
    architect = resolve_backend("epic_architect", meta, root=root)
    seed_epic_role_models(
        "epic_001",
        manager=manager,
        architect=architect,
        root=root,
    )

    calls: list[tuple[str, str, str]] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        calls.append((role, model_id, prompt))
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake)
    ingest_human("epic_001", {"role": "human", "content": "Plan"}, root=root)

    assert len(calls) == 2
    assert calls[0][1] == "mgr-doc-role"
    assert calls[1][1] == "proj-epic"
    assert "source: document-role" in calls[0][2]
    assert "source: project-tier" in calls[1][2]


def test_turn_model_id_does_not_persist_in_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    doc = add_doc(root, id="epic_001", title="Persist", tier="epic", status="active")
    write_doc(
        WorkDoc(
            meta=replace(doc.meta, models={"epic_manager": "mgr-seeded"}),
            body=doc.body,
            sha=doc.sha,
        ),
        root=root,
    )
    meta = read_doc("epic_001", root=root).meta
    manager = resolve_backend("epic_manager", meta, root=root)
    architect = resolve_backend("epic_architect", meta, root=root)
    seed_epic_role_models(
        "epic_001",
        manager=manager,
        architect=architect,
        root=root,
    )

    calls: list[str] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        calls.append(model_id)
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake)
    ingest_human(
        "epic_001",
        {"role": "human", "content": "override turn"},
        root=root,
        model_id="http-override-model",
    )
    ingest_human("epic_001", {"role": "human", "content": "normal turn"}, root=root)

    assert calls[0] == "http-override-model"
    assert calls[1] == "http-override-model"
    assert calls[2] == "mgr-seeded"
    assert calls[3] == "proj-epic"

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    assert state.get("model_id") in (None, "")


def test_run_error_surfaces_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)

    async def run_failed(*_args, **_kwargs) -> RoleResult:
        return RoleResult(text="agent blew up", status="error")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", run_failed)
    state = ingest_human(
        "epic_001",
        {"role": "human", "content": "Go"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    manager = next(m for m in state["messages"] if m.get("role") == "epic_manager")
    assert "turn failed" in manager["content"]
    assert "agent blew up" in manager["content"]


def test_planning_prompt_includes_role_skills_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    calls: list[str] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        calls.append(prompt)
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake)
    ingest_human(
        "epic_001",
        {"role": "human", "content": "Plan"},
        root=root,
        model_id=TEST_MODEL_ID,
    )

    assert len(calls) == 2
    manager_prompt = calls[0]
    architect_prompt = calls[1]
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in manager_prompt
    assert "FIXTURE_PM_SCOPE_GUARD" in manager_prompt
    assert "skills/roles/frugal_engineering/SKILL.md" in manager_prompt
    assert "skills/roles/product_manager/SKILL.md" in manager_prompt
    assert "Role skill paths:" in manager_prompt
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in architect_prompt
    assert "FIXTURE_PM_SCOPE_GUARD" not in architect_prompt
    assert "skills/roles/frugal_engineering/SKILL.md" in architect_prompt


def test_missing_role_skill_playbook_does_not_call_planning_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True)
    called = False

    async def boom(*_args, **_kwargs) -> RoleResult:
        nonlocal called
        called = True
        return RoleResult(text="nope", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", boom)
    state = ingest_human(
        "epic_001",
        {"role": "human", "content": "Hello"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    assert called is False
    manager = next(m for m in state["messages"] if m.get("role") == "epic_manager")
    assert "role skill playbook error" in manager["content"]
