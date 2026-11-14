---
id: task_013_002_002
title: Start a restart-safe independent supervisor audit lane
tier: task
status: completed
parent: feat_013_002
children: []
depends_on:
- task_013_002_001
owners:
- swe
skills: []
parent_rev: d1d322793b212e8a8d7151f409b7751e937d2970
created: '2026-11-08'
updated: '2026-11-08'
provider: codex
flex_mode: false
models:
  swe: gpt-5.6-sol
reasoning:
  swe: medium
---
# Start a restart-safe independent supervisor audit lane

## Parent Feature

[feat_013_002](../../features/2_active/feat_013_002.md)

## Depends on

- task_013_002_001

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

Start the audit lane before blocking startup maintenance, independent of watchdog ticks, review polling, fetches, and model work. Use monotonic deadlines with nonnegative jitter <= min(5% of interval, 60s); coordinate one pass per canonical workspace across processes. Persist a small untracked receipt/cursor only after completed passes (last/next time, duration, counts, schedule recovery data), without triggering board watchers, dispatch, notifications, Git, or provider work. Restore schedule after restart, coalesce overdue intervals, tolerate wall-clock jumps, and create no periodic work when disabled. Prove progress while maintenance is blocked.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
