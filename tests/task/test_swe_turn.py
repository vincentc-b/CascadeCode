"""SWE turn prompt includes seeded skill playbook text and paths (feat_013)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cascade.agent import RoleResult
from cascade.board.store import read_doc
from cascade.task.registry import clear_task_tools
from cascade.task.skills_context import apply_skill_playbooks
from cascade.task.swe_turn import run_swe_turn_sync
from cascade.task.wiring import clear_task_wiring_state, install_task_wiring
from cascade.task.worktree import clear_task_runs, create_task_worktree
from cascade.watchdog.hooks import clear_hooks
from tests.support import add_doc, make_repo, write_role_skill_fixtures


@pytest.fixture(autouse=True)
def _isolation() -> None:
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()
    yield
    clear_hooks()
    clear_task_tools()
    clear_task_runs()
    clear_task_wiring_state()


def _initial_commit(root: Path) -> None:
    (root / "README.md").write_text("board\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=root, check=True, capture_output=True)


def test_swe_prompt_includes_playbook_text_and_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_role_skill_fixtures(root)
    _initial_commit(root)
    add_doc(root, id="epic_001", title="Epic", tier="epic", status="active")
    add_doc(
        root,
        id="feat_001",
        title="Feature",
        tier="feature",
        status="active",
        parent="epic_001",
    )
    task_id = "task_063"
    add_doc(
        root,
        id=task_id,
        title="SWE skills prompt",
        tier="task",
        status="active",
        parent="feat_001",
    )
    create_task_worktree(
        task_id,
        root=root,
        parent_rev=read_doc(task_id, root=root).meta.parent_rev,
        skills=[],
    )
    install_task_wiring(root)

    playbooks = [
        {
            "path": "skills/roles/frugal_engineering/SKILL.md",
            "text": "# Fixture playbook\nFIXTURE_FRUGAL_PHILOSOPHY\n",
        },
        {
            "path": "skills/roles/software_developer/SKILL.md",
            "text": "# Fixture playbook\nFIXTURE_SW_DEV_SIMPLICITY\n",
        },
    ]
    apply_skill_playbooks(task_id, playbooks, root=root)

    captured: list[str] = []

    async def capture_prompt(turn: object) -> RoleResult:
        from cascade.agent.types import RoleTurn

        assert isinstance(turn, RoleTurn)
        captured.append(turn.prompt)
        return RoleResult(text="ok", status="finished")

    run_swe_turn_sync(
        task_id,
        provider="cursor",
        model_id="composer-2.5",
        prompt="implement feature",
        root=root,
        run_role_fn=capture_prompt,
    )

    assert len(captured) == 1
    prompt = captured[0]
    assert "Role skill paths:" in prompt
    assert "skills/roles/frugal_engineering/SKILL.md" in prompt
    assert "skills/roles/software_developer/SKILL.md" in prompt
    assert "--- skills/roles/frugal_engineering/SKILL.md ---" in prompt
    assert "FIXTURE_FRUGAL_PHILOSOPHY" in prompt
    assert "FIXTURE_SW_DEV_SIMPLICITY" in prompt
    assert "implement feature" in prompt
