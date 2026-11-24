---
id: task_018_002_005
title: 'HTTP drain conformance: drain.py flag and drain-start snapshot join'
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 88ae16016c65783ce4b9891ccd33faadf4c55ec3
created: '2026-10-23'
updated: '2026-10-23'
---
# HTTP drain conformance: drain.py flag and drain-start snapshot join

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Follow-up to task_018_002_002, which merged (55a51af / 065d1e0) without the feature-spec review checklist items 1 and 3. Contracts: feature spec "Data structures" (Drain flag) and "API contracts" (Server); feature dec_012, dec_014.

## Acceptance criteria

- **Drain flag in `cascade/workspace/drain.py` (new):** module-level `_draining = threading.Event()` with `begin_drain()` (idempotent), `is_draining()`, `draining_event()`, `reset_drain_for_tests()`. No imports from `worker.py`, `server.py` or `kickoff.py` (no cycles); safe to call outside a worker.
- **Remove the raising accessor:** delete `worker_draining_event()` and the `_worker_draining` global from `cascade/workspace/worker.py`. In `run_worker`, replace the local `draining` event and its `.set()` calls with `begin_drain()`, and pass `draining=draining_event()` to `serve(...)`. Leave the `finally` block's order otherwise as is; task_018_002_003 replaces it with `drain_and_shutdown`.
- **Snapshot join in `cascade/war_room/server.py`:** add `WarRoomHTTPServer.snapshot_handler_threads() -> list[threading.Thread]` (alive tracked threads under `_handler_threads_lock`). Change `join_handler_threads(threads, *, timeout=HTTP_HANDLER_JOIN_TIMEOUT_S) -> list[str]` to join only the given threads, log each still-alive one to stderr, and return their names. Delete the `join_http_handlers` wrapper and update its caller in `run_worker` to `server.join_handler_threads(server.snapshot_handler_threads())`.
- No change to the 503 updating response, `Connection: close`, tracked non-daemon threads or the constants; they already conform.

## Files likely touched

- `cascade/workspace/drain.py` (new)
- `cascade/workspace/worker.py`
- `cascade/war_room/server.py`

## Test plan

No new unit tests; integration test (a) in task_018_002_004 covers this. Keep the existing server and worker tests green, adjusting only call sites of the removed `join_http_handlers` / `worker_draining_event`.

## Out of scope

`drain_and_shutdown`, the shutdown order (no `server.shutdown()` before the join), the final short join after `shutdown()` and the `os._exit` path; these are task_018_002_003's (dec_013, dec_014). Turn registry, kickoff gate, config.

## Implementation notes

Keep the diff small and land quickly: task_018_002_003 (active) imports `cascade.workspace.drain` for its kickoff admission gate. If 003 has already added `drain.py` with the same API when you start, keep it and do only the remaining items.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
