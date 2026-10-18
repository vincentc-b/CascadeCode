---
id: task_007
title: Watchdog poll, illegal-move revert, and toast
tier: task
status: completed
parent: feat_002
children: []
depends_on:
  - task_006
owners: [swe]
skills: []
parent_rev: null
created: 2026-10-09
updated: 2026-10-09
---

# Watchdog poll, illegal-move revert, and toast

## Parent Feature

[feat_002](../../features/3_completed/feat_002_watchdog_queue_dispatch.md) — Watchdog, event queue, and dispatch law.

Honor epic_001: filesystem is truth; unauthorized appearance in `2_active` must not leave rogue work booted. Watchdog is not an LLM (DESIGN.md §9).

## Depends on

- [task_006](../../tasks/3_completed/task_006_dispatch_law.md) (authorized dispatch emits matching queue events)

## Acceptance criteria

- `cascade/watchdog/__init__.py` exports `run_watchdog` and `watchdog_tick`.
- `watchdog_tick(root)` performs **one** scan pass over `docs/{epics,features,tasks}/2_active/*.md` so tests need not run forever.
- `run_watchdog(root, poll_interval=..., stop_when=...)` loops `watchdog_tick` with a short poll (default ~0.5s) until `stop_when()` is true; without a stop condition it runs indefinitely.
- Watchdog state is **process memory** only (e.g. last-seen appearance keys to suppress duplicate toasts); not a second board database. May use git `introduced_at` to correlate file introduction with queue events.
- For each work doc in `2_active`, authorization requires a matching event on **that work id’s queue** (`read_events(work_id, ...)`):
  - Epic: `EpicActivated` with `epic_id == id`.
  - Feature: `FeatureReadyToPlan` with `id` or `feature_id == id`.
  - Task: `TaskDispatched` with `id` or `task_id == id`.
  - `TaskFailed` does **not** authorize presence in `2_active`; do not auto-dispatch on failure.
  - Events on `war_room` or other dests do not authorize a task/feature/epic file.
- If unauthorized (rogue `move_doc`, planning team `mv`, forged queue entry, stale event before file re-introduction):
  - Revert the doc to `1_backlog` via `move_doc(id, backlog)` when possible, or raw rename for unparseable files.
  - Append `Toast` to `war_room` with illegal-move payload (`kind`, `id`, `message`, `reason`).
  - Duplicate toasts for the same stuck appearance may be suppressed within a tick cycle; authorized dispatches must survive subsequent ticks.
- Legal dispatches from task_006 leave files in `2_active` with `status=active` (or `blocked` after human edit — blocked tasks with prior valid dispatch stay).
- Tests in `tests/watchdog/test_watchdog.py` cover rogue moves, TaskFailed non-authorization, run_watchdog stop hook, war_room forged events, stale authorization, and non-UTF8 garbage files.

## Files likely touched

- `cascade/watchdog/loop.py`
- `cascade/watchdog/lock.py` (re-export shared lock if needed)
- `cascade/watchdog/__init__.py`
- `tests/watchdog/test_watchdog.py`

## Implementation notes

The watchdog enforces dispatch law on disk; it does not start LangGraph itself beyond optional boot hooks already fired at dispatch time. A single bad file must not kill the tick loop. Use `parse_doc` / `move_doc` from `cascade.board`. Coordinate with `process_lock` used by queue and board commits.

## Skills

_(none)_

## Test plan

`pytest tests/watchdog/test_watchdog.py`

## Out of scope

- Boss sequencing and automatic `dispatch_task` retries (feat_008)
- War Room / UI consumption of toasts (feat_003)
- LangGraph internals, Task failure teardown (feat_007)
- Counting `task_parallelism` at dispatch time (task_006)
