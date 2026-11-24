---
id: task_018_002_007
title: Widen raised-body os._exit guard to abnormal_exit and handlers_abandoned
tier: task
status: completed
parent: feat_018_002
children: []
depends_on: []
owners:
- swe
skills: []
parent_rev: 88011a01f182f8d299a2f718511d265468243c38
created: '2026-10-23'
updated: '2026-10-23'
---
# Widen raised-body os._exit guard to abnormal_exit and handlers_abandoned

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

On `feat/feat_018_002` (after 006's merge `ba4e852`), `run_worker` in `cascade/workspace/worker.py` only calls `os._exit(1)` after a raised body when no operator stop and no source change was signalled:

```python
if (
    abnormal_exit
    and not operator_stop.is_set()
    and not source_changed
    and handlers_abandoned
):
```

If the watchdog body raises after a SIGTERM or source change has set its flag, the worker re-raises and interpreter exit waits on abandoned non-daemon handler threads. On update the launcher waits with no timeout (epic dec_010), so the workspace stays down.

## Change

Delete the two conditions `and not operator_stop.is_set()` and `and not source_changed` from that `if`, so the guard is exactly `abnormal_exit and handlers_abandoned`. Keep the traceback print, stdio flush and `os._exit(1)` as they are.

## Acceptance

- The guard after `drain_and_shutdown(...)` in `run_worker`'s `finally` is `abnormal_exit and handlers_abandoned`.
- Nothing else changes: shutdown_reason selection, normal-return codes and `main()` stay as they are.

## Files likely touched

- `cascade/workspace/worker.py` only.

## Test plan

No new test (feature dec_017, dec_019). Run the existing `tests/workspace` suite to confirm nothing regresses.

## Out of scope

Any other worker, server, launcher or provider change. Task 004's files.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
