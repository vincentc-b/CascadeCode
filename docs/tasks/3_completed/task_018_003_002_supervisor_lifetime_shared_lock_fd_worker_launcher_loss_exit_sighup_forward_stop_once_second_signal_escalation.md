---
id: task_018_003_002
title: 'Supervisor lifetime: shared lock fd, worker launcher-loss exit, SIGHUP, forward stop once, second-signal escalation'
tier: task
status: completed
parent: feat_018_003
children: []
depends_on:
- task_018_003_001
owners:
- swe
skills: []
parent_rev: a650ec93757565beabb62a80700efd2d29539047
created: '2026-10-23'
updated: '2026-10-23'
---
# Supervisor lifetime: shared lock fd, worker launcher-loss exit, SIGHUP, forward stop once, second-signal escalation

## Parent Feature

[feat_018_003](../../features/2_active/feat_018_003.md)

## Depends on

- task_018_003_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Closes the single-supervisor holes (epic dec_013, dec_014, dec_015).

- `_spawn_worker` adds the `SupervisorLock` handle fd to `pass_fds` and passes its number in the handshake. The worker keeps it open for its whole life and must not leak it to agents (keep subprocess's default `close_fds=True`). `SupervisorLock.release()` only closes the handle and never calls `LOCK_UN`.
- Worker records the launcher pid at start. The first line of `should_stop` checks `os.getppid()`; on change, shut down through `drain_and_shutdown(reason="launcher_lost")`: no drain or turn window, SIGTERM agent pids, 5s grace, **non-zero** exit (never the trailing `return 0`). The same check applies in drain waits.
- Launcher: handle SIGHUP exactly like SIGINT/SIGTERM in every state. When stopping, forward the stop to the worker once (drop the 0.2s re-send loop). A second operator signal calls `_kill_worker_group` immediately and the launcher exits. Transitions go through the task_018_003_001 function.
- Do not touch 002's `finally` block or the existing exit codes.

Integration test: `kill -9` the launcher. The worker exits non-zero within seconds, and until it exits `cascade up --port <other>` on the same workspace exits non-zero. Add one assertion to the same harness: a second SIGTERM while stopping kills the worker group at once.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
