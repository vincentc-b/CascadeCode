---
id: task_005
title: Parallelism config, skill paths, and boot/teardown hooks
tier: task
status: completed
parent: feat_002
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# Parallelism config, skill paths, and boot/teardown hooks

## Parent Feature

[feat_002](../../features/3_completed/feat_002_watchdog_queue_dispatch.md) — Watchdog, event queue, and dispatch law.

Honor DESIGN.md §9.1 (`task_parallelism`) and epic_001 constraint 10 (task skills, not a stack enum).

## Depends on

None (may run in parallel with task_004).

## Acceptance criteria

- `cascade/watchdog/__init__.py` exports `task_parallelism`, `ConfigError`, `register_boot_hook`, and `register_teardown_hook`.
- `task_parallelism(root: Path) -> int` reads `cascade.toml` at the repo root:
  - Missing file → **4**
  - Missing `task_parallelism` key → **4**
  - Non-integer, boolean, or integer `< 1` → raise `ConfigError` (do not fall open to unlimited work).
- `register_boot_hook(tier, fn)` and `register_teardown_hook(tier, fn)`:
  - `tier` is `epic`, `feature`, or `task`.
  - `fn(work_id: str) -> None` is stored and invoked by dispatch (boot only in this feature; teardown is register-only until feat_007/008).
  - Interfaces only — LangGraph implementations live in feat_004, feat_005, feat_007.
- Skill paths (`cascade/watchdog/skills.py` or equivalent):
  - Every path in an effective skills list must resolve to an existing file inside the repo root.
  - Relative paths only; reject absolute paths and `..` escapes.
  - No `stack` enum or language classifier.
  - Helpers may rewrite the Task body `## Skills` section when dispatch overrides skills (called from dispatch Task, not planning tools).
- Tests in `tests/watchdog/test_config.py` cover defaults, valid TOML, and `ConfigError` cases; config errors must not silently dispatch work.
- Additional tests as needed for hook registration (tier validation) and skill path rejection (absolute, missing file, escape).

## Files likely touched

- `cascade/watchdog/config.py`
- `cascade/watchdog/skills.py`
- `cascade/watchdog/hooks.py`
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_config.py`
- `tests/watchdog/test_skills.py` (if split from config/dispatch tests)

## Implementation notes

Planning agents must not use `task_parallelism` to self-start (DESIGN.md §9.1). `dispatch_task` will call skill validation in task_006; keep validation pure and reusable. `clear_hooks()` may exist for tests only — do not export unless tests need it.

## Skills

_(none)_

## Test plan

`pytest tests/watchdog/test_config.py` and any `tests/watchdog/test_skills.py`

## Out of scope

- `activate_epic`, `dispatch_feature`, `dispatch_task`
- Watchdog loop, queue schema (task_004), illegal-move toast emission
- Invoking teardown hooks on Task failure (feat_007)
