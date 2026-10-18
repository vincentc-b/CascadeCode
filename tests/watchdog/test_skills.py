"""Skill path validation and ## Skills rewrite (dispatch-time helpers)."""

from pathlib import Path

import pytest

from cascade.watchdog.skills import SkillPathError, effective_skill_paths, rewrite_skills_section


def test_effective_skill_paths_accepts_relative_in_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    skill = root / "skills" / "demo" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("# demo\n", encoding="utf-8")

    assert effective_skill_paths(root, [Path("skills/demo/SKILL.md")]) == [
        "skills/demo/SKILL.md"
    ]


def test_effective_skill_paths_rejects_absolute(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "SKILL.md"
    outside.write_text("# x\n", encoding="utf-8")

    with pytest.raises(SkillPathError):
        effective_skill_paths(root, [outside])


def test_effective_skill_paths_rejects_parent_escape(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(SkillPathError):
        effective_skill_paths(root, [Path("../secret.md")])


def test_effective_skill_paths_rejects_missing_file(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()

    with pytest.raises(SkillPathError):
        effective_skill_paths(root, [Path("skills/missing/SKILL.md")])


def test_effective_skill_paths_rejects_symlink_outside_repo(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# outside\n", encoding="utf-8")
    link = root / "skills" / "link.md"
    link.parent.mkdir(parents=True)
    link.symlink_to(outside)

    with pytest.raises(SkillPathError):
        effective_skill_paths(root, [Path("skills/link.md")])


def test_rewrite_skills_section_replaces_bullets() -> None:
    body = "## Goal\n\nDo work.\n\n## Skills\n\n- old/path.md\n\n## Notes\n\nDone.\n"
    updated = rewrite_skills_section(body, ["skills/new/SKILL.md"])
    assert "- skills/new/SKILL.md" in updated
    assert "old/path.md" not in updated
    assert "## Goal" in updated
    assert "## Notes" in updated


def test_rewrite_skills_section_none_placeholder() -> None:
    body = "## Skills\n\n- x\n"
    updated = rewrite_skills_section(body, [])
    assert "_(none)_" in updated
