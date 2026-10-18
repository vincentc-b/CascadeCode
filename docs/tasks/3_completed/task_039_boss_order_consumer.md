---
id: task_039
title: Boss order consumer
tier: task
status: completed
parent: feat_008
children: []
depends_on:
  - task_038
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Boss order consumer

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

- task_038 — `compute_boss_view` / dispatchable sets for explicit drain expansion

## Acceptance criteria

- `cascade/boss/orders.py` parses human orders from the **boss** queue:
  - **`BossDispatchRequested`** (existing War Room shape): `{ kind: "feature"|"task", id: work_id, by: "human" }` → dispatch that single id via `dispatch_feature(id, "boss")` or `dispatch_task(id, "boss")`.
  - **`BossDrainRequested`** (new typed event, dest `boss`): `{ feature_id: str, by: "human" }` → for each id in `compute_boss_view().dispatchable_tasks` whose parent feature is `feature_id`, call `dispatch_task` with `by="boss"` **once per order processing pass**, respecting cap (stop when dispatch returns `cap` or list exhausted); never dispatch tasks outside that feature; never dispatch blocked/failed ids unless they appear in a separate explicit `BossDispatchRequested` for that task id.
- `cascade/boss/graph.py` exposes a long-lived consumer API, e.g. `process_boss_queue(*, root, offset) -> int` and/or `install_boss_consumer(root)` that records read offset and is safe to call from watchdog tick (no busy-loop thread required in this task).
- Consumer **must not** scan the board and dispatch every ready card on idle ticks; processing happens only when new queue lines arrive (offset advances).
- **Must not** call `activate_epic`, `merge_task_branch`, `move_doc` for rollup, mint, or `write_doc` on plan bodies.
- **Must not** call `dispatch_task` for a `blocked` task id unless that id is named in a fresh `BossDispatchRequested` (dispatch law already allows blocked restart; consumer must not infer retries from `failed_tasks` alone).
- `tests/boss/test_orders.py`: enqueue `BossDispatchRequested` → exactly one dispatch side effect; enqueue drain → dispatches only backlog tasks under that feature in dependency-safe order (mock or temp board); idle tick with no new events → zero dispatches; failed/blocked task not redispatched by drain alone.

## Files likely touched

- `cascade/boss/graph.py`
- `cascade/boss/orders.py`
- `tests/boss/test_orders.py`

## Implementation notes

Use `read_events("boss", offset, root=...)` from `cascade/watchdog/events.py` and `dispatch_feature` / `dispatch_task` from `cascade/watchdog/dispatch.py` only inside order handlers. Document `BossDrainRequested` payload in module docstring for task_044 UI wiring. Do **not** edit `cascade/war_room/server.py` in this task (ask-boss and drain POST routes are task_044). Optional: helper to enqueue `BossDrainRequested` in tests only.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/boss/test_orders.py -q`

## Out of scope

- War Room POST routes for drain (integration task)
- Boss LLM graph / prompts
- `server.py`, `loop.py`, toasts, views, static JS
- Auto-merge, activate_epic, rollup, orphan toasts
