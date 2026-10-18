"""Role skill defaults, resolver, and playbook loading (task_060)."""

from __future__ import annotations

from pathlib import Path

import pytest

from cascade.agent.types import RoleId
from cascade.watchdog.role_skills import (
    RoleSkillDefaults,
    default_role_skill_paths,
    load_role_skills_context,
    resolve_effective_skills,
)
from cascade.watchdog.skills import SkillPathError

_ALL_ROLES: tuple[RoleId, ...] = (
    "epic_manager",
    "epic_architect",
    "feature_lead",
    "feature_architect",
    "swe",
    "boss",
)

_LOCKED_DEFAULTS: dict[RoleId, list[str]] = {
    "epic_manager": [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/product_manager/SKILL.md",
    ],
    "epic_architect": ["skills/roles/frugal_engineering/SKILL.md"],
    "feature_lead": [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/product_manager/SKILL.md",
    ],
    "feature_architect": ["skills/roles/frugal_engineering/SKILL.md"],
    "boss": [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/engineering_manager/SKILL.md",
    ],
    "swe": [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
    ],
}


def _write_role_skill_fixtures(root: Path) -> None:
    """Create minimal SKILL.md files for all default role skill paths."""

    for paths in RoleSkillDefaults.values():
        for rel in paths:
            skill = root / rel
            skill.parent.mkdir(parents=True, exist_ok=True)
            if not skill.is_file():
                skill.write_text(f"# {rel}\n", encoding="utf-8")


def test_role_skill_defaults_constant_matches_locked_lists() -> None:
    for role in _ALL_ROLES:
        assert RoleSkillDefaults[role] == _LOCKED_DEFAULTS[role]


def test_default_role_skill_paths_returns_copy_for_every_role() -> None:
    for role in _ALL_ROLES:
        paths = default_role_skill_paths(role)
        assert paths == _LOCKED_DEFAULTS[role]
        paths.append("skills/roles/should-not-mutate/SKILL.md")
        assert default_role_skill_paths(role) == _LOCKED_DEFAULTS[role]


def test_resolve_effective_skills_swe_unions_and_dedupes_defaults_first(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_role_skill_fixtures(root)
    extra = root / "skills" / "task" / "extra" / "SKILL.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("# extra\n", encoding="utf-8")

    duplicate = "skills/roles/frugal_engineering/SKILL.md"
    resolved = resolve_effective_skills(
        "swe",
        [
            duplicate,
            "skills/task/extra/SKILL.md",
            "skills/task/extra/SKILL.md",
        ],
        root=root,
    )

    assert resolved == [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
        "skills/task/extra/SKILL.md",
    ]
    assert resolved.count(duplicate) == 1


@pytest.mark.parametrize(
    "role",
    [
        "epic_manager",
        "epic_architect",
        "feature_lead",
        "feature_architect",
        "boss",
    ],
)
def test_resolve_effective_skills_planning_roles_ignore_task_skills(
    tmp_path: Path,
    role: RoleId,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_role_skill_fixtures(root)
    extra = root / "skills" / "task" / "ignored" / "SKILL.md"
    extra.parent.mkdir(parents=True)
    extra.write_text("# ignored\n", encoding="utf-8")

    resolved = resolve_effective_skills(
        role,
        ["skills/task/ignored/SKILL.md"],
        root=root,
    )

    assert resolved == _LOCKED_DEFAULTS[role]


def test_resolve_effective_skills_illegal_task_path_raises(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_role_skill_fixtures(root)

    with pytest.raises(SkillPathError):
        resolve_effective_skills(
            "swe",
            ["../outside/SKILL.md"],
            root=root,
        )


def test_resolve_effective_skills_missing_default_raises(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(SkillPathError):
        resolve_effective_skills("epic_architect", root=root)


def test_load_role_skills_context_returns_path_and_text(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_role_skill_fixtures(root)
    frugal = root / "skills/roles/frugal_engineering/SKILL.md"
    frugal.write_text("# Frugal\nBe frugal.\n", encoding="utf-8")

    playbooks = load_role_skills_context(root, "epic_architect")

    assert playbooks == [
        {
            "path": "skills/roles/frugal_engineering/SKILL.md",
            "text": "# Frugal\nBe frugal.\n",
        }
    ]


def test_load_role_skills_context_swe_includes_task_skills(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write_role_skill_fixtures(root)
    task_skill = root / "skills" / "custom" / "SKILL.md"
    task_skill.parent.mkdir(parents=True)
    task_skill.write_text("custom playbook\n", encoding="utf-8")

    playbooks = load_role_skills_context(
        root,
        "swe",
        task_skills=["skills/custom/SKILL.md"],
    )

    paths = [entry["path"] for entry in playbooks]
    assert paths == [
        "skills/roles/frugal_engineering/SKILL.md",
        "skills/roles/software_developer/SKILL.md",
        "skills/roles/code_reviewer/SKILL.md",
        "skills/custom/SKILL.md",
    ]
    assert playbooks[-1]["text"] == "custom playbook\n"
