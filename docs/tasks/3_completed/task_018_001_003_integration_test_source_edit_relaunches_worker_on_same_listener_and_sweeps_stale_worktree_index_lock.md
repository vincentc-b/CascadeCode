---
id: task_018_001_003
title: 'Integration test: source edit relaunches worker on same listener and sweeps stale worktree index.lock'
tier: task
status: completed
parent: feat_018_001
children: []
depends_on:
- task_018_001_002
owners:
- swe
skills: []
parent_rev: 1a86ddefaff8bbfaf28d9990949bf2400b018cb0
created: '2026-10-23'
updated: '2026-10-23'
---
# Integration test: source edit relaunches worker on same listener and sweeps stale worktree index.lock

## Parent Feature

[feat_018_001](../../features/2_active/feat_018_001.md)

## Depends on

- task_018_001_002
- task_018_001_004 (the stale git lock sweep, split out of task_018_001_002). The board dependency only lists task_018_001_002, so do not start until task_018_001_004 has merged; the `index.lock` assertion fails without it.

## Acceptance criteria

TBD.

## Files likely touched

TBD.

## Implementation notes

One integration test, no separate unit-test matrix.

- Start `cascade up` in a subprocess against a temp workspace that uses a copied Cascade package.
- Record the launcher PID, lock holder, and current worker PID (from the served endpoint or status).
- Plant `.git/index.lock` in a Cascade worktree under `.cascade/worktrees/*`.
- Touch a `.py` file in the copied package.
- Assert: the listener stays connectable throughout (including a connection attempted during the restart gap, which succeeds instead of being refused); a new worker PID answers on the same host:port; the launcher PID and lock holder are unchanged; the planted `index.lock` is gone.
- Tear down with SIGTERM to the launcher and assert it exits 0 with no surviving worker process group.

## Skills

_(none)_

## Test plan

TBD.

## Out of scope

TBD.
