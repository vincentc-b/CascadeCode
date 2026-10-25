---
id: task_018_003_003
title: Readiness-on-serve, bounded backoff, and degraded 503 responder in the launcher
tier: task
status: completed
parent: feat_018_003
children: []
depends_on:
- task_018_003_001
- task_018_003_002
owners:
- swe
skills: []
parent_rev: a650ec93757565beabb62a80700efd2d29539047
created: '2026-10-23'
updated: '2026-10-23'
---
# Readiness-on-serve, bounded backoff, and degraded 503 responder in the launcher

## Parent Feature

[feat_018_003](../../features/2_active/feat_018_003.md)

## Depends on

- task_018_003_001
- task_018_003_002

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

- Move the single `_write_readiness` call in `run_worker` to just after the server thread starts, ahead of `resume_legally_active_graphs`.
- Replace `CRASH_RESTART_DELAY_S` with exponential backoff for workers that exit before reporting ready: 1s doubling, capped at 30s, at most 5 consecutive attempts. Reset the counter after a worker has been ready for 60s. State `restarting`, with `restart_count` in status.
- Pipe worker stderr through the launcher: forward each line to the launcher's stderr and keep a bounded tail for `last_error.stderr_tail` (dec_016).
- Once attempts are exhausted, enter `degraded`. The launcher keeps the lock and listening socket and answers every request with 503 plus a diagnostic: JSON for `/api/*` (including `GET /api/health`, which returns the status file) and HTML otherwise, showing last exit code, stderr tail, and next action. It polls the stdlib fingerprint and relaunches on change. SIGHUP/SIGINT/SIGTERM stop it (no retry on SIGHUP). Do not import changing Cascade modules in this path.

Integration test (b): a worker that crashes on startup gets bounded retries, then serves a degraded 503 with diagnostics. Fixing the source recovers to `serving` without an operator.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
