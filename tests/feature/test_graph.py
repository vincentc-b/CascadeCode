"""Feature graph role-turn wiring (task_048)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from cascade.agent.types import RoleResult
from cascade.board.store import read_doc, write_doc
from cascade.board.types import WorkDoc
from cascade.feature.graph import clear_feature_graph_sessions, ingest_human, seed_feature_role_models
from cascade.watchdog.model_resolve import resolve_backend
from tests.support import TEST_MODEL_ID, install_fake_planning_turns
from tests.support import add_doc, make_repo


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_feature_graph_sessions()
    yield
    clear_feature_graph_sessions()


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

    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", boom)
    state = ingest_human(
        "feat_001",
        {"role": "human", "content": "Hello"},
        root=root,
    )
    assert called is False
    assert not [m for m in state["messages"] if m.get("role") == "feature_lead"]
    assert any(m.get("role") == "human" for m in state["messages"])


@pytest.fixture
def fake_planning_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    install_fake_planning_turns(monkeypatch)


def test_adapter_text_becomes_role_message(
    tmp_path: Path,
    fake_planning_turns: None,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    state = ingest_human(
        "feat_001",
        {"role": "human", "content": "Scope"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    lead = next(m for m in state["messages"] if m.get("role") == "feature_lead")
    assert lead["content"].startswith("feature_lead:")
    assert "Scope" in lead["content"]


def test_per_role_model_ids_and_source_in_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    doc = add_doc(
        root,
        id="feat_001",
        title="Split models",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    write_doc(
        WorkDoc(
            meta=replace(doc.meta, models={"feature_lead": "lead-doc-role"}),
            body=doc.body,
            sha=doc.sha,
        ),
        root=root,
    )
    meta = read_doc("feat_001", root=root).meta
    lead = resolve_backend("feature_lead", meta, root=root)
    architect = resolve_backend("feature_architect", meta, root=root)
    seed_feature_role_models(
        "feat_001",
        lead=lead,
        architect=architect,
        root=root,
    )

    calls: list[tuple[str, str, str]] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        calls.append((role, model_id, prompt))
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", fake)
    ingest_human("feat_001", {"role": "human", "content": "Scope"}, root=root)

    assert len(calls) == 2
    assert calls[0][1] == "lead-doc-role"
    assert calls[1][1] == "proj-feature"
    assert "source: document-role" in calls[0][2]
    assert "source: project-tier" in calls[1][2]


def test_run_error_surfaces_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)

    async def run_failed(*_args, **_kwargs) -> RoleResult:
        return RoleResult(text="feature agent error", status="error")

    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", run_failed)
    state = ingest_human(
        "feat_001",
        {"role": "human", "content": "Go"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    lead = next(m for m in state["messages"] if m.get("role") == "feature_lead")
    assert "turn failed" in lead["content"]
    assert "feature agent error" in lead["content"]


def test_planning_prompt_includes_role_skills_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    calls: list[str] = []

    async def fake(role: str, model_id: str, prompt: str, **_kwargs: object) -> RoleResult:
        calls.append(prompt)
        return RoleResult(text=f"{role}:ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", fake)
    ingest_human(
        "feat_001",
        {"role": "human", "content": "Scope"},
        root=root,
        model_id=TEST_MODEL_ID,
    )

    assert len(calls) == 2
    lead_prompt = calls[0]
    architect_prompt = calls[1]
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in lead_prompt
    assert "FIXTURE_PM_SCOPE_GUARD" in lead_prompt
    assert "skills/roles/product_manager/SKILL.md" in lead_prompt
    assert "Role skill paths:" in lead_prompt
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in architect_prompt
    assert "FIXTURE_PM_SCOPE_GUARD" not in architect_prompt


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

    monkeypatch.setattr("cascade.agent.planning_turn.run_feature_planning_turn", boom)
    state = ingest_human(
        "feat_001",
        {"role": "human", "content": "Hello"},
        root=root,
        model_id=TEST_MODEL_ID,
    )
    assert called is False
    lead = next(m for m in state["messages"] if m.get("role") == "feature_lead")
    assert "role skill playbook error" in lead["content"]
