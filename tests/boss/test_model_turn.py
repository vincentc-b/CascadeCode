"""Boss lieutenant model turn wiring (task_048)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.agent.errors import CursorAgentError
from cascade.agent.types import RoleResult
from cascade.boss.model_turn import produce_boss_reply
from tests.support import TEST_MODEL_ID, make_repo


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

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", boom)
    reply = produce_boss_reply(None, "prompt", root=root, provider_id="cursor")
    assert called is False
    assert "model_id is required" in reply.content


def test_startup_error_surfaces_in_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, role_skills=True)

    async def boom(*_args, **_kwargs) -> RoleResult:
        raise CursorAgentError("network down", retryable=True)

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", boom)
    reply = produce_boss_reply(TEST_MODEL_ID, "prompt", root=root, provider_id="cursor")
    assert "startup failed" in reply.content
    assert "network down" in reply.content


def test_adapter_text_becomes_boss_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, role_skills=True)

    async def fake(_model_id: str, _prompt: str, *, provider: str, root: Path) -> RoleResult:
        return RoleResult(text="boss says hi", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", fake)
    reply = produce_boss_reply(TEST_MODEL_ID, "hello", root=root, provider_id="cursor")
    assert reply.content == "boss says hi"
    assert reply.role == "boss"


def test_boss_wiring_falls_back_to_epic_tier_without_boss_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, models=True, role_skills=True)
    captured: dict[str, str] = {}

    async def fake(_model_id: str, prompt: str, *, provider: str, root: Path) -> RoleResult:
        captured["model_id"] = _model_id
        captured["prompt"] = prompt
        return RoleResult(text="boss ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", fake)
    monkeypatch.setattr(
        "cascade.war_room.chat_store.read_messages",
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        "cascade.boss.wiring.append_transcript_message",
        lambda *_args, **_kwargs: {"id": "1", "author": "boss", "body": "boss ok"},
    )

    from cascade.boss.wiring import accept_boss_chat

    accept_boss_chat({"body": "hello"}, root=root, model_id=None)
    assert captured["model_id"] == "proj-epic"
    assert "source: boss-falls-back-to-epic" in captured["prompt"]


def test_run_error_surfaces_in_boss_reply(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, role_skills=True)

    async def run_failed(_model_id: str, _prompt: str, *, provider: str, root: Path) -> RoleResult:
        return RoleResult(text="boss run failed", status="error")

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", run_failed)
    reply = produce_boss_reply(TEST_MODEL_ID, "prompt", root=root, provider_id="cursor")
    assert "turn failed" in reply.content
    assert "boss run failed" in reply.content


def test_boss_prompt_includes_role_skills_and_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path, role_skills=True)
    captured: dict[str, str] = {}

    async def fake(_model_id: str, prompt: str, *, provider: str, root: Path) -> RoleResult:
        captured["prompt"] = prompt
        return RoleResult(text="boss ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", fake)
    from cascade.boss.model_turn import produce_boss_reply

    produce_boss_reply(TEST_MODEL_ID, "[human] hello", root=root, provider_id="cursor")
    prompt = captured["prompt"]
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in prompt
    assert "FIXTURE_EM_PROCESS_FRUGALITY" in prompt
    assert "skills/roles/engineering_manager/SKILL.md" in prompt
    assert "Role skill paths:" in prompt


def test_missing_role_skill_playbook_does_not_call_boss_turn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = make_repo(tmp_path)
    called = False

    async def boom(*_args, **_kwargs) -> RoleResult:
        nonlocal called
        called = True
        return RoleResult(text="nope", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_boss_planning_turn", boom)
    reply = produce_boss_reply(TEST_MODEL_ID, "prompt", root=root, provider_id="cursor")
    assert called is False
    assert "role skill playbook error" in reply.content
