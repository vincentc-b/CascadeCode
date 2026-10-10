---
id: task_010
title: Transcript sidecar, chat, toasts, attach stubs
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

# Transcript sidecar, chat, toasts, attach stubs

## Parent Feature

[feat_003](../../features/2_active/feat_003_local_war_room.md) — Local War Room UI.

## Depends on

- [task_008](../../tasks/3_completed/task_008_war_room_http_read_api.md) (localhost server)

## Acceptance criteria

- **Transcript storage**: one append-only sidecar per persisting graph id (Epic / Feature queue ids such as `epic_001`, `feat_003`), **not** merged across graphs. Suggested path: `docs/_war_room/chat/{graph_id}.jsonl` (or equivalent under repo root); each line is a JSON object `Message` with at least `{ "id", "graph_id", "author": "human", "body", "ts" }`. Task-tier graphs do not get chat sidecars from this task (UI will omit Task rooms in task_011).
- **`GET /api/chat/{graph_id}`** returns JSON array of messages read from that graph's sidecar (empty list if file missing).
- **`POST /api/chat/{graph_id}`** with `{ "body": "<text>" }`:
  - If the server-side attachment state (in-memory or small session file) does **not** include `graph_id`, return **`403`** with JSON error (human messages only enter attached graph).
  - Else append the message, return **`202 Accepted`** with the stored message JSON; **no agent reply** and no LLM call.
- **`GET /api/toasts?after=<byte_offset>`** reads `read_events("war_room", after_offset, root=...)` and maps events to feat_003 **`Toast`** objects: `{ "kind", "body", "link" }` where `kind` is one of `amendment | comment | blocked | task_failed | task_merged | illegal_dispatch` (map `Toast` / illegal_move payloads from feat_007 per existing event shapes; unknown types may be skipped or mapped to `illegal_dispatch`). Response includes `{ "toasts": [...], "offset": <new_offset> }`.
- **`POST /api/attach`** with `{ "graph_id": "<id>" }` updates attachment state and returns **`200`** with a **briefing pack stub** JSON (e.g. `{ "graph_id", "doc_excerpt": "stub until feat_005", "messages": [] }`); does not require feat_005 graphs.
- **`POST /api/detach`** with `{ "graph_id": "<id>" }` clears that attachment; **`200`** with `{ "ok": true }`.
- Default attachment when none set: **`null`** or active epic id only if an epic is in `2_active` (document chosen behavior in module docstring; tests cover explicit attach before POST chat).
- Tests in `tests/war_room/test_sidecar_toasts.py` cover chat 202 store-without-reply, 403 when not attached, toast offset pagination, attach/detach stub responses.

## Files likely touched

- `cascade/war_room/chat_store.py` (or equivalent)
- `cascade/war_room/attachment.py`
- `cascade/war_room/toasts.py`
- `cascade/war_room/server.py`
- `tests/war_room/test_sidecar_toasts.py`

## Implementation notes

Import `read_events` and `append_event` from `cascade.watchdog` only where needed (attach may optionally emit `HumanAttached` / `HumanDetached` stubs via `append_event` to the graph dest — optional for MVP if documented as no-op until feat_005). Keep sidecar format stable for feat_004 graph subscription later. Do not read Task queue files as chat transcripts.

## Skills

_(none)_

## Test plan

`pytest tests/war_room/test_sidecar_toasts.py`

## Out of scope

- Server-rendered HTML panes (task_011)
- POST dispatch routes (task_009)
- Comment sidecar `docs/_comments/` (feat_005)
- Agent inference or graph checkpointer integration (feat_004/005)

## Decision log

- `dec_013c` · 2026-10-09 · Feature Architect · **Chat no-op store**
  POST chat returns 202 and persists only; no agent loop until feat_004/005.
  Rationale: enables dispatch testing without LLM.
  Honors: feat_003 API contracts; DESIGN.md §10.2 briefing deferred.
