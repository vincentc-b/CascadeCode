"""Role-default skill playbooks and effective path resolution (feat_013 / task_060)."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from cascade.agent.types import RoleId
from cascade.task.skills_context import load_skills_context
from cascade.watchdog.skills import effective_skill_paths

_FRUGAL = "skills/roles/frugal_engineering/SKILL.md"
_PRODUCT = "skills/roles/product_manager/SKILL.md"
_ENG_MGR = "skills/roles/engineering_manager/SKILL.md"
_SW_DEV = "skills/roles/software_developer/SKILL.md"
_CODE_REV = "skills/roles/code_reviewer/SKILL.md"

RoleSkillDefaults: Final[dict[RoleId, list[str]]] = {
    "epic_manager": [_FRUGAL, _PRODUCT],
    "epic_architect": [_FRUGAL],
    "feature_lead": [_FRUGAL, _PRODUCT],
    "feature_architect": [_FRUGAL],
    "boss": [_FRUGAL, _ENG_MGR],
    "swe": [_FRUGAL, _SW_DEV, _CODE_REV],
}


def default_role_skill_paths(role: RoleId) -> list[str]:
    """Return a copy of the default skill path list for ``role``."""

    return list(RoleSkillDefaults[role])


def resolve_effective_skills(
    role: RoleId,
    task_skills: list[str] | None = None,
    *,
    root: Path,
) -> list[str]:
    """Merge role defaults with task skills (``swe`` only), dedupe, and validate."""

    merged: list[str] = list(RoleSkillDefaults[role])
    if role == "swe":
        merged.extend(task_skills or [])
    seen: set[str] = set()
    deduped: list[str] = []
    for path in merged:
        if path in seen:
            continue
        seen.add(path)
        deduped.append(path)
    repo = Path(root).resolve()
    return effective_skill_paths(repo, [Path(p) for p in deduped])


def load_role_skills_context(
    root: Path,
    role: RoleId,
    task_skills: list[str] | None = None,
) -> list[dict]:
    """Load validated playbook text for the effective skill paths of ``role``."""

    paths = resolve_effective_skills(role, task_skills, root=root)
    return load_skills_context(root, paths)
