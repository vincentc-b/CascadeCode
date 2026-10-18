"""Skill playbook loading and graph state persistence at task boot."""

from __future__ import annotations

from pathlib import Path

import pytest

import cascade.task.graph as task_graph
from cascade.task import ensure_task_graph
from cascade.task.checkpoint import thread_config
from cascade.task.skills_context import apply_skill_playbooks, load_skills_context
from cascade.watchdog.role_skills import load_role_skills_context
from cascade.watchdog.skills import SkillPathError
from tests.support import make_repo, write_swe_default_role_skills


@pytest.fixture(autouse=True)
def _graph_isolation() -> None:
    task_graph._graph_cache.clear()
    yield
    task_graph._graph_cache.clear()


def test_load_skills_context_empty_list(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    assert load_skills_context(root, []) == []


def test_load_skills_context_single_skill_md(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    skill = root / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# Demo skill\nPlaybook body.\n", encoding="utf-8")

    playbooks = load_skills_context(root, ["skills/demo/SKILL.md"])

    assert playbooks == [
        {"path": "skills/demo/SKILL.md", "text": "# Demo skill\nPlaybook body.\n"}
    ]


def test_load_skills_context_multiple_paths(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    first = root / "skills" / "a" / "SKILL.md"
    second = root / "skills" / "b" / "SKILL.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("alpha\n", encoding="utf-8")
    second.write_text("beta\n", encoding="utf-8")

    playbooks = load_skills_context(
        root,
        ["skills/a/SKILL.md", "skills/b/SKILL.md"],
    )

    assert playbooks == [
        {"path": "skills/a/SKILL.md", "text": "alpha\n"},
        {"path": "skills/b/SKILL.md", "text": "beta\n"},
    ]


def test_load_skills_context_rejects_absolute_path(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    outside = tmp_path / "SKILL.md"
    outside.write_text("# x\n", encoding="utf-8")

    with pytest.raises(SkillPathError):
        load_skills_context(root, [str(outside)])


def test_load_skills_context_rejects_parent_escape(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    with pytest.raises(SkillPathError):
        load_skills_context(root, ["../secret.md"])


def test_load_skills_context_rejects_missing_file(tmp_path: Path) -> None:
    root = make_repo(tmp_path)

    with pytest.raises(SkillPathError):
        load_skills_context(root, ["skills/missing/SKILL.md"])


def test_apply_skill_playbooks_writes_graph_state(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    task_id = "task_001"
    playbooks = [{"path": "skills/demo/SKILL.md", "text": "playbook\n"}]

    ensure_task_graph(task_id, root=root)
    apply_skill_playbooks(task_id, playbooks, root=root)

    graph = ensure_task_graph(task_id, root=root)
    values = graph.get_state(thread_config(task_id)).values
    assert values is not None
    assert values["skill_playbooks"] == playbooks


def test_load_role_skills_context_empty_task_skills_loads_swe_defaults(
    tmp_path: Path,
) -> None:
    root = make_repo(tmp_path)
    write_swe_default_role_skills(root)

    playbooks = load_role_skills_context(root, "swe", task_skills=[])

    paths = [entry["path"] for entry in playbooks]
    assert paths == [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
    ]


def test_apply_skill_playbooks_on_empty_checkpoint(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    task_id = "task_002"
    playbooks = [{"path": "x/SKILL.md", "text": "t\n"}]

    apply_skill_playbooks(task_id, playbooks, root=root)

    graph = ensure_task_graph(task_id, root=root)
    values = graph.get_state(thread_config(task_id)).values
    assert values is not None
    assert values["skill_playbooks"] == playbooks
    assert values["task_id"] == task_id
