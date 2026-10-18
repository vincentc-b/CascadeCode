---
id: task_032
title: Skill playbooks at task boot
tier: task
status: completed
parent: feat_007
children: []
depends_on:
  - task_030
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Skill playbooks at task boot

## Parent Feature

[feat_007](../../features/3_completed/feat_007_task_execution.md) — Task execution and local branches.

## Depends on

- task_030 — task graph state and boot entrypoint

## Acceptance criteria

- `load_skills_context(root: Path, skills: list[str]) -> list[dict]` in `skills_context.py`:
  - For each path in the Task’s effective skills list (repo-relative strings), read the file as UTF-8 playbook text.
  - Empty list returns `[]` (valid general SWE).
  - Reuse `cascade.watchdog.skills.effective_skill_paths(root, [Path(p) for p in skills])` for validation; missing, absolute, `..`, or out-of-repo paths raise or propagate `SkillPathError` (fail closed).
  - **Do not** classify or infer a stack enum.
- `apply_skill_playbooks(task_id: str, playbooks: list[dict], *, root: Path) -> None`: write `{path, text}` entries into graph state key `skill_playbooks` via `ensure_task_graph` + `update_state` (field defined in task_030 `TaskGraphState`).
- `tests/task/test_skills_context.py` covers empty list, single in-repo `SKILL.md`, multiple paths, and fail-closed on illegal paths.

## Files likely touched

- `cascade/task/skills_context.py`
- `tests/task/test_skills_context.py`

## Implementation notes

Dispatch already validated skills at `dispatch_task`; boot still re-validates via `effective_skill_paths`. Skill content is **context only** for the SWE node; it must not widen tool permissions (sandbox is task_033). Read files from board repo `root`, not the worktree, unless paths only exist in worktree (skills are in-repo at dispatch time).

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/task/test_skills_context.py -q`

## Out of scope

- Worktree (`task_031`), guard/io tools (`task_033`), wiring order (`task_037`)
- Dispatch-time skill override (feat_002 `dispatch_task` — already shipped)
