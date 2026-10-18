---
id: task_062
title: SWE boot role skills wiring
tier: task
status: completed
parent: feat_013
children: []
depends_on:
  - task_060
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-13
updated: 2026-10-13
---

# SWE boot role skills wiring

## Parent Feature

[feat_013](../../features/3_completed/feat_013_role_skills_and_frugal_engineering.md) — Role skills and frugal engineering philosophy.

## Depends on

- task_060 — `load_role_skills_context`, `resolve_effective_skills`

## Acceptance criteria

- **Task boot wiring** (`cascade/task/wiring.py` and/or `cascade/task/boot.py` where `boot_task_wired` loads skills today):
  - Replace direct `load_skills_context(root, task.meta.skills)` with `load_role_skills_context(root, role="swe", task_skills=doc.meta.skills)` so **role defaults prepend** Task frontmatter paths (deduped union from task_060).
  - Continue to write `{path, text}` entries into graph state key `skill_playbooks` via existing `apply_skill_playbooks` (or equivalent).
  - On `SkillPathError` from resolution/load, fail closed at boot (same class as illegal skill paths today — e.g. `fail_closed_boot` where task runtime already does for bad skills).
- **SWE turn prompt** (`cascade/task/swe_turn.py` and/or `format_turn_prompt` if shared): surface loaded role-skill **paths** in the SWE prompt where feat_010 surfaces model source (path list visibility for operator/agent).
- **Semantics**: empty Task `skills: []` means general SWE **plus** default frugal/developer/reviewer playbooks — not “no playbook.”
- **Docs** (this task owns the DESIGN.md sentence; do not rewrite other sections):
  - Update `DESIGN.md` §4.1 (empty-skills sentence) to document the new empty-skills meaning.
  - Update feat_007-related wording in `docs/features/3_completed/feat_007_task_execution.md` if it still says empty list is “no playbook” / general SWE without defaults (minimal edit for accuracy only).
- **Tests**:
  - `tests/task/test_skills_context.py`: adjust expectations — empty task skills list still loads role defaults when called through `load_role_skills_context` (or document split: unit tests on resolver in task_060, integration here).
  - `tests/task/test_runtime.py`: task boot with `skills: []` seeds `skill_playbooks` with default role paths; task with extra in-repo skill path unions correctly; illegal task skill path fails boot closed.

## Files likely touched

- `cascade/task/wiring.py`
- `cascade/task/boot.py` (if boot path differs)
- `cascade/task/swe_turn.py`
- `cascade/agent/graph_turn.py` (if SWE path visibility shared)
- `DESIGN.md` (§4.1 empty-skills only)
- `docs/features/3_completed/feat_007_task_execution.md` (wording alignment)
- `tests/task/test_runtime.py`
- `tests/task/test_skills_context.py`

## Implementation notes

Dispatch-time validation (feat_002) may still validate Task-listed paths; boot re-validates the **effective** merged list. Task frontmatter `skills` remain **additive specialization** on top of SWE role defaults. Do not add roster nodes or change merge/dispatch law.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_runtime.py tests/task/test_skills_context.py -q`

## Out of scope

- Planning graph prompt wiring (task_061)
- Authoring playbook files (task_059)
- `cascade.toml` role skill overrides
- Changing comment, amendment, or Boss merge behavior
