---
id: task_009
title: Human dispatch HTTP routes
tier: task
status: completed
parent: feat_003
children: []
depends_on:
- task_008
owners:
- swe
skills: []
parent_rev: null
created: '2026-10-09'
updated: '2026-10-10'
---

# Human dispatch HTTP routes

## Parent Feature

[feat_003](../../features/2_active/feat_003_local_war_room.md) — Local War Room UI.

## Depends on

- [task_008](../../tasks/2_active/task_008_war_room_http_read_api.md) (localhost server and read API)

## Acceptance criteria

- **`POST /api/activate_epic`** with JSON body `{ "id": "<epic_id>" }` calls `cascade.watchdog.activate_epic(id, by="human", root=...)` and returns JSON-serialized `DispatchResult` (`ok`, `reason`, `event` or null). Never passes `by="boss"` from this route.
- **`POST /api/dispatch_feature`** with `{ "id": "<feat_id>" }` calls `dispatch_feature(id, by="human", root=...)`.
- **`POST /api/dispatch_task`** with `{ "id": "<task_id>", "skills": [<path>, ...] | null }` calls `dispatch_task(id, by="human", skills=..., root=...)`; omit or null `skills` leaves Task doc skills unchanged.
- All three routes: invalid JSON → `400`; missing `id` → `400`; success/failure reflected in response body with HTTP `200` (body carries `ok: false` and `reason` on dispatch refusal, matching feat_002 semantics).
- **`POST /api/merge_task_branch`** accepts `{ "id": "<task_id>" }` and returns **`202 Accepted`** with a JSON stub body (e.g. `{ "ok": false, "reason": "not_implemented", "message": "merge wired in feat_007/008" }`); must **not** perform a real git merge.
- Optional **`POST /api/ask_boss_dispatch`** (or equivalent name documented in server module) accepts `{ "kind": "feature"|"task", "id": "<work_id>" }`, appends a **`war_room`** or **`boss`** queue event via `append_event` (typed payload e.g. `BossDispatchRequested` with `{ kind, id, by: "human" }`), returns **`202`**, and **does not** call `dispatch_feature` / `dispatch_task` itself.
- No HTTP route accepts a client-supplied `by` principal; Boss dispatch from the UI is event-only until feat_008.
- Tests in `tests/war_room/test_dispatch_routes.py` cover human-only principal, successful dispatch against fixture board, refusal cases (`unauthorized` not applicable for human on these three, but `unmet_deps` / `bad_state` where easy), merge stub 202, and ask-boss append without file move.

## Files likely touched

- `cascade/war_room/server.py` (POST handlers)
- `cascade/war_room/__init__.py`
- `tests/war_room/test_dispatch_routes.py`

## Implementation notes

Import `activate_epic`, `dispatch_feature`, `dispatch_task`, `append_event`, and `DispatchResult` from `cascade.watchdog`. Serialize `Event` datetimes as ISO-8601 in JSON responses. Share the server instance from task_008. For ask-boss, pick a single dest (`war_room` or `boss`) and document the event `type` string in code so task_010 toast mapping can ignore it until needed.

## Skills

_(none)_

## Test plan

`pytest tests/war_room/test_dispatch_routes.py`

## Out of scope

- War Room HTML controls (task_011)
- Chat, toasts, attach/detach (task_010)
- Boss brain consuming ask-boss events (feat_008)
- Real `merge_task_branch` git operations (feat_007/008)

## Decision log

- `dec_013b` · 2026-10-09 · Feature Architect · **Human-only dispatch from UI**
  POST routes hard-code `by="human"`; Boss dispatch is enqueue-only.
  Rationale: feat_002 dispatch law; UI must not impersonate Boss.
  Honors: epic_001 constraints; feat_003 API contracts.
