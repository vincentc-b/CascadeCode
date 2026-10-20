"""Planning sandbox: scratch cwd, teardown, and guarded MCP tool dispatch."""

from __future__ import annotations

import asyncio
from pathlib import Path
import pytest

from cascade.agent.mcp_wrappers import ToolEffectCollector, dispatch_planning_tool
from cascade.agent.planning_sandbox import (
    collect_epic_readable_paths,
    materialize_scratch,
    teardown_scratch,
)
from cascade.agent import CursorAgentError
from cascade.agent.planning_turn import run_epic_planning_turn
from cascade.agent.types import RoleResult
from cascade.epic.wiring import load_epic_tools
from tests.support import add_doc, make_repo


@pytest.fixture
def epic_board(tmp_path: Path) -> dict[str, object]:
    root = make_repo(tmp_path)
    epic = add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Child",
        tier="feature",
        status="backlog",
        parent="epic_001",
    )
    return {"root": root, "epic": epic}


def test_scratch_write_does_not_touch_repo(monkeypatch: pytest.MonkeyPatch, epic_board: dict) -> None:
    root = epic_board["root"]
    epic_id = "epic_001"
    captured_cwd: list[Path] = []

    async def fake_run_role(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        captured_cwd.append(turn.cwd)
        secret = turn.cwd / "scratch_only.txt"
        secret.write_text("ephemeral\n", encoding="utf-8")
        assert secret.is_file()
        return RoleResult(text="ok", status="finished", tool_effects=[])

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)

    result = asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "composer-2.5",
            "plan",
            provider="cursor",
            epic_id=epic_id,
            root=root,
        )
    )
    assert result.status == "finished"
    assert len(captured_cwd) == 1
    scratch = captured_cwd[0]
    assert not scratch.exists()
    assert not (root / "scratch_only.txt").exists()
    assert not any(root.rglob("scratch_only.txt"))


def test_scratch_removed_after_turn(monkeypatch: pytest.MonkeyPatch, epic_board: dict) -> None:
    root = epic_board["root"]
    seen: list[Path] = []

    async def fake_run_role(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        seen.append(turn.cwd)
        assert turn.cwd.is_dir()
        return RoleResult(text="", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_architect",
            "composer-2.5",
            "x",
            provider="cursor",
            epic_id="epic_001",
            root=root,
        )
    )
    assert len(seen) == 1
    assert not seen[0].exists()


def test_dispatch_planning_tool_hits_guarded_mint_feature(
    monkeypatch: pytest.MonkeyPatch,
    epic_board: dict,
) -> None:
    root = epic_board["root"]
    load_epic_tools()
    calls: list[tuple[str, dict]] = []

    from cascade.epic.registry import epic_tools, register_epic_tool

    original = epic_tools()["mint_feature"]

    def spy_mint_feature(*args: object, **kwargs: object) -> str:
        calls.append(("mint_feature", dict(kwargs)))
        return original(*args, **kwargs)

    register_epic_tool("mint_feature", spy_mint_feature)

    collector = ToolEffectCollector()
    result = dispatch_planning_tool(
        "epic",
        "mint_feature",
        {"title": "New feature"},
        scope_id="epic_001",
        repo_root=root,
        collector=collector,
    )
    assert isinstance(result, str) and result.startswith("feat_")
    assert calls and calls[0][0] == "mint_feature"
    assert calls[0][1]["epic_id"] == "epic_001"
    assert collector.effects and collector.effects[0].tool == "mint_feature"


def test_materialize_only_allowed_epic_docs(epic_board: dict) -> None:
    root = epic_board["root"]
    epic = epic_board["epic"]
    paths = collect_epic_readable_paths("epic_001", root=root)
    scratch = materialize_scratch(root, paths, tier="epic")
    try:
        epic_rel = epic.meta.path.relative_to(root)
        assert (scratch / epic_rel).is_file()
        assert (scratch / "docs" / "features" / "1_backlog" / "feat_001_child.md").is_file()
        assert not (scratch / "docs" / "tasks").exists()
    finally:
        teardown_scratch(scratch)


def test_run_role_receives_cursor_custom_tools(
    monkeypatch: pytest.MonkeyPatch, epic_board: dict
) -> None:
    root = epic_board["root"]
    turns: list[object] = []

    async def fake_run_role(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        turns.append(turn)
        return RoleResult(text="", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "composer-2.5",
            "hi",
            provider="cursor",
            epic_id="epic_001",
            root=root,
        )
    )
    assert len(turns) == 1
    turn = turns[0]
    from cascade.agent.types import RoleTurn

    assert isinstance(turn, RoleTurn)
    assert turn.tools == []
    assert turn.custom_tools is not None
    assert "write_doc" in turn.custom_tools
    assert "read_doc" in turn.custom_tools


def test_run_role_receives_mcp_mapping_for_claude(
    monkeypatch: pytest.MonkeyPatch, epic_board: dict
) -> None:
    root = epic_board["root"]
    tools_seen: list[object] = []

    async def fake_run_role(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        tools_seen.append(turn.tools)
        return RoleResult(text="", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "composer-2.5",
            "hi",
            provider="claude",
            epic_id="epic_001",
            root=root,
        )
    )
    assert len(tools_seen) == 1
    tools = tools_seen[0]
    assert isinstance(tools, dict)
    assert "cascade" in tools
    assert tools["cascade"]["command"]


def test_blank_model_id_before_scratch(monkeypatch: pytest.MonkeyPatch, epic_board: dict) -> None:
    root = epic_board["root"]
    materialized: list[Path] = []

    def spy_materialize(*args: object, **kwargs: object) -> Path:
        scratch = materialize_scratch(*args, **kwargs)  # type: ignore[arg-type]
        materialized.append(scratch)
        return scratch

    monkeypatch.setattr("cascade.agent.planning_turn.materialize_scratch", spy_materialize)

    with pytest.raises(ValueError, match="model_id"):
        asyncio.run(
            run_epic_planning_turn(
                "epic_manager",
                "   ",
                "plan",
                provider="cursor",
                epic_id="epic_001",
                root=root,
            )
        )
    assert materialized == []


def test_scratch_removed_when_run_role_raises_cursor_error(
    monkeypatch: pytest.MonkeyPatch,
    epic_board: dict,
) -> None:
    root = epic_board["root"]
    seen: list[Path] = []

    async def fail_run_role(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        seen.append(turn.cwd)
        raise CursorAgentError("startup fail", retryable=False)

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fail_run_role)

    with pytest.raises(CursorAgentError):
        asyncio.run(
            run_epic_planning_turn(
                "epic_manager",
                "composer-2.5",
                "plan",
                provider="cursor",
                epic_id="epic_001",
                root=root,
            )
        )

    assert len(seen) == 1
    assert not seen[0].exists()


def test_materialize_skips_symlink_escape(epic_board: dict) -> None:
    root = epic_board["root"]
    outside = root.parent / "outside_secret.txt"
    outside.write_text("secret\n", encoding="utf-8")
    link = root / "escape_link.md"
    link.symlink_to(outside)
    scratch = materialize_scratch(root, [link], tier="epic")
    try:
        assert not (scratch / "escape_link.md").exists()
        assert not any(scratch.rglob("outside_secret.txt"))
    finally:
        teardown_scratch(scratch)
