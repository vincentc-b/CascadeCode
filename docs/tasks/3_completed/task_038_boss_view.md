---
id: task_038
title: BossView read model
tier: task
status: completed
parent: feat_008
children: []
depends_on: []
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# BossView read model

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

_(none — wave A; uses existing board + dispatch helpers only)_

## Acceptance criteria

- New module `cascade/boss/view.py` defines a `BossView` dataclass (or typed structure) with fields matching the feature spec: `dispatchable_features`, `dispatchable_tasks`, `slots_free`, `failed_tasks` (each a list of work id strings except `slots_free: int`).
- Public entrypoint `compute_boss_view(*, root: Path | None = None) -> BossView` (name may vary but must not shadow `cascade.board.store.list_board`) performs **read-only** board inspection via `list_board`, `read_doc` as needed, and reuses the same dependency and cap rules as `cascade/watchdog/dispatch.py`:
  - **dispatchable_features**: tier `feature`, column `1_backlog`, status in `{backlog, ready_to_plan}`, every `depends_on` id in `3_completed`.
  - **dispatchable_tasks**: tier `task`, column `1_backlog`, status in `{backlog, ready_to_plan}`, deps met, and dispatch would **not** exceed cap (same `_active_task_count` semantics: only `status=active` tasks in `2_active` count; `blocked` excluded).
  - **slots_free**: `max(0, task_parallelism(root) - active_count)` with the same active-count rule as dispatch.
  - **failed_tasks**: tier `task`, `status=blocked`, file in `2_active`.
- No calls to `dispatch_feature`, `dispatch_task`, `move_doc`, `append_event`, or boot hooks.
- `tests/boss/test_view.py` covers: empty board; backlog task/feature with met/unmet deps; cap-full board excludes extra dispatchable tasks but still reports correct `slots_free`; blocked task appears in `failed_tasks` not in dispatchable lists; a `ready_to_plan` feature in backlog is dispatchable when deps met.

## Files likely touched

- `cascade/boss/__init__.py` (minimal package marker; optional re-export of `compute_boss_view`)
- `cascade/boss/view.py`
- `tests/boss/test_view.py`

## Implementation notes

Import `_deps_met` / `_active_task_count` only if they are or become shared helpers; prefer duplicating the small counting loops over importing private dispatch internals—if you import privates, document and test parity with `dispatch_task` cap refusal. Do **not** edit `cascade/war_room/server.py` (API exposure is task_044). Boss tool name in DESIGN is `list_board`; this task delivers the **view** function integration will wire later.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_view.py -q`

## Out of scope

- Boss LangGraph runtime, queue consumer, or `dispatch_*` calls
- HTTP routes or War Room UI
- Auto-merge, activate_epic, merge, mint, write_doc plan bodies
- Auto `dispatch_task` after `TaskFailed`
