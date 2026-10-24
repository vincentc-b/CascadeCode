"""Brief defaults propagate through mint and execution handoffs (task_006_002_003)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

import cascade.epic.mint  # noqa: F401
import cascade.feature.mint  # noqa: F401
from cascade.board.store import read_doc, reset_id_reservations, write_doc
from cascade.board.types import WorkDoc
from cascade.epic.graph import clear_epic_graph_sessions, ingest_human, seed_epic_role_models
from cascade.epic.mint import mint_feature
from cascade.feature.mint import mint_task
from cascade.task.graph import clear_task_graph_sessions, seed_task_role_models
from cascade.watchdog.model_resolve import resolve_backend
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _reset_ids() -> None:
    reset_id_reservations()
    yield
    reset_id_reservations()


@pytest.fixture(autouse=True)
def _graph_isolation() -> None:
    clear_epic_graph_sessions()
    clear_task_graph_sessions()
    yield
    clear_epic_graph_sessions()
    clear_task_graph_sessions()


def _stack_epic(root: Path) -> WorkDoc:
    add_doc(root, id="epic_001", title="Stack epic", tier="epic", status="active")
    epic = read_doc("epic_001", root=root)
    write_doc(
        WorkDoc(
            meta=replace(
                epic.meta,
                provider="cursor",
                models={
                    "epic_manager": "mgr-model",
                    "epic_architect": "arch-model",
                    "feature_lead": "lead-model",
                    "feature_architect": "fa-model",
                    "swe": "swe-model",
                },
                reasoning={
                    "epic_manager": "high",
                    "epic_architect": "low",
                    "swe": "high",
                },
            ),
            body=epic.body,
            sha=epic.sha,
        ),
        root=root,
    )
    feature = add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    epic = read_doc("epic_001", root=root)
    epic.meta.children = ["feat_001"]
    write_doc(epic, root=root)
    feature = read_doc("feat_001", root=root)
    feature.meta.children = []
    write_doc(feature, root=root)
    return read_doc("epic_001", root=root)


def test_mint_feature_copies_reasoning_from_epic(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _stack_epic(root)
    feature_id = mint_feature("Child", epic_id="epic_001", root=root)
    child = read_doc(feature_id, root=root)
    assert child.meta.reasoning == {
        "feature_lead": "high",
        "feature_architect": "low",
    }


def test_mint_task_stamps_swe_defaults_from_epic_stack(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    _stack_epic(root)
    task_id = mint_task("Slice", feature_id="feat_001", root=root)
    task = read_doc(task_id, root=root)
    assert task.meta.provider == "cursor"
    assert task.meta.models == {"swe": "swe-model"}
    assert task.meta.reasoning == {"swe": "high"}


def test_resolve_backend_uses_stamped_task_defaults(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    _stack_epic(root)
    task_id = mint_task("Slice", feature_id="feat_001", root=root)
    meta = read_doc(task_id, root=root).meta
    backend = resolve_backend("swe", meta, root=root)
    assert backend.model.model_id == "swe-model"
    assert backend.model.source == "document-role"
    assert backend.provider == "cursor"
    assert backend.reasoning == "high"
    assert backend.reasoning_source == "document-role"


def test_seed_task_checkpoint_retains_reasoning(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    _stack_epic(root)
    task_id = mint_task("Slice", feature_id="feat_001", root=root)
    meta = read_doc(task_id, root=root).meta
    swe = resolve_backend("swe", meta, root=root)
    seed_task_role_models(task_id, swe=swe, root=root, feature_id="feat_001")

    from cascade.task.graph import ensure_task_graph

    state = ensure_task_graph(task_id, root=root, feature_id="feat_001").get_state(
        {"configurable": {"thread_id": task_id}}
    ).values
    assert state is not None
    assert state["reasoning_ids"]["swe"] == "high"


def test_epic_boot_seeds_reasoning_into_checkpoint(tmp_path: Path) -> None:
    root = make_repo(tmp_path, models=True)
    _stack_epic(root)
    from cascade.epic.boot import install_epic_boot_hook
    from cascade.epic.graph import ensure_epic_graph
    from cascade.watchdog.hooks import invoke_boot

    install_epic_boot_hook(root)
    invoke_boot("epic", "epic_001")

    graph = ensure_epic_graph("epic_001", root=root)
    state = graph.get_state({"configurable": {"thread_id": "epic_001"}}).values
    assert state is not None
    assert state["reasoning_ids"]["epic_manager"] == "high"
    assert state["reasoning_sources"]["epic_manager"] == "document-role"


def test_planning_turn_prompt_includes_saved_reasoning(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    _stack_epic(root)
    meta = read_doc("epic_001", root=root).meta
    manager = resolve_backend("epic_manager", meta, root=root)
    architect = resolve_backend("epic_architect", meta, root=root)
    seed_epic_role_models(
        "epic_001",
        manager=manager,
        architect=architect,
        root=root,
    )

    from cascade.agent.types import RoleResult

    prompts: list[str] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        prompts.append(prompt)
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_epic_planning_turn", fake)
    ingest_human("epic_001", {"role": "human", "content": "Plan"}, root=root)
    assert any("Assigned reasoning: high (source: document-role)" in p for p in prompts)
