"""Dependency lifecycle context injected into scoped planning turns."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from cascade.agent.planning_turn import (
    _DEPENDENCY_PROJECTION_BOUNDARY,
    _DEPENDENCY_PROJECTION_HEADING,
    run_epic_planning_turn,
    run_feature_planning_turn,
)
from cascade.agent.types import RoleResult, RoleTurn
from cascade.board.store import move_doc
from cascade.epic.guard import EpicToolDenied
from cascade.epic.scoped_docs import epic_read_doc
from cascade.feature.guard import FeatureToolDenied
from cascade.feature.scoped_docs import feature_read_doc
from cascade.workspace.integration_worktree import merged_board, merged_board_snapshot
from tests.support import SyntheticDependencyLifecycle, add_doc, make_repo


def _projection_from_prompt(prompt: str) -> dict[str, object]:
    heading = f"\n\n{_DEPENDENCY_PROJECTION_HEADING}\n\n"
    payload, boundary = prompt.split(heading, 1)[1].split("\n\n", 1)
    assert boundary == _DEPENDENCY_PROJECTION_BOUNDARY
    return json.loads(payload)


def test_synthetic_completed_dependency_is_projected_without_content_access(
    synthetic_dependency_lifecycle: SyntheticDependencyLifecycle,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = synthetic_dependency_lifecycle
    captured: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        captured.append(turn)
        assert not any(
            scenario.dependency_id in path.name for path in turn.cwd.rglob("*.md")
        )
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "test-model",
            "plan",
            provider="fake",
            epic_id=scenario.owner_id,
            root=scenario.root,
        )
    )

    projection = _projection_from_prompt(captured[0].prompt)
    assert projection["outcome"] == "satisfied"
    rows = projection["dependencies"]
    assert isinstance(rows, list) and len(rows) == 1
    assert rows[0]["work_id"] == scenario.dependency_id
    assert rows[0]["status"] == "completed"
    assert rows[0]["column"] == "3_completed"
    assert rows[0]["outcome"] == "satisfied"
    assert rows[0]["completion_evidence"] == (
        "canonical_completed_in_3_completed"
    )
    assert "Synthetic private dependency" not in captured[0].prompt
    with pytest.raises(EpicToolDenied):
        epic_read_doc(
            scenario.dependency_id,
            epic_id=scenario.owner_id,
            root=scenario.root,
        )


def test_epic_turn_projects_all_dependencies_without_content_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(
        root,
        id="epic_002",
        title="Completed private epic",
        tier="epic",
        status="completed",
    )
    add_doc(
        root,
        id="epic_003",
        title="Active dependency",
        tier="epic",
        status="active",
    )
    add_doc(
        root,
        id="epic_001",
        title="Owning epic",
        tier="epic",
        status="active",
        depends_on=["epic_002", "epic_003"],
    )
    captured: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        captured.append(turn)
        assert not any("epic_002" in path.name for path in turn.cwd.rglob("*.md"))
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_epic_planning_turn(
            "epic_manager",
            "test-model",
            "original prompt",
            provider="fake",
            epic_id="epic_001",
            root=root,
        )
    )

    assert len(captured) == 1
    assert captured[0].prompt.startswith("original prompt\n\n")
    assert "Completed private epic" not in captured[0].prompt
    assert str(root) not in captured[0].prompt
    projection = _projection_from_prompt(captured[0].prompt)
    assert projection["owner_work_id"] == "epic_001"
    assert projection["outcome"] == "dependency_unmet"
    assert [row["work_id"] for row in projection["dependencies"]] == [
        "epic_002",
        "epic_003",
    ]
    assert [row["outcome"] for row in projection["dependencies"]] == [
        "satisfied",
        "dependency_unmet",
    ]
    with pytest.raises(EpicToolDenied):
        epic_read_doc("epic_002", epic_id="epic_001", root=root)


def test_feature_turn_projects_all_dependencies_without_content_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
    add_doc(
        root,
        id="feat_002",
        title="Completed private feature",
        tier="feature",
        status="completed",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_003",
        title="Active dependency",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    add_doc(
        root,
        id="feat_001",
        title="Owning feature",
        tier="feature",
        status="active",
        parent="epic_001",
        depends_on=["feat_002", "feat_003"],
    )
    captured: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        captured.append(turn)
        assert not any("feat_002" in path.name for path in turn.cwd.rglob("*.md"))
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    asyncio.run(
        run_feature_planning_turn(
            "feature_lead",
            "test-model",
            "original prompt",
            provider="fake",
            feature_id="feat_001",
            root=root,
        )
    )

    assert len(captured) == 1
    assert "Completed private feature" not in captured[0].prompt
    assert str(root) not in captured[0].prompt
    projection = _projection_from_prompt(captured[0].prompt)
    assert projection["owner_work_id"] == "feat_001"
    assert projection["outcome"] == "dependency_unmet"
    assert [row["work_id"] for row in projection["dependencies"]] == [
        "feat_002",
        "feat_003",
    ]
    assert [row["outcome"] for row in projection["dependencies"]] == [
        "satisfied",
        "dependency_unmet",
    ]
    with pytest.raises(FeatureToolDenied):
        feature_read_doc("feat_002", feature_id="feat_001", root=root)


@pytest.mark.parametrize("tier", ["epic", "feature"])
def test_planning_turn_without_dependencies_projects_satisfied(
    tier: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    if tier == "epic":
        work_id = "epic_001"
        add_doc(root, id=work_id, title="Independent", tier="epic", status="active")
    else:
        work_id = "feat_001"
        add_doc(root, id="epic_001", title="Parent", tier="epic", status="active")
        add_doc(
            root,
            id=work_id,
            title="Independent",
            tier="feature",
            status="active",
            parent="epic_001",
        )
    captured: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        captured.append(turn)
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    if tier == "epic":
        asyncio.run(
            run_epic_planning_turn(
                "epic_architect", "test-model", "plan", provider="fake",
                epic_id=work_id, root=root,
            )
        )
    else:
        asyncio.run(
            run_feature_planning_turn(
                "feature_architect", "test-model", "plan", provider="fake",
                feature_id=work_id, root=root,
            )
        )

    projection = _projection_from_prompt(captured[0].prompt)
    assert projection["outcome"] == "satisfied"
    assert projection["dependencies"] == []


def test_epic_turn_projection_ignores_request_scoped_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = make_repo(tmp_path)
    add_doc(root, id="epic_001", title="Dependency", tier="epic", status="completed")
    add_doc(
        root,
        id="epic_002",
        title="Owner",
        tier="epic",
        status="active",
        depends_on=["epic_001"],
    )
    stale = merged_board(root)
    move_doc("epic_001", "active", root=root)
    captured: list[RoleTurn] = []

    async def fake_run_role(turn: RoleTurn) -> RoleResult:
        captured.append(turn)
        return RoleResult(text="ok", status="finished")

    monkeypatch.setattr("cascade.agent.planning_turn.run_role", fake_run_role)
    with merged_board_snapshot(root, stale):
        asyncio.run(
            run_epic_planning_turn(
                "epic_manager",
                "test-model",
                "plan",
                provider="fake",
                epic_id="epic_002",
                root=root,
            )
        )

    projection = _projection_from_prompt(captured[0].prompt)
    assert projection["outcome"] == "dependency_unmet"
