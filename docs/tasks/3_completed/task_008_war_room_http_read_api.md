---
id: task_008
title: Localhost HTTP server and read API
tier: task
status: completed
parent: feat_003
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: null
created: '2026-10-09'
updated: '2026-10-10'
---

# Localhost HTTP server and read API

## Parent Feature

[feat_003](../../features/3_completed/feat_003_local_war_room.md) — Local War Room UI.

## Depends on

None (feat_001 / feat_002 are Feature dependencies, not Task edges).

## Acceptance criteria

- New package (e.g. `cascade/war_room/`) exposes a runnable localhost HTTP server using **Python 3.12 stdlib only** for HTTP (e.g. `http.server` or equivalent); **no Node, no TS build, no new pip dependency** beyond what the repo already uses (PyYAML is fine if already required by board).
- Server binds **`127.0.0.1` only**. Attempting to configure or default to `0.0.0.0` (or any non-loopback host) is rejected at startup or config parse with a clear error; tests assert bind address is loopback.
- Serves a minimal static shell (HTML/CSS/JS allowed as static files under the package or `cascade/war_room/static/`) at `GET /` so a browser can load the War Room chrome scaffold (content may be empty until task_011).
- **`GET /api/board`** returns JSON encoding a `BoardView`: `{ "epics": { column: [WorkMeta-like dicts] }, "features": { ... }, "tasks": { ... } }` built from `cascade.board.list_board(root=...)` (columns keyed by folder names `1_backlog`, `2_active`, `3_completed` or the project's existing column convention).
- **`GET /api/doc/{id}`** returns JSON for the work document from `cascade.board.read_doc(id, root=...)` (meta + body or a stable serializable shape documented in module docstring); `404` + JSON error when id is missing.
- Wrong methods/paths return appropriate HTTP status (404 for unknown routes, 405 where applicable).
- Tests in `tests/war_room/test_http_read.py` use a free port on `127.0.0.1`, start the server in a thread or subprocess, and assert board/doc JSON shape and loopback bind.

## Files likely touched

- `cascade/war_room/__init__.py`
- `cascade/war_room/server.py` (or equivalent)
- `cascade/war_room/static/index.html` (minimal shell)
- `tests/war_room/test_http_read.py`

## Implementation notes

Reuse `list_board` and `read_doc` from `cascade.board`; do not duplicate board indexing logic. Serialize `WorkMeta` / `WorkDoc` with JSON-friendly primitives (iso dates, string paths). Keep handlers thin so task_009 can add POST routes on the same server class. Document how to run the server (module `__main__` or a small CLI entry) in implementation comments only if needed.

## Skills

_(none)_

## Test plan

`pytest tests/war_room/test_http_read.py`

## Out of scope

- POST dispatch routes (task_009)
- Chat, toasts, attach/detach (task_010)
- Full War Room layout and human controls (task_011)
- Calling `activate_epic`, `dispatch_feature`, or `dispatch_task`

## Decision log

- `dec_013a` · 2026-10-09 · Feature Architect · **Read API scope**
  First slice is loopback HTTP + board/doc GET only; defers all mutating routes to task_009.
  Rationale: pytest can lock bind address and board integration before dispatch wiring.
  Honors: feat_003 localhost and BoardView contract.
