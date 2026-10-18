"""Dispatch-time skill paths. Relative, inside the repo, and present on disk."""

from __future__ import annotations

from pathlib import Path


class SkillPathError(ValueError):
    """A skill path is absolute, escapes the repo, or does not exist."""


def effective_skill_paths(root: Path, skills: list[Path]) -> list[str]:
    """Return posix relative paths. Raise SkillPathError when any path is illegal."""

    root_resolved = root.resolve()
    normalized: list[str] = []
    for skill in skills:
        path = Path(skill)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise SkillPathError(str(skill))
        if not path.parts or any(part in {"", "."} for part in path.parts):
            raise SkillPathError(str(skill))
        resolved = (root_resolved / path).resolve()
        if not resolved.is_relative_to(root_resolved) or not resolved.is_file():
            raise SkillPathError(str(skill))
        normalized.append(path.as_posix())
    return normalized


def rewrite_skills_section(body: str, skills: list[str]) -> str:
    """Replace the body of the `## Skills` section. Other sections stay put."""

    lines = body.splitlines(keepends=True)
    start = None
    for index, line in enumerate(lines):
        if line.strip() == "## Skills":
            start = index
            break
    if start is None:
        return body
    end = len(lines)
    for index in range(start + 1, len(lines)):
        if lines[index].startswith("## "):
            end = index
            break
    heading = lines[start]
    if not heading.endswith("\n"):
        heading += "\n"
    if skills:
        bullets = "\n".join(f"- {skill}" for skill in skills)
    else:
        bullets = "_(none)_"
    block = f"{heading}\n{bullets}\n\n"
    return "".join(lines[:start]) + block + "".join(lines[end:])
