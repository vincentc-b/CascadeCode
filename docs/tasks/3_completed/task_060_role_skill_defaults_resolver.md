---
id: task_060
title: Role skill defaults and resolver
tier: task
status: completed
parent: feat_013
children: []
depends_on:
  - task_059
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-13
updated: 2026-10-13
---

# Role skill defaults and resolver

## Parent Feature

[feat_013](../../features/3_completed/feat_013_role_skills_and_frugal_engineering.md) — Role skills and frugal engineering philosophy.

## Depends on

- task_059 — on-disk `skills/roles/**/SKILL.md` playbooks

## Acceptance criteria

- **New module** `cascade/watchdog/role_skills.py` (locked location; mirror `model_resolve.py` next to skill path validation):
  - `RoleSkillDefaults`: a **code constant** mapping each `RoleId` (`cascade/agent/types.py`) to an ordered list of repo-relative path strings:
    - `epic_manager`: `skills/roles/frugal_engineering/SKILL.md`, `skills/roles/product_manager/SKILL.md`
    - `epic_architect`: `skills/roles/frugal_engineering/SKILL.md`
    - `feature_lead`: `skills/roles/frugal_engineering/SKILL.md`, `skills/roles/product_manager/SKILL.md`
    - `feature_architect`: `skills/roles/frugal_engineering/SKILL.md`
    - `boss`: `skills/roles/frugal_engineering/SKILL.md`, `skills/roles/engineering_manager/SKILL.md`
    - `swe`: `skills/roles/frugal_engineering/SKILL.md`, `skills/roles/software_developer/SKILL.md`, `skills/roles/code_reviewer/SKILL.md`
  - `default_role_skill_paths(role: RoleId) -> list[str]` returns a copy of the default list for that role.
  - `resolve_effective_skills(role: RoleId, task_skills: list[str] | None = None) -> list[str]`:
    - Start with role defaults; for `role == "swe"` only, append `task_skills` (or `[]` when `None`).
    - **Deduplicate** preserving order: defaults first, then task-specific paths (first occurrence wins).
    - For all non-`swe` roles, **ignore** `task_skills` entirely (planning/boss never union Task frontmatter).
    - Validate the merged list via `cascade.watchdog.skills.effective_skill_paths(root, [Path(p) for p in merged])`; propagate `SkillPathError` (fail closed on missing, absolute, `..`, or out-of-repo paths).
  - `load_role_skills_context(root: Path, role: RoleId, task_skills: list[str] | None = None) -> list[dict]`:
    - Call `resolve_effective_skills`, then reuse `cascade.task.skills_context.load_skills_context(root, paths)` (or equivalent read loop) to return `[{path, text}, ...]`.
- **`cascade/watchdog/__init__.py`**: export the public resolver helpers if other packages import from the package root (match `model_resolve` export style).
- **Tests** `tests/watchdog/test_role_skills.py` (new):
  - `default_role_skill_paths` for every `RoleId` matches the locked lists above.
  - `resolve_effective_skills("swe", task_skills=[...])` unions and deduplicates (defaults before task paths; duplicate path appears once).
  - Planning roles (`epic_manager`, `feature_lead`, `boss`, architects) ignore non-empty `task_skills`.
  - Illegal path in defaults or task list raises `SkillPathError`.
  - `load_role_skills_context` returns text for in-repo fixtures (may use task_059 files once present, or minimal temp `SKILL.md` under test repo).

## Files likely touched

- `cascade/watchdog/role_skills.py` (new)
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_role_skills.py` (new)

## Implementation notes

v1 **does not** read role defaults from `cascade.toml`; the map is a code constant only. Reuse existing `effective_skill_paths` and `load_skills_context`; do not classify stacks or widen tool sandboxes. Skill files are context only.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/watchdog/test_role_skills.py -q`

## Out of scope

- Injecting playbooks into prompts (task_061, task_062)
- `cascade.toml` `[skills.roles]` overrides
- Dispatch-time changes (feat_002 skill validation at dispatch remains as-is until task_062 boot semantics land)
