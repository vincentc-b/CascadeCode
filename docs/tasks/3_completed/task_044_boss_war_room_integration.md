---
id: task_044
title: Boss and War Room integration
tier: task
status: completed
parent: feat_008
children: []
depends_on:
  - task_038
  - task_039
  - task_040
  - task_041
  - task_042
  - task_043
owners: [swe]
skills: []
parent_rev: 6e82b701d276a80d34206a904cbe0d0a4dec6246
created: 2026-10-10
updated: 2026-10-10
---

# Boss and War Room integration

## Parent Feature

[feat_008](../../features/3_completed/feat_008_boss_and_rollup.md) — Boss agent and completion rollup.

## Depends on

- task_038 — BossView for read API
- task_039 — boss queue consumer install + drain event type
- task_040 — `merge_task_branch` implementation
- task_041 — rollup hooks
- task_042 — epic confirm + prompt
- task_043 — orphan list + toast payloads

## Acceptance criteria

- **`cascade/war_room/server.py`** (only task allowed to edit it among feat_008 tasks):
  - Replace `POST /api/merge_task_branch` stub with call to `merge_task_branch`; success returns **200** JSON `{ ok: true, merge_sha, branch, task_id }`; failures return appropriate 4xx with reason (no 202 stub).
  - Add **`POST /api/confirm_epic_complete`** `{ id: epic_id }` → `confirm_epic_complete(id, "human")`.
  - Optional **`POST /api/boss_drain`** `{ feature_id }` → append `BossDrainRequested` to boss queue (202), mirroring ask-boss pattern.
  - Read API: **`GET /api/boss_view`** (or extend `/api/board`) returning JSON serialization of `BossView`; **`GET /api/orphans`** returning `detect_orphans` list.
- **`cascade/watchdog/loop.py`**: on each tick (or documented hook), call boss queue consumer from task_039 with persisted offset; after processing, optionally run orphan detection and enqueue toasts (policy: at most once per tick if orphans non-empty).
- **Rollup chain**: after successful merge handler, call `on_task_merged(task_id)`; wire `on_feature_completed` from task_042 when `FeatureCompleted` is processed or directly from rollup success path in handler.
- **`cascade/war_room/toasts.py`**: map new toast kinds (`epic_ready_to_close`, `orphan`, failed-task retry proposal) without breaking existing kinds.
- **`cascade/war_room/views.py`** and **`cascade/war_room/static/war_room.js`**:
  - Merge button shows real merge result / errors.
  - Failed tasks (`blocked` in `2_active`): show **propose retry** UI that enqueues `BossDispatchRequested` or ask-boss only — **must not** call `dispatch_task` directly from the browser.
  - Epic-close confirm button posts `confirm_epic_complete`.
  - Orphan toasts link to affected ids.
  - BossView data available where board UI needs dispatchable/failed/slots (read from new GET endpoint).
- **`tests/war_room/test_dispatch_routes.py`**: replace `test_merge_task_branch_stub_202` expectations with the real merge contract (use temp repo fixture with branch or mock merge module if needed); keep ask-boss tests passing.
- Install **`install_boss_consumer(root)`** next to existing `install_*_boot_hook` / `install_task_wiring` in server startup and watchdog startup (mirror task_037 pattern).

## Files likely touched

- `cascade/war_room/server.py`
- `cascade/watchdog/loop.py`
- `cascade/war_room/toasts.py`
- `cascade/war_room/views.py`
- `cascade/war_room/static/war_room.js`
- `tests/war_room/test_dispatch_routes.py`
- (optional) `tests/boss/test_integration_smoke.py` if a single end-to-end smoke helps; primary contract tests remain war_room + unit tests from sibling tasks

## Implementation notes

This is the **only** feat_008 task that touches shared integration surfaces. Do not reimplement merge/rollup/boss logic inline—import from `cascade/boss/*`. Persist boss queue read offset in memory for the process (file-backed offset is optional stretch). Register consumer idempotently like other install_* helpers.

## Skills

_(none)_

## Test plan

`python3 -m pytest tests/war_room/test_dispatch_routes.py tests/boss/ -q`

## Out of scope

- Boss LLM persona or planning
- Auto-merge, auto dispatch on board poll, activate_epic for Boss
- Boss `write_doc` / architecture bodies
- Moving task markdown files out of `docs/tasks/1_backlog/`
