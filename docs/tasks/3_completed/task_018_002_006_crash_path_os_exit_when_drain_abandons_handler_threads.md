---
id: task_018_002_006
title: Crash-path os._exit when drain abandons handler threads
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: b8f27d1dc062966a96a2263bb2c436b04f01eabf
created: '2026-10-23'
updated: '2026-10-23'
---
# Crash-path os._exit when drain abandons handler threads

## Parent Feature

[feat_018_002](../../features/2_active/feat_018_002.md)

## Depends on

None.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

## Goal

Close the crash-path hang left by task_018_002_003 (merged as `97dcdec`). In `cascade/workspace/worker.py::run_worker`, when the body (`resume_legally_active_graphs` / `run_watchdog`) raises, the `finally` runs `drain_and_shutdown(...)` but its `handlers_abandoned` result is discarded as the exception propagates; `main()` re-raises and interpreter shutdown waits on the abandoned non-daemon handler threads, so the worker can hang instead of exiting.

## Acceptance criteria

- On the crash path (body raised, not operator stop, not source change), if `drain_and_shutdown` returns True: print the exception traceback to stderr, flush stdout and stderr, and call `os._exit(1)`.
- On the crash path with no abandoned handlers, behaviour is unchanged (the exception propagates as today).
- Update and stop paths are unchanged (`main()` still does `os._exit(code)` / `SystemExit(code)` from the `(code, handlers_abandoned)` return).
- No change to `drain_and_shutdown`, `server.py`, `drain.py`, the launcher, or kickoff.

## Files likely touched

- `cascade/workspace/worker.py` only (the `finally` block in `run_worker`, or equivalent handling in `main()`).

## Test plan

No new test (feature rule: no unit-test matrix; the crash path with abandoned handlers is rare and not covered by integration tests a/b/c). Verify by reading the diff and by running the existing worker/drain tests and task_018_002_004's integration tests if already merged.

## Out of scope

Any other drain behaviour; task_018_002_004's tests. Do not touch the integration test files 004 is writing.

## Refs

Feature spec Risks (crash path), API contracts -> Worker shutdown (exit codes); dec_015, dec_017.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
