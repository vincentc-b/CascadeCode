"""First-turn declaration works from the public tool contract alone."""

from __future__ import annotations

import asyncio
import subprocess
import sys

import pytest

from cascade.agent.mcp_wrappers import (
    ToolEffectCollector,
    dispatch_planning_tool,
    mcp_tool_catalog,
)
from cascade.agent.planning_turn import run_epic_planning_turn
from cascade.agent.types import RoleResult
from cascade.epic.dependency_manifests import read_dependency_manifest_history


@pytest.fixture
def board(tmp_path):
    from tests.epic.test_dependency_manifest_authoring import board as fixture

    return fixture.__wrapped__(tmp_path)


def call(root, name, args=None):
    return dispatch_planning_tool(
        "epic",
        name,
        args or {},
        scope_id="epic_001",
        repo_root=root,
        collector=ToolEffectCollector(),
        role="epic_manager",
    )


def test_missing_read_returns_complete_usable_contract_without_declaring_or_installing(
    board,
):
    result = call(board, "read_dependency_manifest")
    authoring = result["authoring"]
    assert result["manifest"] is None and result["manifest_revision"] == 0
    assert authoring["state"] == "declaration_required"
    assert authoring["expected_revision"] == 0
    assert authoring["observed_local_environment"]["repository"] == str(board)
    assert read_dependency_manifest_history("epic_001", root=board) == ()
    tool = mcp_tool_catalog("epic", ["write_dependency_manifest"])[0]
    schema = tool["inputSchema"]["properties"]["manifest"]
    assert schema == authoring["manifest_schema"]
    assert schema["additionalProperties"] is False
    # Construct an explicit declaration entirely from the returned contract.
    # The fixture has no prerequisites; production callers must assess theirs.
    created = call(
        board,
        "write_dependency_manifest",
        {
            "expected_revision": authoring["expected_revision"],
            "manifest": {
                "target_environment": authoring["observed_local_environment"],
                "actual_environment": None,
                "none_required": True,
                "dependencies": [],
            },
        },
    )
    assert created["authoring"]["state"] == "declared"
    assert created["software_dependency_status"]["status"] == "ready"
    assert not created["software_dependency_status"]["errors"]
    code = "from cascade.board.store import list_board; from cascade.epic.dependency_manifest_authoring import read_dependency_manifest; from pathlib import Path; import sys; print(read_dependency_manifest(epic_id='epic_001',root=Path(sys.argv[1]))['manifest_revision'])"
    loaded = subprocess.run(
        [sys.executable, "-c", code, str(board)],
        capture_output=True,
        text=True,
        check=True,
    )
    assert loaded.stdout.strip() == "1"
    assert len(read_dependency_manifest_history("epic_001", root=board)) == 1


@pytest.mark.parametrize("declare", [False, True])
def test_epic_first_turn_requires_durable_declaration_before_finished(
    board, monkeypatch, declare
):
    captured = []

    async def run(turn):
        captured.append(turn)
        assert "Dependency declaration phase" in turn.prompt
        assert "observed_local_environment" in turn.prompt
        assert "installation" in turn.prompt.lower()
        if declare:
            context = call(board, "read_dependency_manifest")["authoring"]
            call(
                board,
                "write_dependency_manifest",
                {
                    "expected_revision": 0,
                    "manifest": {
                        "target_environment": context["observed_local_environment"],
                        "actual_environment": None,
                        "none_required": True,
                        "dependencies": [],
                    },
                },
            )
        return RoleResult(text="Completed planning", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", run)
    result = asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "test-model",
            "Plan the epic",
            provider="fake",
            epic_id="epic_001",
            root=board,
        )
    )
    assert result.status == ("finished" if declare else "error")
    if not declare:
        assert "Dependency declaration incomplete" in result.text
        assert read_dependency_manifest_history("epic_001", root=board) == ()
    else:
        captured.clear()

        async def resumed(turn):
            assert "Dependency declaration phase" not in turn.prompt
            return RoleResult(text="Continue existing planning", status="finished")

        monkeypatch.setattr("cascade.agent.planning_turn.run_role", resumed)
        result = asyncio.run(
            run_epic_planning_turn(
                "epic_architect",
                "test-model",
                "Review",
                provider="fake",
                epic_id="epic_001",
                root=board,
            )
        )
        assert result.status == "finished"
        assert len(read_dependency_manifest_history("epic_001", root=board)) == 1
