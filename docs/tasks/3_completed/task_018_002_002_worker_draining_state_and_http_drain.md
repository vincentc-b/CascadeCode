---
id: task_018_002_002
title: Worker draining state and HTTP drain
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 6785a23f6e5ce8e08add374543e7bc40a4c90fb6
created: '2026-10-23'
updated: '2026-10-23'
---
# Worker draining state and HTTP drain

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Introduce the worker's **draining** state and drain the War Room HTTP server (epic dec_006). This task owns the shared drain flag/event in `cascade/workspace/worker.py` (`run_worker` stop path) that the turn-drain task also consumes.

Acceptance:
- A single draining event is set when the worker decides to exit (update or operator stop via the existing SIGTERM/SIGINT/`stop_event` path).
- While draining, POST/PUT/PATCH/DELETE return `503` with `Retry-After` and body `{"error":"updating"}`; GETs keep working until the join finishes.
- Every response while draining sets `Connection: close`.
- `cascade/war_room/server.py`: handler threads become tracked, non-daemon threads (still bounded by `MAX_CONCURRENT_REQUESTS`, replacing `daemon_threads = True`). On drain they are joined with a bound of the longest route deadline plus margin (~65s); handlers still running are logged and abandoned. An accepted write within its route deadline is never cut off mid-handler.
- The HTTP join is exposed so the worker can run it concurrently with turn drain.

Testing: covered by integration test (a) in the integration-tests task; no new unit tests unless an existing server test breaks.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
